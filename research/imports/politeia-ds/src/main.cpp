#include "core/types.hpp"
#include "core/config.hpp"
#include "core/particle_data.hpp"
#include "domain/cell_list.hpp"
#include "domain/sfc_decomposition.hpp"
#include "integrator/langevin_integrator.hpp"
#include "interaction/resource_exchange.hpp"
#include "interaction/culture_dynamics.hpp"
#include "interaction/tech_spread.hpp"
#include "interaction/loyalty.hpp"
#include "population/reproduction.hpp"
#include "population/mortality.hpp"
#include "population/plague.hpp"
#include "population/carrying_capacity.hpp"
#include "analysis/order_params.hpp"
#include "analysis/network_analysis.hpp"
#include "analysis/polity.hpp"
#include "analysis/phase_transition.hpp"
#include "analysis/perf_monitor.hpp"
#include "force/terrain_force.hpp"
#include "force/terrain_loader.hpp"
#include "climate/climate_grid.hpp"
#include "river/river_field.hpp"
#include "io/csv_writer.hpp"
#include "io/ic_loader.hpp"
#include "io/checkpoint.hpp"

#include <algorithm>
#include <iostream>
#include <iomanip>
#include <random>
#include <chrono>
#include <cmath>
#include <filesystem>
#include <cstring>
#include "analysis/async_analyzer.hpp"

#ifdef POLITEIA_USE_MPI
#include <mpi.h>
#endif

