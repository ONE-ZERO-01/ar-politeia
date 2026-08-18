#pragma once

#include "core/types.hpp"
#include <vector>

namespace politeia {

struct TerrainParams {
    // Gaussian well parameters: V(x,y) = -depth * exp(-((x-cx)^2+(y-cy)^2)/(2*width^2))
    // Multiple wells can simulate river valleys
    struct Well {
        Real cx, cy;
        Real depth;
        Real width;
    };

    std::vector<Well> wells;
};

/// Compute terrain forces from Gaussian potential wells.
/// Accumulates into force buffer. Returns total terrain potential energy.
[[nodiscard]] Real compute_terrain_forces(
    const Real* __restrict__ x_data,
    Real* __restrict__ force,
    Index count,
    const TerrainParams& params
);

/// Evaluate terrain potential at a point (for diagnostics).
[[nodiscard]] Real terrain_potential(Real x, Real y, const TerrainParams& params);

} // namespace politeia
