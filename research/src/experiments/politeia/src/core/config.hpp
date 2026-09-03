#pragma once

#include "types.hpp"
#include "constants.hpp"
#include <string>

namespace politeia {

struct SimConfig {
    // Domain
    Real domain_xmin = 0.0;
    Real domain_xmax = 100.0;
    Real domain_ymin = 0.0;
    Real domain_ymax = 100.0;

    // Time stepping
    Real dt = constants::DEFAULT_DT;
    Index total_steps = 10000;
    Index output_interval = 100;
    Index compact_interval = 1000;

    // Particles
    Index initial_particles = 1000;
    std::string initial_conditions_file = "";  // CSV file for explicit initial conditions
    Real init_jitter_factor = 0.15;   // grid placement jitter σ = factor × min(dx,dy)
    Real init_age_min = 15.0;         // initial age range lower bound
    Real init_age_max = 40.0;         // initial age range upper bound
    bool age_pyramid = false;         // if true, redistribute ages to a realistic pyramid (0-70)

    // Langevin
    Real temperature = constants::DEFAULT_TEMPERATURE;
    Real friction = constants::DEFAULT_FRICTION;

    // Social force
    Real social_strength = constants::DEFAULT_SOCIAL_STRENGTH;
    Real social_distance = constants::DEFAULT_SOCIAL_DISTANCE;
    Real interaction_range = constants::DEFAULT_INTERACTION_RANGE;

    // Resources
    Real initial_wealth = constants::DEFAULT_INITIAL_WEALTH;
    Real survival_threshold = constants::DEFAULT_SURVIVAL_THRESHOLD;
    Real consumption_rate = constants::DEFAULT_CONSUMPTION_RATE;
    Real wealth_decay_rate = 0.02;  // proportional wealth decay (asset depreciation)
    Real base_production = 0.5;

    // Cultural vector
    int culture_dim = constants::DEFAULT_CULTURE_DIM;

    // Resource exchange
    Real exchange_rate = 0.003;
    Real exchange_cutoff = -1.0;  // <0 → use interaction_range
    Real ability_saturation_w = 5.0; // wealth half-saturation for exchange ability
    Real exchange_noise_strength = 0.0; // η_n: antisymmetric zero-sum fluctuation intensity (continuous-time)
    Real exchange_reversion_rate = 1.0; // k: mean-reversion rate of share toward 1/2 (continuous-time)

    // Culture dynamics
    Real assimilation_rate = 0.01;
    Real repulsion_threshold = 1.5;
    Real repulsion_strength = 0.5;
    Real attraction_strength = 1.0;
    Real culture_mate_threshold = 2.0;

    // Technology evolution
    Real tech_drift_rate = 0.0001;
    Real tech_spread_rate = 0.01;
    Real tech_jump_base_rate = 1e-5;
    Real tech_jump_knowledge_scale = 1.0;
    Real tech_jump_magnitude = 0.5;
    Real wealth_jump_rate_pos = 1e-4;
    Real wealth_jump_rate_neg = 1e-4;
    Real wealth_jump_fraction = 0.3;

    // Reproduction
    Real puberty_age = constants::DEFAULT_PUBERTY_AGE;
    Real menopause_age = constants::DEFAULT_MENOPAUSE_AGE;
    Real gestation_time = constants::DEFAULT_GESTATION_TIME;
    Real nursing_time = constants::DEFAULT_NURSING_TIME;
    Real max_fertility = 5e-4;
    Real peak_fertility_age = 25.0;
    Real fertility_alpha = 2.0;       // Beta-curve shape parameter for fertility φ(a)
    Real mate_range = -1.0;           // <0 → use interaction_range
    Real wealth_birth_cost = 0.3;
    Real min_wealth_to_breed = 0.5;
    Real mutation_strength = 0.1;
    Real culture_mutation_scale = 0.2; // offspring culture variation multiplier
    Real epsilon_mutation_scale = 0.01; // offspring ε variation multiplier

    // Carrying capacity
    Real carrying_capacity_base = 50.0;
    Real density_radius = 5.0;

    // Mortality
    Real gompertz_alpha = 1e-4;
    Real gompertz_beta = constants::DEFAULT_GOMPERTZ_BETA;
    Real max_age = 80.0;
    Real accident_rate = constants::DEFAULT_ACCIDENT_RATE;
    Real starvation_sigmoid_k = 10.0;  // steepness of hunger→death sigmoid

    // Lifespan coupling (26C): lifespan as derived quantity λ_i = h(w_i, ε_local)
    bool lifespan_wealth_enabled = false;
    Real lifespan_wealth_k = 20.0;       // k_w: max age bonus from wealth
    Real lifespan_wealth_ref = 10.0;     // w_ref: wealth reference scale
    Real lifespan_wealth_beta_alpha = 0.3; // α_w: Gompertz β reduction from wealth
    bool lifespan_tech_enabled = false;
    Real lifespan_tech_k = 15.0;         // k_ε: max age bonus from technology
    Real lifespan_tech_ref = 2.0;        // ε_ref: technology reference scale
    Real lifespan_tech_beta_alpha = 0.5; // α_ε: Gompertz β reduction from technology

