#include "core/config.hpp"

#include <fstream>
#include <sstream>
#include <stdexcept>
#include <iostream>

namespace politeia {

namespace {

std::string trim(const std::string& s) {
    auto start = s.find_first_not_of(" \t\r\n");
    if (start == std::string::npos) return "";
    auto end = s.find_last_not_of(" \t\r\n");
    return s.substr(start, end - start + 1);
}

bool parse_bool(const std::string& val) {
    return val == "true" || val == "1" || val == "yes";
}

bool apply_key_value(SimConfig& cfg, const std::string& key, const std::string& val) {
    // Domain
    if (key == "domain_xmin") cfg.domain_xmin = std::stod(val);
    else if (key == "domain_xmax") cfg.domain_xmax = std::stod(val);
    else if (key == "domain_ymin") cfg.domain_ymin = std::stod(val);
    else if (key == "domain_ymax") cfg.domain_ymax = std::stod(val);
    // Time stepping
    else if (key == "dt") cfg.dt = std::stod(val);
    else if (key == "total_steps") cfg.total_steps = std::stoull(val);
    else if (key == "output_interval") cfg.output_interval = std::stoull(val);
    else if (key == "compact_interval") cfg.compact_interval = std::stoull(val);
    // Particles
    else if (key == "initial_particles") cfg.initial_particles = std::stoull(val);
    else if (key == "initial_conditions_file") cfg.initial_conditions_file = val;
    else if (key == "init_jitter_factor") cfg.init_jitter_factor = std::stod(val);
    else if (key == "init_age_min") cfg.init_age_min = std::stod(val);
    else if (key == "init_age_max") cfg.init_age_max = std::stod(val);
    else if (key == "age_pyramid") cfg.age_pyramid = (val == "true" || val == "1");
    // Langevin
    else if (key == "temperature") cfg.temperature = std::stod(val);
    else if (key == "friction") cfg.friction = std::stod(val);
    // Social force
    else if (key == "social_strength") cfg.social_strength = std::stod(val);
    else if (key == "social_distance") cfg.social_distance = std::stod(val);
    else if (key == "interaction_range") cfg.interaction_range = std::stod(val);
    // Resources
    else if (key == "initial_wealth") cfg.initial_wealth = std::stod(val);
    else if (key == "survival_threshold") cfg.survival_threshold = std::stod(val);
    else if (key == "consumption_rate") cfg.consumption_rate = std::stod(val);
    else if (key == "wealth_decay_rate") cfg.wealth_decay_rate = std::stod(val);
    else if (key == "base_production") cfg.base_production = std::stod(val);
    // Culture vector
    else if (key == "culture_dim") cfg.culture_dim = std::stoi(val);
    // Resource exchange
    else if (key == "exchange_rate") cfg.exchange_rate = std::stod(val);
    else if (key == "exchange_cutoff") cfg.exchange_cutoff = std::stod(val);
    else if (key == "ability_saturation_w") cfg.ability_saturation_w = std::stod(val);
    else if (key == "exchange_noise_strength") cfg.exchange_noise_strength = std::stod(val);
    // Culture dynamics
    else if (key == "assimilation_rate") cfg.assimilation_rate = std::stod(val);
    else if (key == "repulsion_threshold") cfg.repulsion_threshold = std::stod(val);
    else if (key == "repulsion_strength") cfg.repulsion_strength = std::stod(val);
    else if (key == "attraction_strength") cfg.attraction_strength = std::stod(val);
    else if (key == "culture_mate_threshold") cfg.culture_mate_threshold = std::stod(val);
    // Technology evolution
    else if (key == "tech_drift_rate") cfg.tech_drift_rate = std::stod(val);
    else if (key == "tech_spread_rate") cfg.tech_spread_rate = std::stod(val);
    else if (key == "tech_jump_base_rate") cfg.tech_jump_base_rate = std::stod(val);
    else if (key == "tech_jump_knowledge_scale") cfg.tech_jump_knowledge_scale = std::stod(val);
    else if (key == "tech_jump_magnitude") cfg.tech_jump_magnitude = std::stod(val);
    else if (key == "wealth_jump_rate_pos") cfg.wealth_jump_rate_pos = std::stod(val);
    else if (key == "wealth_jump_rate_neg") cfg.wealth_jump_rate_neg = std::stod(val);
    else if (key == "wealth_jump_fraction") cfg.wealth_jump_fraction = std::stod(val);
    // Reproduction
    else if (key == "puberty_age") cfg.puberty_age = std::stod(val);
    else if (key == "menopause_age") cfg.menopause_age = std::stod(val);
    else if (key == "gestation_time") cfg.gestation_time = std::stod(val);
    else if (key == "nursing_time") cfg.nursing_time = std::stod(val);
    else if (key == "max_fertility") cfg.max_fertility = std::stod(val);
    else if (key == "peak_fertility_age") cfg.peak_fertility_age = std::stod(val);
    else if (key == "fertility_alpha") cfg.fertility_alpha = std::stod(val);
    else if (key == "mate_range") cfg.mate_range = std::stod(val);
    else if (key == "wealth_birth_cost") cfg.wealth_birth_cost = std::stod(val);
    else if (key == "min_wealth_to_breed") cfg.min_wealth_to_breed = std::stod(val);
    else if (key == "mutation_strength") cfg.mutation_strength = std::stod(val);
    else if (key == "culture_mutation_scale") cfg.culture_mutation_scale = std::stod(val);
    else if (key == "epsilon_mutation_scale") cfg.epsilon_mutation_scale = std::stod(val);
    // Carrying capacity
    else if (key == "carrying_capacity_base") cfg.carrying_capacity_base = std::stod(val);
    else if (key == "density_radius") cfg.density_radius = std::stod(val);
    // Mortality
    else if (key == "gompertz_alpha") cfg.gompertz_alpha = std::stod(val);
    else if (key == "gompertz_beta") cfg.gompertz_beta = std::stod(val);
    else if (key == "max_age") cfg.max_age = std::stod(val);
    else if (key == "accident_rate") cfg.accident_rate = std::stod(val);
    else if (key == "starvation_sigmoid_k") cfg.starvation_sigmoid_k = std::stod(val);
    // Lifespan coupling (26C)
    else if (key == "lifespan_wealth_enabled") cfg.lifespan_wealth_enabled = parse_bool(val);
    else if (key == "lifespan_wealth_k") cfg.lifespan_wealth_k = std::stod(val);
    else if (key == "lifespan_wealth_ref") cfg.lifespan_wealth_ref = std::stod(val);
    else if (key == "lifespan_wealth_beta_alpha") cfg.lifespan_wealth_beta_alpha = std::stod(val);
    else if (key == "lifespan_tech_enabled") cfg.lifespan_tech_enabled = parse_bool(val);
    else if (key == "lifespan_tech_k") cfg.lifespan_tech_k = std::stod(val);
    else if (key == "lifespan_tech_ref") cfg.lifespan_tech_ref = std::stod(val);
    else if (key == "lifespan_tech_beta_alpha") cfg.lifespan_tech_beta_alpha = std::stod(val);
    // Loyalty & hierarchy
    else if (key == "loyalty_protection_gain") cfg.loyalty_protection_gain = std::stod(val);
    else if (key == "loyalty_tax_drain") cfg.loyalty_tax_drain = std::stod(val);
    else if (key == "loyalty_culture_penalty") cfg.loyalty_culture_penalty = std::stod(val);
    else if (key == "loyalty_noise_sigma") cfg.loyalty_noise_sigma = std::stod(val);
    else if (key == "tax_rate") cfg.tax_rate = std::stod(val);
    else if (key == "tax_efficiency") cfg.tax_efficiency = std::stod(val);
    else if (key == "rebel_threshold") cfg.rebel_threshold = std::stod(val);
    else if (key == "switch_threshold") cfg.switch_threshold = std::stod(val);
    else if (key == "attachment_threshold") cfg.attachment_threshold = std::stod(val);
    else if (key == "initial_loyalty") cfg.initial_loyalty = std::stod(val);
    else if (key == "succession_loyalty_factor") cfg.succession_loyalty_factor = std::stod(val);
    else if (key == "succession_heir_loyalty_cap") cfg.succession_heir_loyalty_cap = std::stod(val);
    else if (key == "max_hierarchy_depth") cfg.max_hierarchy_depth = std::stoi(val);
    else if (key == "hierarchy_repair_interval") cfg.hierarchy_repair_interval = std::stoull(val);
    // Hierarchy cultural assimilation
    else if (key == "hierarchy_assimilation_rate") cfg.hierarchy_assimilation_rate = std::stod(val);

    // Conquest
    else if (key == "conquest_power_ratio") cfg.conquest_power_ratio = std::stod(val);
    else if (key == "conquest_base_prob") cfg.conquest_base_prob = std::stod(val);
    else if (key == "conquest_initial_loyalty") cfg.conquest_initial_loyalty = std::stod(val);
    // Plague
    else if (key == "n_pathogens") cfg.n_pathogens = std::stoi(val);
    else if (key == "plague_trigger_density") cfg.plague_trigger_density = std::stod(val);
    else if (key == "plague_trigger_rate") cfg.plague_trigger_rate = std::stod(val);
    else if (key == "plague_infection_radius") cfg.plague_infection_radius = std::stod(val);
    else if (key == "plague_infection_rate") cfg.plague_infection_rate = std::stod(val);
    else if (key == "plague_base_mortality") cfg.plague_base_mortality = std::stod(val);
    else if (key == "plague_recovery_time") cfg.plague_recovery_time = std::stod(val);
    else if (key == "plague_immunity_inheritance") cfg.plague_immunity_inheritance = std::stod(val);
    // Gender & mating (26D)
    else if (key == "gender_enabled") cfg.gender_enabled = parse_bool(val);
    else if (key == "sex_ratio") cfg.sex_ratio = std::stod(val);
    else if (key == "male_cooldown") cfg.male_cooldown = std::stod(val);
    else if (key == "max_partners_per_cooldown") cfg.max_partners_per_cooldown = std::stoi(val);
    else if (key == "partner_wealth_factor") cfg.partner_wealth_factor = std::stod(val);
    else if (key == "inheritance_model") cfg.inheritance_model = val;
    else if (key == "epsilon_patrilineal_threshold") cfg.epsilon_patrilineal_threshold = std::stod(val);
    else if (key == "culture_dominant_weight") cfg.culture_dominant_weight = std::stod(val);
    // War enhancement (26E)
    else if (key == "war_cost_enabled") cfg.war_cost_enabled = parse_bool(val);
    else if (key == "war_cost_attacker") cfg.war_cost_attacker = std::stod(val);
    else if (key == "war_cost_defender") cfg.war_cost_defender = std::stod(val);
    else if (key == "war_casualties_enabled") cfg.war_casualties_enabled = parse_bool(val);
    else if (key == "war_casualty_rate") cfg.war_casualty_rate = std::stod(val);
    else if (key == "pillage_enabled") cfg.pillage_enabled = parse_bool(val);
    else if (key == "pillage_fraction") cfg.pillage_fraction = std::stod(val);
    else if (key == "deterrence_enabled") cfg.deterrence_enabled = parse_bool(val);
    else if (key == "deterrence_ratio") cfg.deterrence_ratio = std::stod(val);
    // Control
    else if (key == "random_seed") cfg.random_seed = std::stoi(val);
    else if (key == "network_window_factor") cfg.network_window_factor = std::stoi(val);
    else if (key == "density_update_interval") cfg.density_update_interval = std::stoull(val);
    // Module switches
    else if (key == "culture_enabled") cfg.culture_enabled = parse_bool(val);
    else if (key == "technology_enabled") cfg.technology_enabled = parse_bool(val);
    else if (key == "loyalty_enabled") cfg.loyalty_enabled = parse_bool(val);
    else if (key == "conquest_enabled") cfg.conquest_enabled = parse_bool(val);
    else if (key == "plague_enabled") cfg.plague_enabled = parse_bool(val);
    else if (key == "carrying_capacity_enabled") cfg.carrying_capacity_enabled = parse_bool(val);
    else if (key == "reproduction_enabled") cfg.reproduction_enabled = parse_bool(val);
    else if (key == "mortality_enabled") cfg.mortality_enabled = parse_bool(val);
    // Terrain
    else if (key == "terrain_file") cfg.terrain_file = val;
    else if (key == "terrain_format") cfg.terrain_format = val;
    else if (key == "terrain_scale") {
        cfg.terrain_scale = std::stod(val);
        cfg.terrain_force_scale = cfg.terrain_scale;
        cfg.terrain_production_scale = cfg.terrain_scale;
    }
    else if (key == "terrain_force_enabled") cfg.terrain_force_enabled = parse_bool(val);
    else if (key == "terrain_force_scale") cfg.terrain_force_scale = std::stod(val);
    else if (key == "terrain_production_enabled") cfg.terrain_production_enabled = parse_bool(val);
    else if (key == "terrain_production_scale") cfg.terrain_production_scale = std::stod(val);
    else if (key == "terrain_type") cfg.terrain_type = val;
    else if (key == "terrain_grid_rows") cfg.terrain_grid_rows = std::stoi(val);
    else if (key == "terrain_grid_cols") cfg.terrain_grid_cols = std::stoi(val);
    else if (key == "terrain_barrier_enabled") cfg.terrain_barrier_enabled = parse_bool(val);
    else if (key == "terrain_barrier_scale") cfg.terrain_barrier_scale = std::stod(val);
    // Climate
    else if (key == "climate_enabled") cfg.climate_enabled = parse_bool(val);
    else if (key == "climate_file") cfg.climate_file = val;
    else if (key == "climate_mode") cfg.climate_mode = val;
    else if (key == "climate_time_mode") cfg.climate_time_mode = val;
    else if (key == "climate_drift_rate") cfg.climate_drift_rate = std::stod(val);
    else if (key == "climate_drift_schedule") cfg.climate_drift_schedule = val;
    else if (key == "climate_season_amplitude") cfg.climate_season_amplitude = std::stod(val);
    else if (key == "climate_season_period") cfg.climate_season_period = std::stod(val);
    else if (key == "climate_update_interval") cfg.climate_update_interval = std::stoi(val);
    else if (key == "climate_production_enabled") cfg.climate_production_enabled = parse_bool(val);
    else if (key == "climate_carrying_enabled") cfg.climate_carrying_enabled = parse_bool(val);
    else if (key == "climate_mortality_enabled") cfg.climate_mortality_enabled = parse_bool(val);
    else if (key == "climate_mortality_scale") cfg.climate_mortality_scale = std::stod(val);
    else if (key == "climate_friction_enabled") cfg.climate_friction_enabled = parse_bool(val);
    else if (key == "climate_friction_scale") cfg.climate_friction_scale = std::stod(val);
    else if (key == "climate_plague_enabled") cfg.climate_plague_enabled = parse_bool(val);
    else if (key == "climate_plague_scale") cfg.climate_plague_scale = std::stod(val);
    // River
    else if (key == "river_enabled") cfg.river_enabled = parse_bool(val);
    else if (key == "river_file") cfg.river_file = val;
    else if (key == "river_format") cfg.river_format = val;
    else if (key == "river_mode") cfg.river_mode = val;
    else if (key == "river_grid_rows") cfg.river_grid_rows = std::stoi(val);
    else if (key == "river_grid_cols") cfg.river_grid_cols = std::stoi(val);
    else if (key == "river_type") cfg.river_type = val;
    else if (key == "river_resource_enabled") cfg.river_resource_enabled = parse_bool(val);
    else if (key == "river_resource_strength") cfg.river_resource_strength = std::stod(val);
    else if (key == "river_resource_alpha") cfg.river_resource_alpha = std::stod(val);
    else if (key == "river_capacity_enabled") cfg.river_capacity_enabled = parse_bool(val);
    else if (key == "river_capacity_strength") cfg.river_capacity_strength = std::stod(val);
    else if (key == "river_capacity_beta") cfg.river_capacity_beta = std::stod(val);
    else if (key == "river_exchange_enabled") cfg.river_exchange_enabled = parse_bool(val);
    else if (key == "river_exchange_strength") cfg.river_exchange_strength = std::stod(val);
    else if (key == "river_tech_enabled") cfg.river_tech_enabled = parse_bool(val);
    else if (key == "river_tech_strength") cfg.river_tech_strength = std::stod(val);
    else if (key == "river_plague_enabled") cfg.river_plague_enabled = parse_bool(val);
    else if (key == "river_plague_strength") cfg.river_plague_strength = std::stod(val);
    else if (key == "river_force_enabled") cfg.river_force_enabled = parse_bool(val);
    else if (key == "river_force_scale") cfg.river_force_scale = std::stod(val);
    // Output
    else if (key == "output_dir") cfg.output_dir = val;
    else if (key == "snapshot_binary") cfg.snapshot_binary = (val == "true" || val == "1");
    // Checkpoint / Restart
    else if (key == "checkpoint_interval") cfg.checkpoint_interval = std::stoull(val);
    else if (key == "checkpoint_dir") cfg.checkpoint_dir = val;
    else if (key == "restart_file") cfg.restart_file = val;
    // MPI
    else if (key == "mpi_px") cfg.mpi_px = std::stoi(val);
    else if (key == "mpi_py") cfg.mpi_py = std::stoi(val);
    else return false;
    return true;
}

} // namespace

SimConfig load_config(const std::string& filepath) {
    SimConfig cfg;
    std::ifstream file(filepath);
    if (!file.is_open()) {
        throw std::runtime_error("Cannot open config file: " + filepath);
    }

    std::string line;
    int lineno = 0;
    int unknown_count = 0;
    while (std::getline(file, line)) {
        ++lineno;
        line = trim(line);
        if (line.empty() || line[0] == '#') continue;

        auto eq_pos = line.find('=');
        if (eq_pos == std::string::npos) {
            std::cerr << "Warning: ignoring malformed line " << lineno
                      << ": " << line << "\n";
            continue;
        }

        auto key = trim(line.substr(0, eq_pos));
        auto val = trim(line.substr(eq_pos + 1));
        try {
            if (!apply_key_value(cfg, key, val)) {
                std::cerr << "Warning: unknown config key '" << key
                          << "' at line " << lineno << " (ignored)\n";
                ++unknown_count;
            }
        } catch (const std::exception& e) {
            std::cerr << "Error parsing config key '" << key << "' = '" << val
                      << "' at line " << lineno << ": " << e.what() << "\n";
            throw;
        }
    }
    if (unknown_count > 0) {
        std::cerr << "Config: " << unknown_count << " unknown key(s) ignored. "
                  << "Check for typos.\n";
    }
    return cfg;
}

SimConfig default_config() {
    return SimConfig{};
}

} // namespace politeia
