#pragma once

#include "core/types.hpp"
#include "core/particle_data.hpp"
#include "domain/cell_list.hpp"

#include <random>

namespace politeia {

struct TechParams {
    // Slow drift: dε = α·|c⃗|·ε·dt (knowledge-driven improvement)
    Real drift_rate = 0.0001;

    // Contact spread: high-ε teaches low-ε neighbors
    Real spread_rate = 0.01;
    Real spread_range = 2.5;
    bool river_enabled = false;
    Real river_strength = 0.5;

    // Poisson jump: breakthrough discovery
    Real jump_base_rate = 1e-5;    // base probability per step
    Real jump_knowledge_scale = 1.0; // how much |c⃗| amplifies jump probability
    Real jump_magnitude = 0.5;      // size of ε jump

    // Wealth Poisson jumps (luck/misfortune)
    Real wealth_jump_rate_pos = 1e-4;  // probability of windfall per step
    Real wealth_jump_rate_neg = 1e-4;  // probability of loss per step
    Real wealth_jump_fraction = 0.3;   // fraction of wealth gained/lost
};

/// Evolve energy utilization ε through drift, contact spread, and Poisson jumps.
/// Also applies wealth Poisson jumps.
///
/// Research proposal §2.4:
///   dε = α·|c⃗|·ε·dt + [spread] + Δε·dN(t)
///
/// Returns: {number of ε breakthroughs, number of wealth jumps}
struct JumpStats {
    Index eps_jumps = 0;
    Index wealth_jumps_pos = 0;
    Index wealth_jumps_neg = 0;
};

[[nodiscard]] JumpStats evolve_technology(
    ParticleData& particles,
    const CellList& cells,
    const TechParams& params,
    Real dt,
    std::mt19937_64& rng,
    const Real* river_proximity_at_particle = nullptr
);

/// Compute mean ε of alive particles.
[[nodiscard]] Real compute_mean_epsilon(const ParticleData& particles);

} // namespace politeia
