#pragma once

#include "core/types.hpp"
#include "core/particle_data.hpp"
#include "domain/cell_list.hpp"

#include "interaction/culture_dynamics.hpp"
#include "interaction/loyalty.hpp"
#include <random>
#include <string>

namespace politeia {

struct ReproductionParams {
    Real puberty_age = 15.0;
    Real menopause_age = 45.0;
    Real peak_fertility_age = 25.0;
    Real max_fertility = 5e-4;
    Real gestation_time = 0.75;
    Real nursing_time = 1.5;
    Real mate_range = 3.0;
    Real wealth_birth_cost = 0.3;
    Real min_wealth_to_breed = 0.5;
    Real mutation_strength = 0.1;
    Real culture_mutation_scale = 0.2;
    Real epsilon_mutation_scale = 0.01;
    Real fertility_alpha = 2.0;
    Real culture_mate_threshold = 2.0;

    // Gender & mating (26D)
    bool gender_enabled = false;
    Real sex_ratio = 0.5;
    Real male_cooldown = 0.1;
    int max_partners_per_cooldown = 0;
    Real partner_wealth_factor = 2.0;
    std::string inheritance_model = "contribution";
    Real epsilon_patrilineal_threshold = 3.0;
    Real culture_dominant_weight = 0.7;
};

/// Fertility function φ(a): bell-shaped curve over [puberty, menopause].
/// Returns value in [0, max_fertility].
[[nodiscard]] Real fertility(Real age, const ReproductionParams& params);

/// Attempt reproduction for all eligible pairs.
/// Modifies particles in-place (adds new particles, modifies parent wealth).
/// local_density/local_K: optional density suppression arrays (size N).
///   When provided, fertility is scaled by max(0, 1 − ρ/K).
/// Returns number of births.
[[nodiscard]] Index attempt_reproduction(
    ParticleData& particles,
    const CellList& cells,
    const ReproductionParams& params,
    Real current_time,
    std::mt19937_64& rng,
    const Real* local_density = nullptr,
    const Real* local_K = nullptr,
    const LoyaltyParams* loyalty_params = nullptr
);

} // namespace politeia
