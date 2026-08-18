#pragma once

#include "core/types.hpp"
#include "core/particle_data.hpp"
#include "domain/cell_list.hpp"

#include <vector>

namespace politeia {

struct CarryingCapacityParams {
    Real density_radius = 5.0;
    Real carrying_capacity_base = 50.0;
};

/// Compute local density ρ(x_i) for each alive particle using neighbor counting.
/// density_radius: the radius within which neighbors are counted.
/// Returns a vector of size particles.count() with density values.
[[nodiscard]] std::vector<Real> compute_local_density(
    const ParticleData& particles,
    const CellList& cells,
    Real density_radius
);

/// Compute local carrying capacity K(x_i) for each particle.
/// K(x) = carrying_capacity_base × max(0, −V(x))
/// terrain_potential_at_particle: precomputed V(x_i), length N.
/// Returns a vector of size particles.count().
[[nodiscard]] std::vector<Real> compute_carrying_capacity(
    const ParticleData& particles,
    Real carrying_capacity_base,
    const Real* terrain_potential_at_particle,
    const Real* river_proximity_at_particle = nullptr,
    bool river_capacity_enabled = false,
    Real river_capacity_strength = 0.0,
    Real river_capacity_beta = 1.0
);

/// Density suppression factor: max(0, 1 − ρ/K).
/// When ρ >= K, returns 0 (population at or above carrying capacity).
/// When K <= 0 (barren land), returns 0.
[[nodiscard]] inline Real density_suppression(Real local_density, Real local_K) {
    if (local_K <= 1e-15) return 0.0;
    return std::max(0.0, 1.0 - local_density / local_K);
}

} // namespace politeia
