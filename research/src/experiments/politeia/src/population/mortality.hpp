#pragma once

#include "core/types.hpp"
#include "core/particle_data.hpp"

#include <random>

namespace politeia {

struct MortalityParams {
    Real gompertz_alpha = 1e-4;   // baseline hazard rate
    Real gompertz_beta = 0.085;   // aging acceleration (β₀)
    Real max_age = 80.0;          // hard age limit (a_base)
    Real accident_rate = 1e-4;    // random death probability per step
    Real survival_threshold = 0.1;
    Real starvation_sigmoid_k = 10.0; // steepness of wealth→starvation sigmoid

    // Lifespan coupling: per-particle Gompertz parameters derived from w_i and ε
    // a_max(i) = max_age + k_w·min(w/w_ref, 1) + k_ε·log(1 + ε/ε_ref)
    // β_eff(i) = β₀ / (1 + α_w·w/w_ref + α_ε·ε/ε_ref)
    bool lifespan_wealth_enabled = false;
    Real lifespan_wealth_k = 20.0;
    Real lifespan_wealth_ref = 10.0;
    Real lifespan_wealth_beta_alpha = 0.3;
    bool lifespan_tech_enabled = false;
    Real lifespan_tech_k = 15.0;
    Real lifespan_tech_ref = 2.0;
    Real lifespan_tech_beta_alpha = 0.5;
};

/// Compute effective max age for a particle given its wealth and epsilon.
[[nodiscard]] Real effective_max_age(Real base_max_age, Real wealth, Real epsilon,
                                     const MortalityParams& params);

/// Compute effective Gompertz beta for a particle given its wealth and epsilon.
[[nodiscard]] Real effective_gompertz_beta(Real base_beta, Real wealth, Real epsilon,
                                           const MortalityParams& params);

/// Apply four-fold mortality: aging (Gompertz) + starvation + accident + plague (reserved).
/// Returns number of deaths.
[[nodiscard]] Index apply_mortality(
    ParticleData& particles,
    const MortalityParams& params,
    Real dt,
    std::mt19937_64& rng
);

/// Advance age of all alive particles by dt.
/// Also applies productivity bell curve to effective wealth generation.
void advance_age(ParticleData& particles, Real dt);

/// Productivity modifier based on age: bell curve peaking at prime age.
/// Returns value in [0, 1].
[[nodiscard]] Real productivity_factor(Real age);

} // namespace politeia