    // Loyalty & hierarchy
    Real loyalty_protection_gain = 0.03;
    Real loyalty_tax_drain = 0.1;
    Real loyalty_culture_penalty = 0.02;
    Real loyalty_noise_sigma = 0.01;
    Real tax_rate = 0.05;
    Real tax_efficiency = 0.5;
    Real rebel_threshold = 0.1;
    Real switch_threshold = 0.2;
    Real attachment_threshold = 0.05;
    Real initial_loyalty = 0.5;
    Real succession_loyalty_factor = 0.85; // subordinate loyalty retention on leader death
    Real succession_heir_loyalty_cap = 0.8; // heir loyalty cap to inherited superior
    int max_hierarchy_depth = 10; // max allowed hierarchy chain depth
    /// Steps between hierarchy repair passes; 0 = same as compact_interval.
    Index hierarchy_repair_interval = 0;

    // Hierarchy cultural assimilation
    Real hierarchy_assimilation_rate = 0.3;

    // Conquest
    Real conquest_power_ratio = 1.5;
    Real conquest_base_prob = 0.02;
    Real conquest_initial_loyalty = 0.3;

    // Plague
    int n_pathogens = 4;
    Real plague_trigger_density = 50.0;
    Real plague_trigger_rate = 1e-5;
    Real plague_infection_radius = 3.0;
    Real plague_infection_rate = 0.3;
    Real plague_base_mortality = 0.5;
    Real plague_recovery_time = 5.0;
    Real plague_immunity_inheritance = 0.5;

    // Gender & mating (26D)
    bool gender_enabled = false;
    Real sex_ratio = 0.5;
    Real male_cooldown = 0.1;
    int max_partners_per_cooldown = 0;
    Real partner_wealth_factor = 2.0;
    std::string inheritance_model = "contribution";
    Real epsilon_patrilineal_threshold = 3.0;
    Real culture_dominant_weight = 0.7;

    // War enhancement (26E)
    bool war_cost_enabled = false;
    Real war_cost_attacker = 0.1;
    Real war_cost_defender = 0.2;
    bool war_casualties_enabled = false;
    Real war_casualty_rate = 0.05;
    bool pillage_enabled = false;
    Real pillage_fraction = 0.3;
    bool deterrence_enabled = false;
    Real deterrence_ratio = 3.0;

    // Control
    int random_seed = 42;
    int network_window_factor = 10;
    Index density_update_interval = 10;

    // Module switches (for ablation experiments)
    bool culture_enabled = true;
    bool technology_enabled = true;
    bool loyalty_enabled = true;
    bool conquest_enabled = true;
    bool plague_enabled = true;
    bool carrying_capacity_enabled = true;
    bool reproduction_enabled = true;
    bool mortality_enabled = true;

    // Terrain
    std::string terrain_file = "";
    std::string terrain_format = "auto";
    Real terrain_scale = 1.0;  // legacy alias: setting it updates both scales below
    bool terrain_force_enabled = true;
    Real terrain_force_scale = 1.0;
    bool terrain_production_enabled = true;
    Real terrain_production_scale = 1.0;
    std::string terrain_type = "gaussian";
    int terrain_grid_rows = 0;
    int terrain_grid_cols = 0;
    bool terrain_barrier_enabled = false;
    Real terrain_barrier_scale = 5.0;

    // Climate
    bool climate_enabled = false;
    std::string climate_file;
    std::string climate_mode = "procedural";    // "file" | "procedural"
    std::string climate_time_mode = "static";   // "static" | "drift" | "seasonal"
    Real climate_drift_rate = 0.0;
    std::string climate_drift_schedule;         // piecewise linear: "step:delta_T, ..."
    Real climate_season_amplitude = 5.0;
    Real climate_season_period = 365.0;
    int  climate_update_interval = 100;

    bool climate_production_enabled = true;
    bool climate_carrying_enabled = true;
    bool climate_mortality_enabled = true;
    Real climate_mortality_scale = 1e-4;
    bool climate_friction_enabled = true;
    Real climate_friction_scale = 0.5;
    bool climate_plague_enabled = true;
    Real climate_plague_scale = 2.0;

    // River field
    bool river_enabled = false;
    std::string river_file = "";
    std::string river_format = "auto";
    std::string river_mode = "procedural";  // "procedural" | "file"
    int river_grid_rows = 0;
    int river_grid_cols = 0;
    std::string river_type = "major_rivers";

    bool river_resource_enabled = true;
    Real river_resource_strength = 1.0;
    Real river_resource_alpha = 1.0;

    bool river_capacity_enabled = true;
    Real river_capacity_strength = 1.0;
    Real river_capacity_beta = 1.0;

    bool river_exchange_enabled = true;
    Real river_exchange_strength = 0.5;

    bool river_tech_enabled = true;
    Real river_tech_strength = 0.5;

    bool river_plague_enabled = false;
    Real river_plague_strength = 0.3;

    bool river_force_enabled = false;
    Real river_force_scale = 0.1;

    // Output
    std::string output_dir = "output";
    bool snapshot_binary = false;         // write .bin instead of .csv snapshots

    // Checkpoint / Restart
    Index checkpoint_interval = 0;          // write checkpoint every N steps (0 = disabled)
    std::string checkpoint_dir = "checkpoints";
    std::string restart_file = "";          // path to checkpoint file for restart

    // MPI
    int mpi_px = 1;
    int mpi_py = 1;
};

/// Load config from a simple key=value file. Unrecognized keys are ignored.
[[nodiscard]] SimConfig load_config(const std::string& filepath);

/// Load config with all defaults.
[[nodiscard]] SimConfig default_config();

} // namespace politeia