int main(int argc, char* argv[]) {
    int rank = 0;
    int nprocs = 1;

#ifdef POLITEIA_USE_MPI
    MPI_Init(&argc, &argv);
    MPI_Comm_rank(MPI_COMM_WORLD, &rank);
    MPI_Comm_size(MPI_COMM_WORLD, &nprocs);
#endif

    // Parse CLI: politeia [config.cfg]
    //            politeia --restart checkpoint.bin [override.cfg]
    std::string cfg_path;
    std::string restart_path;
    for (int argi = 1; argi < argc; ++argi) {
        if (std::strcmp(argv[argi], "--restart") == 0 && argi + 1 < argc) {
            restart_path = argv[++argi];
        } else {
            cfg_path = argv[argi];
        }
    }

    politeia::SimConfig cfg;
    if (!cfg_path.empty()) {
        cfg = politeia::load_config(cfg_path);
    } else {
        cfg = politeia::default_config();
    }
    if (!restart_path.empty()) {
        cfg.restart_file = restart_path;
    }
    const bool is_restart = !cfg.restart_file.empty();

    // --- SFC Domain Decomposition (Morton Z-curve) ---
    politeia::SFCDecomposition domain;
    constexpr int SFC_LEVEL = 10;  // 2^10 × 2^10 = ~100万 Morton cell
    domain.init(
        cfg.domain_xmin, cfg.domain_xmax,
        cfg.domain_ymin, cfg.domain_ymax,
        SFC_LEVEL, rank, nprocs
    );

    // --- Initialize particles ---
    const bool use_ic_file = !cfg.initial_conditions_file.empty();

    // Step counter for restart support
    politeia::Index start_step = 0;

    if (rank == 0) {
        std::cout << "=== Politeia v0.1.0 ===\n"
                  << "Processes: " << nprocs << "\n"
                  << "Domain: [" << cfg.domain_xmin << ", " << cfg.domain_xmax
                  << "] x [" << cfg.domain_ymin << ", " << cfg.domain_ymax << "]\n";
        if (is_restart) {
            std::cout << "Mode: RESTART from " << cfg.restart_file << "\n";
        } else {
            std::cout << "Particles: " << cfg.initial_particles
                      << (use_ic_file ? " (from " + cfg.initial_conditions_file + ")" : " (grid)") << "\n";
        }
        std::cout << "Steps: " << cfg.total_steps << "\n"
                  << "dt: " << cfg.dt << "\n"
                  << "Temperature: " << cfg.temperature << "\n"
                  << "Friction: " << cfg.friction << "\n";
        if (cfg.checkpoint_interval > 0) {
            std::cout << "Checkpoint: every " << cfg.checkpoint_interval
                      << " steps -> " << cfg.checkpoint_dir << "/\n";
        }
        std::cout << std::endl;
    }

    politeia::Index init_capacity = 256;
    if (!is_restart) {
        if (use_ic_file) {
            // Avoid repeated doubling reallocations when loading large IC CSVs
            init_capacity = (cfg.initial_particles > 0) ? cfg.initial_particles : 256;
        } else {
            init_capacity = cfg.initial_particles * 4;
        }
    }

    politeia::ParticleData particles(init_capacity, cfg.culture_dim);
    particles.set_id_seed(rank);

    if (is_restart) {
        // ── Restart from checkpoint ──
        uint64_t ckpt_step = 0;
        double ckpt_time = 0.0;
        politeia::read_checkpoint(cfg.restart_file, particles, ckpt_step, ckpt_time,
                                  rank, nprocs);
        start_step = static_cast<politeia::Index>(ckpt_step);
        if (rank == 0) {
            std::cout << "Restarted from step " << start_step
                      << " (time=" << ckpt_time << "), will run to step "
                      << cfg.total_steps << "\n";
        }
    } else if (use_ic_file) {
        std::mt19937_64 rng(cfg.random_seed + rank);
        politeia::Index loaded = politeia::load_initial_conditions(
            cfg.initial_conditions_file, particles, cfg, rng, rank);
        if (rank == 0 && loaded == 0) {
            std::cerr << "Warning: no particles loaded from " << cfg.initial_conditions_file << "\n";
        }
    } else {
        politeia::Index local_n = cfg.initial_particles / static_cast<politeia::Index>(nprocs);
        if (rank == 0) local_n += cfg.initial_particles % nprocs;

        particles.reserve(local_n * 4);

        std::mt19937_64 rng(cfg.random_seed + rank);

        const politeia::Real margin = cfg.social_distance * 1.5;
        const politeia::Real Lx = cfg.domain_xmax - cfg.domain_xmin - 2.0 * margin;
        const politeia::Real Ly = cfg.domain_ymax - cfg.domain_ymin - 2.0 * margin;

        const politeia::Real band_y_start = cfg.domain_ymin + margin + Ly * rank / nprocs;
        const politeia::Real band_y_end = cfg.domain_ymin + margin + Ly * (rank + 1) / nprocs;
        const politeia::Real band_Ly = band_y_end - band_y_start;

        const int nx_grid = std::max(1, static_cast<int>(std::ceil(std::sqrt(static_cast<double>(local_n) * Lx / band_Ly))));
        const int ny_grid = std::max(1, static_cast<int>(std::ceil(static_cast<double>(local_n) / nx_grid)));
        const politeia::Real dx = Lx / nx_grid;
        const politeia::Real dy = band_Ly / ny_grid;

        std::normal_distribution<politeia::Real> jitter(0.0, cfg.init_jitter_factor * std::min(dx, dy));
        std::normal_distribution<politeia::Real> dist_p(0.0, std::sqrt(cfg.temperature));
        std::uniform_real_distribution<politeia::Real> dist_age(cfg.init_age_min, cfg.init_age_max);
        std::normal_distribution<politeia::Real> dist_cv(0.0, 1.0);
        std::uniform_real_distribution<politeia::Real> dist_sex(0.0, 1.0);
        std::uniform_real_distribution<politeia::Real> dist_u01(0.0, 1.0);
        constexpr politeia::Real PYR_LAMBDA = 0.03;
        constexpr politeia::Real PYR_MAX = 70.0;
        const politeia::Real pyr_exp = std::exp(-PYR_LAMBDA * PYR_MAX);

        politeia::Index placed = 0;
        for (int iy = 0; iy < ny_grid && placed < local_n; ++iy) {
            for (int ix = 0; ix < nx_grid && placed < local_n; ++ix) {
                politeia::Real x = cfg.domain_xmin + margin + (ix + 0.5) * dx + jitter(rng);
                politeia::Real y = band_y_start + (iy + 0.5) * dy + jitter(rng);
                politeia::Vec2 pos = {x, y};
                politeia::Vec2 mom = {dist_p(rng), dist_p(rng)};
                politeia::Real age = cfg.age_pyramid
                    ? -std::log(1.0 - dist_u01(rng) * (1.0 - pyr_exp)) / PYR_LAMBDA
                    : dist_age(rng);
                politeia::Index idx = particles.add_particle(pos, mom, cfg.initial_wealth, 1.0, age);
                if (cfg.gender_enabled) {
                    particles.sex(idx) = (dist_sex(rng) < cfg.sex_ratio) ? 1 : 0;
                }
                for (int d = 0; d < cfg.culture_dim; ++d) {
                    particles.culture(idx, d) = dist_cv(rng);
                }
                ++placed;
            }
        }
    }

    // Initial SFC distribution: balance particles across ranks by Morton key
    {
        auto keys = domain.compute_keys(particles);
        domain.rebalance(keys);
        domain.redistribute(particles);
        particles.rebuild_gid_map();
    }

    // Create checkpoint output directory if needed
    if (cfg.checkpoint_interval > 0 && rank == 0) {
        std::filesystem::create_directories(cfg.checkpoint_dir);
    }

    // --- Initialize cell list (uses global domain; SFC handles partitioning) ---
    // Cell size must cover both interaction range and density radius for neighbor searching
    const politeia::Real cell_cutoff = std::max(cfg.interaction_range, cfg.density_radius);
    politeia::CellList cells;
    cells.init(cfg.domain_xmin, cfg.domain_xmax,
               cfg.domain_ymin, cfg.domain_ymax, cell_cutoff);

    // --- Initialize terrain ---
    politeia::TerrainParams terrain;  // Gaussian wells (fallback)
    politeia::TerrainGrid terrain_grid;

    const bool use_synthetic_grid =
        (cfg.terrain_type == "valley" || cfg.terrain_type == "river" ||
         cfg.terrain_type == "basins" || cfg.terrain_type == "continent" ||
         cfg.terrain_type == "ridge" || cfg.terrain_type == "china" ||
         cfg.terrain_type == "europe");

    if (cfg.terrain_type == "grid" && !cfg.terrain_file.empty()) {
        if (cfg.terrain_format == "binary") {
            terrain_grid.load_binary(cfg.terrain_file,
                cfg.terrain_grid_rows, cfg.terrain_grid_cols,
                cfg.domain_xmin, cfg.domain_ymin,
                (cfg.domain_xmax - cfg.domain_xmin) / std::max(cfg.terrain_grid_cols - 1, 1));
        } else {
            terrain_grid.load_ascii(cfg.terrain_file);
        }
        if (rank == 0) {
            std::cout << "Terrain: grid " << terrain_grid.ncols() << "x" << terrain_grid.nrows()
                      << " h=[" << terrain_grid.h_min() << ", " << terrain_grid.h_max()
                      << "] scale=" << cfg.terrain_scale << "\n";
        }
    } else if (use_synthetic_grid) {
        int grid_res = 128;
        terrain_grid.generate_synthetic(grid_res, grid_res,
            cfg.domain_xmin, cfg.domain_ymin,
            cfg.domain_xmax, cfg.domain_ymax, cfg.terrain_type);
        if (rank == 0) {
            std::cout << "Terrain: synthetic '" << cfg.terrain_type
                      << "' " << grid_res << "x" << grid_res
                      << " h=[" << terrain_grid.h_min() << ", " << terrain_grid.h_max()
                      << "] scale=" << cfg.terrain_scale << "\n";
        }
    } else if (cfg.terrain_type == "flat") {
        if (rank == 0) {
            std::cout << "Terrain: flat (no wells)\n";
        }
    } else {
        // Default Gaussian wells
        terrain.wells.push_back({
            0.5 * (cfg.domain_xmin + cfg.domain_xmax),
            0.5 * (cfg.domain_ymin + cfg.domain_ymax),
            10.0, 25.0
        });
        terrain.wells.push_back({
            0.3 * (cfg.domain_xmin + cfg.domain_xmax),
            0.7 * (cfg.domain_ymin + cfg.domain_ymax),
            6.0, 15.0
        });
        if (rank == 0) {
            std::cout << "Terrain: " << terrain.wells.size() << " Gaussian wells\n";
        }
    }

    // --- Initialize integrator (BBK/Langevin) ---
    // 反射边界在全局域边界上（SFC 只负责 rank 间分配，不做边界反射）
    const politeia::TerrainGrid* grid_ptr = terrain_grid.loaded() ? &terrain_grid : nullptr;
    politeia::LangevinIntegrator integrator(
        cfg.dt, 1.0, cfg.friction, cfg.temperature,
        politeia::SocialForceParams{cfg.social_strength, cfg.social_distance, cfg.interaction_range},
        terrain,
        cfg.domain_xmin, cfg.domain_xmax,
        cfg.domain_ymin, cfg.domain_ymax,
        cfg.random_seed + rank * 1000003,
        grid_ptr, cfg.terrain_scale
    );

    // --- Initialize river field ---
    politeia::RiverField river_field;
    if (cfg.river_enabled) {
        if (cfg.river_mode == "file" && !cfg.river_file.empty()) {
            if (cfg.river_format == "binary") {
                river_field.load_binary(
                    cfg.river_file,
                    cfg.river_grid_rows, cfg.river_grid_cols,
                    cfg.domain_xmin, cfg.domain_ymin,
                    (cfg.domain_xmax - cfg.domain_xmin) / std::max(cfg.river_grid_cols - 1, 1)
                );
            } else {
                river_field.load_ascii(cfg.river_file);
            }
        } else {
            const politeia::Real x_span = cfg.domain_xmax - cfg.domain_xmin;
            const politeia::Real y_span = cfg.domain_ymax - cfg.domain_ymin;
            const int river_cols = 256;
            const int river_rows = std::max(32, static_cast<int>(std::round(river_cols * y_span / std::max(x_span, 1.0))));
            river_field.generate_synthetic(
                river_rows, river_cols,
                cfg.domain_xmin, cfg.domain_ymin,
                cfg.domain_xmax, cfg.domain_ymax,
                cfg.river_type
            );
        }
        if (rank == 0) {
            std::cout << "RiverField: " << (cfg.river_mode == "file" ? "file" : "procedural")
                      << " " << river_field.ncols() << "x" << river_field.nrows()
                      << " type=" << cfg.river_type << "\n";
        }
    }

    // --- Initialize climate ---
    politeia::ClimateGrid climate_grid;
    politeia::ClimateTimeMode climate_time_mode = politeia::ClimateTimeMode::Static;
    if (cfg.climate_enabled) {
        if (cfg.climate_mode == "file" && !cfg.climate_file.empty()) {
            climate_grid.load_ascii(cfg.climate_file);
        } else {
            climate_grid.generate_procedural(
                128, 256,
                cfg.domain_xmin, cfg.domain_ymin,
                cfg.domain_xmax, cfg.domain_ymax,
                grid_ptr
            );
        }
        if (cfg.climate_time_mode == "drift") {
            climate_time_mode = politeia::ClimateTimeMode::Drift;
        } else if (cfg.climate_time_mode == "seasonal") {
            climate_time_mode = politeia::ClimateTimeMode::Seasonal;
        }
        if (!cfg.climate_drift_schedule.empty()) {
            climate_grid.set_drift_schedule(cfg.climate_drift_schedule);
        }
        if (rank == 0) {
            std::cout << "Climate: " << (cfg.climate_mode == "file" ? "file" : "procedural")
                      << " " << climate_grid.ncols() << "x" << climate_grid.nrows()
                      << " mode=" << cfg.climate_time_mode << "\n";
        }
    }

    // --- I/O ---
    politeia::CSVWriter writer(cfg.output_dir);

    // --- Initial force computation (needed for first Verlet half-step) ---
    {
        auto& f = particles.force_buffer();
        std::fill(f.begin(), f.end(), 0.0);
        cells.build(particles.x_data(), particles.count());
        (void)politeia::compute_social_forces(
            particles.x_data(), f.data(), particles.count(), cells,
            {cfg.social_strength, cfg.social_distance, cfg.interaction_range}
        );
        if (terrain_grid.loaded()) {
            (void)politeia::compute_grid_terrain_forces(
                particles.x_data(), f.data(), particles.count(),
                terrain_grid, cfg.terrain_scale);
        } else {
            (void)politeia::compute_terrain_forces(
                particles.x_data(), f.data(), particles.count(), terrain);
        }
    }

    // --- Resource exchange parameters ---
    politeia::ExchangeParams exchange_params;
    exchange_params.exchange_rate = cfg.exchange_rate;
    exchange_params.cutoff = (cfg.exchange_cutoff > 0) ? cfg.exchange_cutoff : cfg.interaction_range;
    exchange_params.terrain_barrier_enabled = cfg.terrain_barrier_enabled;
    exchange_params.terrain_barrier_scale = cfg.terrain_barrier_scale;
    exchange_params.river_exchange_enabled = cfg.river_enabled && cfg.river_exchange_enabled;
    exchange_params.river_exchange_strength = cfg.river_exchange_strength;
    exchange_params.ability_saturation_w = cfg.ability_saturation_w;

    // --- Reproduction parameters ---
    politeia::ReproductionParams repro_params;
    repro_params.puberty_age = cfg.puberty_age;
    repro_params.menopause_age = cfg.menopause_age;
    repro_params.peak_fertility_age = cfg.peak_fertility_age;
    repro_params.max_fertility = cfg.max_fertility;
    repro_params.gestation_time = cfg.gestation_time;
    repro_params.nursing_time = cfg.nursing_time;
    repro_params.mate_range = (cfg.mate_range > 0) ? cfg.mate_range : cfg.interaction_range;
    repro_params.wealth_birth_cost = cfg.wealth_birth_cost;
    repro_params.min_wealth_to_breed = cfg.min_wealth_to_breed;
    repro_params.mutation_strength = cfg.mutation_strength;
    repro_params.culture_mutation_scale = cfg.culture_mutation_scale;
    repro_params.epsilon_mutation_scale = cfg.epsilon_mutation_scale;
    repro_params.fertility_alpha = cfg.fertility_alpha;
    repro_params.culture_mate_threshold = cfg.culture_mate_threshold;
    repro_params.gender_enabled = cfg.gender_enabled;
    repro_params.sex_ratio = cfg.sex_ratio;
    repro_params.male_cooldown = cfg.male_cooldown;
    repro_params.max_partners_per_cooldown = cfg.max_partners_per_cooldown;
    repro_params.partner_wealth_factor = cfg.partner_wealth_factor;
    repro_params.inheritance_model = cfg.inheritance_model;
    repro_params.epsilon_patrilineal_threshold = cfg.epsilon_patrilineal_threshold;
    repro_params.culture_dominant_weight = cfg.culture_dominant_weight;

    // --- Culture dynamics parameters ---
    politeia::CultureParams culture_params;
    culture_params.assimilation_rate = cfg.assimilation_rate;
    culture_params.interaction_range = cfg.interaction_range;
    culture_params.repulsion_threshold = cfg.repulsion_threshold;
    culture_params.repulsion_strength = cfg.repulsion_strength;
    culture_params.attraction_strength = cfg.attraction_strength;
    culture_params.culture_mate_threshold = cfg.culture_mate_threshold;

    // --- Technology parameters ---
    politeia::TechParams tech_params;
    tech_params.drift_rate = cfg.tech_drift_rate;
    tech_params.spread_rate = cfg.tech_spread_rate;
    tech_params.spread_range = cfg.interaction_range;
    tech_params.river_enabled = cfg.river_enabled && cfg.river_tech_enabled;
    tech_params.river_strength = cfg.river_tech_strength;
    tech_params.jump_base_rate = cfg.tech_jump_base_rate;
    tech_params.jump_knowledge_scale = cfg.tech_jump_knowledge_scale;
    tech_params.jump_magnitude = cfg.tech_jump_magnitude;
    tech_params.wealth_jump_rate_pos = cfg.wealth_jump_rate_pos;
    tech_params.wealth_jump_rate_neg = cfg.wealth_jump_rate_neg;
    tech_params.wealth_jump_fraction = cfg.wealth_jump_fraction;

    // Network analysis for hierarchy detection
    politeia::InteractionNetwork network;
    network.resize(cfg.initial_particles);
    const politeia::Index network_window = std::max(
        cfg.output_interval * cfg.network_window_factor, politeia::Index(1));

    // Async heavy analysis (polity detection, hierarchy metrics, etc.)
    politeia::AsyncAnalyzer async_analyzer(&writer, cfg.snapshot_binary);

    // --- Loyalty system parameters ---
    politeia::LoyaltyParams loyalty_params;
    loyalty_params.protection_gain = cfg.loyalty_protection_gain;
    loyalty_params.tax_drain = cfg.loyalty_tax_drain;
    loyalty_params.culture_penalty = cfg.loyalty_culture_penalty;
    loyalty_params.noise_sigma = cfg.loyalty_noise_sigma;
    loyalty_params.tax_rate = cfg.tax_rate;
    loyalty_params.tax_efficiency = cfg.tax_efficiency;
    loyalty_params.rebel_threshold = cfg.rebel_threshold;
    loyalty_params.switch_threshold = cfg.switch_threshold;
    loyalty_params.attachment_threshold = cfg.attachment_threshold;
    loyalty_params.initial_loyalty = cfg.initial_loyalty;
    loyalty_params.succession_loyalty_factor = cfg.succession_loyalty_factor;
    loyalty_params.succession_heir_loyalty_cap = cfg.succession_heir_loyalty_cap;
    loyalty_params.max_hierarchy_depth = cfg.max_hierarchy_depth;

    // --- Plague parameters ---
    politeia::PlagueParams plague_params;
    plague_params.trigger_density = cfg.plague_trigger_density;
    plague_params.trigger_rate = cfg.plague_trigger_rate;
    plague_params.infection_radius = cfg.plague_infection_radius;
    plague_params.infection_rate = cfg.plague_infection_rate;
    plague_params.base_mortality = cfg.plague_base_mortality;
    plague_params.recovery_time = cfg.plague_recovery_time;
    plague_params.immunity_inheritance = cfg.plague_immunity_inheritance;

    politeia::PlagueManager plague_mgr;
    if (cfg.plague_enabled) {
        plague_mgr.init(particles.capacity(), cfg.n_pathogens);
    }

    // --- Mortality parameters ---
    politeia::MortalityParams mort_params;
    mort_params.gompertz_alpha = cfg.gompertz_alpha;
    mort_params.gompertz_beta = cfg.gompertz_beta;
    mort_params.max_age = cfg.max_age;
    mort_params.accident_rate = cfg.accident_rate;
    mort_params.survival_threshold = cfg.survival_threshold;
    mort_params.starvation_sigmoid_k = cfg.starvation_sigmoid_k;
    mort_params.lifespan_wealth_enabled = cfg.lifespan_wealth_enabled;
    mort_params.lifespan_wealth_k = cfg.lifespan_wealth_k;
    mort_params.lifespan_wealth_ref = cfg.lifespan_wealth_ref;
    mort_params.lifespan_wealth_beta_alpha = cfg.lifespan_wealth_beta_alpha;
    mort_params.lifespan_tech_enabled = cfg.lifespan_tech_enabled;
    mort_params.lifespan_tech_k = cfg.lifespan_tech_k;
    mort_params.lifespan_tech_ref = cfg.lifespan_tech_ref;
    mort_params.lifespan_tech_beta_alpha = cfg.lifespan_tech_beta_alpha;

    std::mt19937_64 pop_rng(cfg.random_seed + rank * 999983);

    // Density/carrying capacity cache (recomputed periodically, not every step)
    std::vector<politeia::Real> cached_density;
    std::vector<politeia::Real> cached_K;
    std::vector<politeia::Real> cached_density_factor;
    const politeia::Index DENSITY_UPDATE_INTERVAL = cfg.density_update_interval;

    // Precompute terrain potential at each particle for resource production
    std::vector<politeia::Real> terrain_at_particle;
    std::vector<politeia::Real> river_proximity_at_particle;

    auto update_terrain_potential = [&]() {
        terrain_at_particle.resize(particles.count(), 0.0);
        const politeia::Real* x = particles.x_data();
        for (politeia::Index i = 0; i < particles.count(); ++i) {
            if (terrain_grid.loaded()) {
                terrain_at_particle[i] = politeia::grid_terrain_potential(
                    x[2*i], x[2*i+1], terrain_grid, cfg.terrain_scale);
            } else {
                terrain_at_particle[i] = politeia::terrain_potential(x[2*i], x[2*i+1], terrain);
            }
        }
    };

    auto update_river_field = [&]() {
        river_proximity_at_particle.resize(particles.count(), 0.0);
        if (!river_field.loaded()) {
            std::fill(river_proximity_at_particle.begin(), river_proximity_at_particle.end(), 0.0);
            return;
        }
        const politeia::Real* x = particles.x_data();
        for (politeia::Index i = 0; i < particles.count(); ++i) {
            river_proximity_at_particle[i] = river_field.proximity(x[2 * i], x[2 * i + 1]);
        }
    };

    update_terrain_potential();
    update_river_field();

    // Initial SFC neighbor discovery
    domain.discover_neighbors(particles, cfg.interaction_range);

    // compute_load_stats contains MPI_Allreduce — all ranks must call it
    auto init_lstats = domain.compute_load_stats(particles.count());

    if (rank == 0) {
        std::cout << "Initialized " << init_lstats.global_total << " particles (local: " << particles.count() << ")\n"
                  << "SFC level: " << SFC_LEVEL << " (grid " << (1 << SFC_LEVEL) << "x" << (1 << SFC_LEVEL) << ")\n"
                  << "Mode: " << (integrator.is_deterministic() ? "Velocity-Verlet (deterministic)" : "Langevin (BBK)") << "\n"
                  << "Load balance: efficiency=" << init_lstats.efficiency * 100 << "%\n"
                  << std::endl;
        writer.write_positions(particles, 0);
    }

    // --- Performance monitor ---
    politeia::PerfMonitor perf;
    perf.reset();

    // Auto-rebalance: trigger when efficiency drops below this threshold
    constexpr double REBALANCE_EFFICIENCY_THRESHOLD = 0.5;
    // Minimum steps between auto-triggered rebalances to avoid thrashing
    constexpr politeia::Index MIN_REBALANCE_GAP = 50;
    politeia::Index steps_since_rebalance = 0;

    // --- Validate intervals (prevent division by zero) ---
    if (cfg.output_interval == 0) cfg.output_interval = 1;
    if (cfg.compact_interval == 0) cfg.compact_interval = 100;
    if (cfg.density_update_interval == 0) cfg.density_update_interval = 10;

    // --- Main time-stepping loop ---
    auto t_start = std::chrono::steady_clock::now();
    politeia::Index total_deaths = 0;
    politeia::Index cached_global_N = init_lstats.global_total;

    // Demographic tracking: accumulate births/deaths between output intervals
    politeia::Index interval_births = 0;
    politeia::Index interval_deaths = 0;

    // Progress reporting interval: print a lightweight status line so the
    // user can tell the simulation is alive between full output_interval dumps.
    const politeia::Index progress_interval = std::max(
        cfg.compact_interval, politeia::Index(100));

    for (politeia::Index step = start_step + 1; step <= cfg.total_steps; ++step) {
        if (rank == 0 && step % progress_interval == 0
            && step % cfg.output_interval != 0) {
            auto t_now = std::chrono::steady_clock::now();
            double wall = std::chrono::duration<double>(t_now - t_start).count();
            double pct = 100.0 * step / cfg.total_steps;
            double step_rate = (step - start_step) / std::max(wall, 1e-9);
            double eta = (cfg.total_steps - step) / std::max(step_rate, 1e-9);
            std::cout << "  [" << step << "/" << cfg.total_steps
                      << "]  " << std::fixed << std::setprecision(1) << pct << "%"
                      << "  N=" << cached_global_N
                      << "  wall=" << std::setprecision(0) << wall << "s"
                      << "  rate=" << std::setprecision(1) << step_rate << " step/s"
                      << "  ETA=" << std::setprecision(0) << eta << "s"
                      << std::defaultfloat << "\n" << std::flush;
        }

        // 1. Langevin dynamics (positions + momenta)
        perf.start(politeia::PerfMonitor::Dynamics);
        auto state = integrator.step(particles, cells);

        if (cfg.river_enabled && cfg.river_force_enabled && river_field.loaded()) {
            politeia::Real* p = particles.p_data();
            const politeia::Real* x = particles.x_data();
            const politeia::Index n = particles.count();
            for (politeia::Index i = 0; i < n; ++i) {
                const politeia::Vec2 river_force = river_field.force(
                    x[2 * i], x[2 * i + 1], cfg.river_force_scale
                );
                p[2 * i] += cfg.dt * river_force[0];
                p[2 * i + 1] += cfg.dt * river_force[1];
            }
        }

        // Climate friction: extra per-particle momentum damping in harsh climates
        if (cfg.climate_enabled && cfg.climate_friction_enabled && climate_grid.loaded()) {
            politeia::Real* p = particles.p_data();
            const politeia::Real* x = particles.x_data();
            const politeia::Index n = particles.count();
            for (politeia::Index i = 0; i < n; ++i) {
                auto cf = climate_grid.factors_at(x[2*i], x[2*i+1],
                    cfg.climate_mortality_scale, cfg.climate_friction_scale,
                    cfg.climate_plague_scale);
                if (cf.friction_factor > 1.0) {
                    politeia::Real damp = 1.0 - (cf.friction_factor - 1.0) * cfg.dt;
                    damp = std::max(0.5, std::min(1.0, damp));
                    p[2*i]   *= damp;
                    p[2*i+1] *= damp;
                }
            }
        }
        update_terrain_potential();
        update_river_field();

        // Berendsen thermostat: gradual velocity rescaling every step.
        // Target KE = N*T for 2D (equipartition: d/2 * N * kT with d=2).
        // Uses Berendsen coupling with tau_T to avoid energy sloshing from
        // instant resets; hard cap at 2×T prevents divergence in dense clusters.
        if (cfg.temperature > 0.0) {
            const politeia::Real* p_data = particles.p_data();
            const politeia::Index n_ke = particles.count();
            politeia::Real ke = 0.0;
            for (politeia::Index i = 0; i < n_ke * 2; ++i) ke += p_data[i] * p_data[i];
            ke *= 0.5;
            const politeia::Real target_ke = n_ke * cfg.temperature;  // 2D: N*kT
            const politeia::Real ke_ratio = ke / std::max(target_ke, 1e-15);

            constexpr politeia::Real tau_T = 0.1;  // coupling time (in sim time units)
            const politeia::Real berendsen_dt = cfg.dt / tau_T;

            if (ke_ratio > 1.2) {
                // Gradual Berendsen coupling toward target
                politeia::Real lambda = std::sqrt(1.0 + berendsen_dt * (1.0 / ke_ratio - 1.0));
                lambda = std::max(lambda, 0.9);  // limit per-step correction to 10%
                // Hard cap: if temperature is dangerously high, apply stronger correction
                if (ke_ratio > 2.0) {
                    lambda = std::sqrt(1.0 / ke_ratio);
                }
                politeia::Real* p = particles.p_data();
                for (politeia::Index i = 0; i < n_ke * 2; ++i) p[i] *= lambda;
            }
        }

        perf.stop(politeia::PerfMonitor::Dynamics);

        // 2. Resource exchange between neighbors (symmetric rule)
        // Record network flows in the last 20 steps of each compact_interval
        // so form_attachments gets enough accumulated signal for hierarchy formation.
        perf.start(politeia::PerfMonitor::Exchange);
        constexpr politeia::Index NETWORK_RECORD_WINDOW = 20;
        bool need_network = cfg.loyalty_enabled
                         && (step % cfg.compact_interval >= cfg.compact_interval - NETWORK_RECORD_WINDOW);
        (void)politeia::exchange_resources(particles, cells, exchange_params,
            need_network ? &network : nullptr,
            terrain_at_particle.empty() ? nullptr : terrain_at_particle.data(),
            river_proximity_at_particle.empty() ? nullptr : river_proximity_at_particle.data());
        perf.stop(politeia::PerfMonitor::Exchange);

        // 3. Cultural dynamics: assimilation between neighbors
        perf.start(politeia::PerfMonitor::Culture);
        if (cfg.culture_enabled) {
            politeia::evolve_culture(particles, cells, culture_params, cfg.dt);
        }
        perf.stop(politeia::PerfMonitor::Culture);

        // 4. Technology evolution: drift + contact spread + Poisson jumps
        perf.start(politeia::PerfMonitor::Technology);
        if (cfg.technology_enabled) {
            (void)politeia::evolve_technology(
                particles, cells, tech_params, cfg.dt, pop_rng,
                river_proximity_at_particle.empty() ? nullptr : river_proximity_at_particle.data()
            );
        }
        perf.stop(politeia::PerfMonitor::Technology);

        // 5. Resource consumption and terrain-based production (with density competition)
        perf.start(politeia::PerfMonitor::Resources);
        // Climate time advance (periodic update)
        if (cfg.climate_enabled && climate_grid.loaded() &&
            cfg.climate_update_interval > 0 &&
            step % static_cast<politeia::Index>(cfg.climate_update_interval) == 0) {
            climate_grid.advance(step, climate_time_mode,
                cfg.climate_drift_rate, cfg.climate_season_amplitude,
                cfg.climate_season_period, cfg.dt);
        }

        if (step % DENSITY_UPDATE_INTERVAL == 1 || step == 1 ||
            cached_density.size() != particles.count()) {
            if (cfg.carrying_capacity_enabled) {
                cached_density = politeia::compute_local_density(
                    particles, cells, cfg.density_radius);
                cached_K = politeia::compute_carrying_capacity(
                    particles, cfg.carrying_capacity_base, terrain_at_particle.data(),
                    river_proximity_at_particle.empty() ? nullptr : river_proximity_at_particle.data(),
                    cfg.river_enabled && cfg.river_capacity_enabled,
                    cfg.river_capacity_strength,
                    cfg.river_capacity_beta
                );

                // Climate carrying capacity modulation
                if (cfg.climate_enabled && cfg.climate_carrying_enabled && climate_grid.loaded()) {
                    const politeia::Real* x = particles.x_data();
                    for (politeia::Index i = 0; i < particles.count(); ++i) {
                        auto cf = climate_grid.factors_at(x[2*i], x[2*i+1],
                            cfg.climate_mortality_scale, cfg.climate_friction_scale,
                            cfg.climate_plague_scale);
                        cached_K[i] *= cf.carrying_factor;
                    }
                }

                cached_density_factor.resize(particles.count());
                for (politeia::Index i = 0; i < particles.count(); ++i) {
                    if (cached_K[i] > 1e-15 && cached_density[i] > cached_K[i]) {
                        cached_density_factor[i] = cached_K[i] / cached_density[i];
                    } else {
                        cached_density_factor[i] = 1.0;
                    }
                }
            } else {
                cached_density.assign(particles.count(), 0.0);
                cached_K.assign(particles.count(), 1e10);
                cached_density_factor.assign(particles.count(), 1.0);
            }
        }

        // Apply climate production modulation
        if (cfg.climate_enabled && cfg.climate_production_enabled && climate_grid.loaded()) {
            const politeia::Real* x = particles.x_data();
            politeia::Real* w = particles.w_data();
            const politeia::Real* eps = particles.eps_data();
            for (politeia::Index i = 0; i < particles.count(); ++i) {
                auto cf = climate_grid.factors_at(x[2*i], x[2*i+1],
                    cfg.climate_mortality_scale, cfg.climate_friction_scale,
                    cfg.climate_plague_scale);
                politeia::Real local_resource = 0.0;
                if (terrain_at_particle.data() != nullptr) {
                    local_resource = cfg.base_production * std::max(0.0, -terrain_at_particle[i]);
                }
                politeia::Real climate_bonus = local_resource * eps[i] * cfg.dt * (cf.production_factor - 1.0);
                if (cached_density_factor.size() > i) {
                    climate_bonus *= cached_density_factor[i];
                }
                w[i] += climate_bonus;
            }
        }

        politeia::apply_resource_dynamics(
            particles, cfg.dt, cfg.consumption_rate,
            cfg.base_production,
            terrain_at_particle.data(),
            cached_density_factor.data(),
            river_proximity_at_particle.empty() ? nullptr : river_proximity_at_particle.data(),
            cfg.river_enabled && cfg.river_resource_enabled,
            cfg.river_resource_strength,
            cfg.river_resource_alpha,
            cfg.wealth_decay_rate
        );
        perf.stop(politeia::PerfMonitor::Resources);

        // 6. Population dynamics: age, death, plague, reproduction
        perf.start(politeia::PerfMonitor::Population);
        politeia::advance_age(particles, cfg.dt);

        politeia::Index deaths = politeia::apply_mortality(particles, mort_params, cfg.dt, pop_rng);

        // Climate-induced extra mortality
        if (cfg.climate_enabled && cfg.climate_mortality_enabled && climate_grid.loaded()) {
            const politeia::Real* x = particles.x_data();
            for (politeia::Index i = 0; i < particles.count(); ++i) {
                if (particles.status(i) != politeia::ParticleStatus::Alive) continue;
                auto cf = climate_grid.factors_at(x[2*i], x[2*i+1],
                    cfg.climate_mortality_scale, cfg.climate_friction_scale,
                    cfg.climate_plague_scale);
                if (cf.mortality_addition > 0.0) {
                    politeia::Real death_prob = cf.mortality_addition * cfg.dt;
                    if (std::uniform_real_distribution<politeia::Real>(0.0, 1.0)(pop_rng) < death_prob) {
                        particles.mark_dead(i);
                        ++deaths;
                    }
                }
            }
        }

        politeia::Index plague_deaths = 0;
        if (cfg.plague_enabled) {
            politeia::Real bbox_area = std::max(1.0,
                (domain.local_xmax() - domain.local_xmin()) * (domain.local_ymax() - domain.local_ymin()));
            politeia::Real density_estimate = static_cast<politeia::Real>(particles.count()) / bbox_area;

            // Climate plague modulation: scale trigger rate
            politeia::PlagueParams local_plague_params = plague_params;
            if (cfg.climate_enabled && cfg.climate_plague_enabled && climate_grid.loaded()) {
                politeia::Real avg_plague_factor = 1.0;
                if (particles.count() > 0) {
                    const politeia::Real* x = particles.x_data();
                    politeia::Real sum_f = 0.0;
                    politeia::Index sample_n = std::min(particles.count(), static_cast<politeia::Index>(100));
                    for (politeia::Index i = 0; i < sample_n; ++i) {
                        auto cf = climate_grid.factors_at(x[2*i], x[2*i+1],
                            cfg.climate_mortality_scale, cfg.climate_friction_scale,
                            cfg.climate_plague_scale);
                        sum_f += cf.plague_factor;
                    }
                    avg_plague_factor = sum_f / static_cast<politeia::Real>(sample_n);
                }
                local_plague_params.trigger_rate *= avg_plague_factor;
            }
            if (cfg.river_enabled && cfg.river_plague_enabled &&
                !river_proximity_at_particle.empty()) {
                politeia::Real avg_river_prox = 0.0;
                const politeia::Index sample_n = std::min(
                    particles.count(), static_cast<politeia::Index>(100)
                );
                for (politeia::Index i = 0; i < sample_n; ++i) {
                    avg_river_prox += std::max(0.0, river_proximity_at_particle[i]);
                }
                if (sample_n > 0) {
                    avg_river_prox /= static_cast<politeia::Real>(sample_n);
                }
                const politeia::Real river_plague_factor =
                    1.0 + cfg.river_plague_strength * avg_river_prox;
                local_plague_params.trigger_rate *= river_plague_factor;
                local_plague_params.infection_rate *= river_plague_factor;
            }

            plague_mgr.resize(particles.count());
            plague_deaths = plague_mgr.update(
                particles, cells, local_plague_params, density_estimate, cfg.dt, pop_rng
            );
        }
        deaths += plague_deaths;
        total_deaths += deaths;
        interval_deaths += deaths;

        politeia::Real sim_time = step * cfg.dt;
        politeia::Index births = 0;
        if (cfg.reproduction_enabled) {
            births = politeia::attempt_reproduction(
                particles, cells, repro_params, sim_time, pop_rng,
                cached_density.data(), cached_K.data(),
                cfg.loyalty_enabled ? &loyalty_params : nullptr
            );
            interval_births += births;
        }
        perf.stop(politeia::PerfMonitor::Population);

        // 6b. Hierarchy dynamics: loyalty evolution, rebellion, taxation, conquest
        if (cfg.loyalty_enabled) {
            politeia::evolve_loyalty(particles, loyalty_params, cfg.dt, pop_rng);
            (void)politeia::process_loyalty_events(particles, cells, loyalty_params, pop_rng);
            politeia::apply_taxation(particles, loyalty_params, cfg.dt);
            if (cfg.hierarchy_assimilation_rate > 0.0) {
                politeia::apply_hierarchy_assimilation(particles, cfg.hierarchy_assimilation_rate, cfg.dt);
            }

            const politeia::Index hierarchy_repair_iv =
                (cfg.hierarchy_repair_interval > 0)
                    ? cfg.hierarchy_repair_interval
                    : cfg.compact_interval;

            if (step % hierarchy_repair_iv == 0) {
                politeia::Index n_repaired = politeia::repair_hierarchy_graph(
                    particles, loyalty_params.max_hierarchy_depth);
                if (rank == 0 && n_repaired > 0 && step % cfg.output_interval == 0) {
                    std::cout << "  [hierarchy] repaired " << n_repaired
                              << " superior links at step " << step << "\n";
                }
            }

            if (step % cfg.compact_interval == 0) {
                (void)politeia::form_attachments(particles, network, loyalty_params);
                auto power = politeia::compute_effective_power(particles);
                if (cfg.conquest_enabled) {
                    politeia::ConquestParams cparams;
                    cparams.power_ratio = cfg.conquest_power_ratio;
                    cparams.base_prob = cfg.conquest_base_prob;
                    cparams.initial_loyalty = cfg.conquest_initial_loyalty;
                    cparams.war_cost_enabled = cfg.war_cost_enabled;
                    cparams.war_cost_attacker = cfg.war_cost_attacker;
                    cparams.war_cost_defender = cfg.war_cost_defender;
                    cparams.war_casualties_enabled = cfg.war_casualties_enabled;
                    cparams.war_casualty_rate = cfg.war_casualty_rate;
                    cparams.pillage_enabled = cfg.pillage_enabled;
                    cparams.pillage_fraction = cfg.pillage_fraction;
                    cparams.deterrence_enabled = cfg.deterrence_enabled;
                    cparams.deterrence_ratio = cfg.deterrence_ratio;
                    politeia::Index n_conquest = politeia::attempt_conquest(particles, cells, power, cfg.interaction_range, pop_rng, cparams, loyalty_params.max_hierarchy_depth);
                    if (rank == 0 && n_conquest > 0) {
                        std::cout << "  [conquest] " << n_conquest << " conquests at step " << step << "\n";
                    }
                }
            }
        }

        // 7. MPI particle migration
        perf.start(politeia::PerfMonitor::Migration);
        domain.migrate_particles(particles);
        particles.rebuild_gid_map();
        perf.stop(politeia::PerfMonitor::Migration);

        ++steps_since_rebalance;

        // 8. Periodic compaction + SFC rebalance
        bool do_rebalance = (step % cfg.compact_interval == 0);

        // Auto-triggered rebalance: check load balance every compact_interval
        if (!do_rebalance && steps_since_rebalance >= MIN_REBALANCE_GAP
            && step % std::max(cfg.compact_interval / 4, politeia::Index(1)) == 0)
        {
            auto lr = perf.compute_load_report(
                particles.count(), REBALANCE_EFFICIENCY_THRESHOLD);
            if (lr.needs_rebalance) {
                do_rebalance = true;
                if (rank == 0) {
                    std::cout << "  [AUTO-REBALANCE] step " << step
                              << " eff=" << lr.efficiency * 100 << "%\n";
                }
            }
        }

        if (do_rebalance) {
            network.reset();
            network.resize(particles.count());
            if (total_deaths > 0) {
                // Process succession before compaction
                std::vector<politeia::Index> dead_indices;
                for (politeia::Index i = 0; i < particles.count(); ++i) {
                    if (particles.status(i) == politeia::ParticleStatus::Dead) {
                        dead_indices.push_back(i);
                    }
                }
                if (!dead_indices.empty()) {
                    (void)politeia::process_succession(particles, dead_indices, loyalty_params);
                }

                politeia::Index old_count = particles.count();
                std::vector<politeia::Index> old_to_new;
                particles.compact_with_map(old_to_new);
                politeia::repair_superior_after_compact(particles, old_to_new, old_count);
                total_deaths = 0;
            }
            auto keys = domain.compute_keys(particles);
            domain.rebalance(keys);
            domain.redistribute(particles);
            particles.rebuild_gid_map();
            domain.discover_neighbors(particles, cfg.interaction_range);
            steps_since_rebalance = 0;

            auto lstats = domain.compute_load_stats(particles.count());
            cached_global_N = lstats.global_total;
        }

        // 9. Analysis + Output
        perf.start(politeia::PerfMonitor::Analysis);
        bool do_output = (step % cfg.output_interval == 0);
        politeia::Real gini = 0;
        if (do_output && rank == 0) {
            gini = politeia::compute_gini(particles);
        }
        perf.stop(politeia::PerfMonitor::Analysis);

        perf.start(politeia::PerfMonitor::IO);

        // Gather all particles for snapshot (collective — all ranks must participate)
        bool do_snapshot = do_output;
        politeia::ParticleData global_snap(0, cfg.culture_dim);
        if (do_snapshot) {
            global_snap = politeia::gather_all_particles(particles, rank, nprocs);
        }

        // MPI: reduce energies across all ranks before writing
#ifdef POLITEIA_USE_MPI
        if (do_output && nprocs > 1) {
            double local_e[3] = {state.kinetic_energy, state.social_potential, state.terrain_potential};
            double global_e[3];
            MPI_Allreduce(local_e, global_e, 3, MPI_DOUBLE, MPI_SUM, MPI_COMM_WORLD);
            state.kinetic_energy = global_e[0];
            state.social_potential = global_e[1];
            state.terrain_potential = global_e[2];
        }
#endif

        if (do_output && rank == 0) {
            politeia::Real time = step * cfg.dt;
            (void)politeia::compute_wealth_stats(global_snap);

            writer.write_energy(step, time, state.kinetic_energy,
                                state.social_potential, state.terrain_potential,
                                state.total_energy());

            // Demographics: age distribution analysis
            politeia::Index alive_n = 0;
            politeia::Real frac_fertile_out = 0;
            {
                politeia::Real age_sum = 0;
                politeia::Index n_fertile = 0, n_children = 0, n_elderly = 0;
                std::vector<politeia::Real> ages;
                ages.reserve(global_snap.count());

                for (politeia::Index ii = 0; ii < global_snap.count(); ++ii) {
                    if (global_snap.status(ii) != politeia::ParticleStatus::Alive) continue;
                    politeia::Real a = global_snap.age(ii);
                    ages.push_back(a);
                    age_sum += a;
                    ++alive_n;
                    if (a >= 15.0 && a <= 45.0) ++n_fertile;
                    if (a < 15.0) ++n_children;
                    if (a > 60.0) ++n_elderly;
                }

                politeia::Real median_age = 0;
                if (!ages.empty()) {
                    std::sort(ages.begin(), ages.end());
                    median_age = ages[ages.size() / 2];
                }
                frac_fertile_out = alive_n > 0 ? static_cast<politeia::Real>(n_fertile) / alive_n : 0;

                politeia::CSVWriter::DemographicRecord dr;
                dr.step = step;
                dr.time = time;
                dr.N = alive_n;
                dr.births = interval_births;
                dr.deaths = interval_deaths;
                dr.mean_age = alive_n > 0 ? age_sum / alive_n : 0;
                dr.median_age = median_age;
                dr.frac_fertile = frac_fertile_out;
                dr.frac_children = alive_n > 0 ? static_cast<politeia::Real>(n_children) / alive_n : 0;
                dr.frac_elderly = alive_n > 0 ? static_cast<politeia::Real>(n_elderly) / alive_n : 0;
                dr.growth_rate = alive_n > 0 ? static_cast<politeia::Real>(interval_births) / alive_n
                                              - static_cast<politeia::Real>(interval_deaths) / alive_n : 0;
                writer.write_demographics(dr);

                interval_births = 0;
                interval_deaths = 0;
            }

            // Heavy analysis (hierarchy, polity detection, power Gini) is
            // dispatched to a background thread at network_window intervals,
            // allowing the main simulation loop to continue immediately.
            if (step % network_window == 0) {
                network.reset();
                network.resize(particles.count());

                politeia::AsyncAnalysisInput ai{
                    global_snap,   // deep copy (ParticleData copy ctor)
                    step, time, gini
                };
                async_analyzer.launch(std::move(ai), cfg.total_steps);

                std::cout << "  [" << step << "/" << cfg.total_steps
                          << "]  N=" << alive_n
                          << "  Gini=" << gini
                          << "  (async heavy analysis launched)\n";
            } else {
                if (cfg.snapshot_binary) {
                    writer.write_snapshot_binary(global_snap, step);
                } else {
                    writer.write_snapshot(global_snap, step);
                }
                std::cout << "Step " << step << "/" << cfg.total_steps
                          << "  N=" << alive_n
                          << "  Gini=" << gini
                          << "  (light output, full analysis at step "
                          << ((step / network_window + 1) * network_window)
                          << ")\n";
            }

            // Health diagnostics at every output_interval (not just heavy analysis)
            bool any_warn = false;
            if (gini > 0.85) {
                std::cerr << "  [WARN] Gini=" << gini
                          << " > 0.85 — extreme wealth inequality\n";
                any_warn = true;
            }
            double ke_ratio = state.kinetic_energy / std::max(1.0, alive_n * cfg.temperature);
            if (ke_ratio > 3.0 || ke_ratio < 0.2) {
                std::cerr << "  [WARN] KE/NkT=" << ke_ratio
                          << " — thermal equilibrium violation\n";
                any_warn = true;
            }
            if (std::abs(state.social_potential) > 1e12) {
                std::cerr << "  [WARN] V_social=" << state.social_potential
                          << " — potential energy may be divergent\n";
                any_warn = true;
            }
            if (frac_fertile_out < 0.2) {
                std::cerr << "  [WARN] fertile_fraction=" << frac_fertile_out
                          << " < 0.20 — population aging crisis\n";
                any_warn = true;
            }
            if (any_warn) {
                std::cerr << "  (See wiki/troubleshooting.md for diagnostic guidance)\n";
            }
        }

        // 10. Checkpoint writing (collective — all ranks participate)
        if (cfg.checkpoint_interval > 0 && step % cfg.checkpoint_interval == 0) {
            std::string ckpt_path = cfg.checkpoint_dir + "/checkpoint_step_"
                                  + std::to_string(step) + ".bin";
            politeia::write_checkpoint(ckpt_path, particles, cfg,
                                       cfg_path, step, rank, nprocs);
        }

        perf.stop(politeia::PerfMonitor::IO);

        perf.step_done();

        // Load balance report (all ranks participate in MPI_Allreduce)
        if (do_output) {
            auto lr = perf.compute_load_report(
                particles.count(), REBALANCE_EFFICIENCY_THRESHOLD);
            if (rank == 0) {
                std::cout << perf.format_report(lr) << "\n";
                std::cout << perf.format_breakdown() << "\n";
            }
        }
    }

    // Wait for any pending async analysis before cleanup
    async_analyzer.wait();

    // Write final checkpoint at end of simulation
    if (cfg.checkpoint_interval > 0) {
        std::string final_ckpt = cfg.checkpoint_dir + "/checkpoint_final_step_"
                               + std::to_string(cfg.total_steps) + ".bin";
        politeia::write_checkpoint(final_ckpt, particles, cfg,
                                   cfg_path, cfg.total_steps, rank, nprocs);
    }

    auto t_end = std::chrono::steady_clock::now();
    double elapsed = std::chrono::duration<double>(t_end - t_start).count();

    if (rank == 0) {
        writer.close();
        std::cout << "\nSimulation complete. Wall time: " << elapsed << " s\n";
    }

#ifdef POLITEIA_USE_MPI
    MPI_Finalize();
#endif
    return 0;
}
