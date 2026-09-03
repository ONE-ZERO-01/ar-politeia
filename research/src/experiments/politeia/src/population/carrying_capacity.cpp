#include "population/carrying_capacity.hpp"

#include <cmath>

#ifdef POLITEIA_USE_OPENMP
#include <omp.h>
#endif

namespace politeia {

std::vector<Real> compute_local_density(
    const ParticleData& particles,
    const CellList& cells,
    Real density_radius
) {
    const Index n = particles.count();
    const Real* __restrict__ x = particles.x_data();
    if (n == 0 || density_radius <= 0.0) {
        return std::vector<Real>(n, 0.0);
    }
    const Real cutoff_sq = density_radius * density_radius;
    const Real area = M_PI * cutoff_sq;

    std::vector<Real> density(n, 0.0);

    #pragma omp parallel for schedule(dynamic, 64) if(n > 256)
    for (Index i = 0; i < n; ++i) {
        if (particles.status(i) != ParticleStatus::Alive) continue;

        Index count = 0;
        cells.for_neighbors_of(i, x, n, cutoff_sq,
            [&](Index j, Real, Real, Real) {
                if (particles.status(j) == ParticleStatus::Alive) {
                    ++count;
                }
            }
        );
        density[i] = static_cast<Real>(count + 1) / area;  // +1 for self
    }

    return density;
}

std::vector<Real> compute_carrying_capacity(
    const ParticleData& particles,
    Real carrying_capacity_base,
    const Real* terrain_potential_at_particle,
    const Real* river_proximity_at_particle,
    bool river_capacity_enabled,
    Real river_capacity_strength,
    Real river_capacity_beta
) {
    const Index n = particles.count();
    std::vector<Real> K(n, 0.0);

    // Normalize terrain potential so that K ∈ [0, carrying_capacity_base].
    // Without normalization, K = base × |V| where |V| can be ~100+,
    // making density suppression ineffective (K >> local_density).
    Real max_neg_V = 0.0;
    if (terrain_potential_at_particle != nullptr) {
        for (Index i = 0; i < n; ++i) {
            if (terrain_potential_at_particle[i] < 0) {
                Real neg_v = -terrain_potential_at_particle[i];
                if (neg_v > max_neg_V) max_neg_V = neg_v;
            }
        }
    }
    if (max_neg_V < 1e-15) max_neg_V = 1.0;

    #pragma omp parallel for schedule(static) if(n > 256)
    for (Index i = 0; i < n; ++i) {
        if (terrain_potential_at_particle != nullptr) {
            Real quality = std::max(0.0, -terrain_potential_at_particle[i]) / max_neg_V;
            K[i] = carrying_capacity_base * quality;
        }
        if (river_capacity_enabled && river_proximity_at_particle != nullptr && K[i] > 0.0) {
            const Real prox = std::max(0.0, river_proximity_at_particle[i]);
            K[i] *= 1.0 + river_capacity_strength * std::pow(prox, river_capacity_beta);
        }
    }

    return K;
}

} // namespace politeia
