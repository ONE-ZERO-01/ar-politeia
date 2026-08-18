#pragma once

#include "core/types.hpp"
#include "core/particle_data.hpp"
#include "domain/cell_list.hpp"

namespace politeia {

struct CultureParams {
    Real assimilation_rate = 0.01;  // rate of cultural convergence per interaction
    Real interaction_range = 2.5;   // 文化交互距离
    Real repulsion_threshold = 1.5; // cultural distance beyond which repulsion kicks in
    Real repulsion_strength = 0.5;  // strength of cultural repulsion force
    Real attraction_strength = 1.0; // strength of cultural attraction force
    Real culture_mate_threshold = 2.0; // max cultural distance for mating
};

/// Apply cultural dynamics: assimilation between nearby individuals.
/// Nearby individuals with similar culture converge; dissimilar ones don't.
/// This is a diffusion process on the culture vector space.
void evolve_culture(
    ParticleData& particles,
    const CellList& cells,
    const CultureParams& params,
    Real dt
);

/// Compute cultural distance between two particles.
[[nodiscard]] Real culture_distance(
    const ParticleData& particles, Index i, Index j
);

/// Compute culture-dependent interaction force modifier.
/// Returns a multiplier in [-1, 1]: positive = attraction, negative = repulsion.
/// 用于基于文化相似度调制人际空间交互力的强度。
[[nodiscard]] Real culture_force_modifier(
    Real culture_dist,
    const CultureParams& params
);

/// Compute global cultural order parameter Q(t).
/// Q = |<ĉ_i>|: average of normalized culture vectors.
/// Q ≈ 0: high diversity, Q ≈ 1: cultural uniformity.
[[nodiscard]] Real compute_culture_order_param(const ParticleData& particles);

/// Hierarchy-driven cultural assimilation: subordinates drift toward
/// their superior's culture at a rate proportional to loyalty.
///   c⃗_i += rate × L_ij × (c⃗_superior − c⃗_i) × dt
/// This stabilizes empires by reducing the culture_penalty term in loyalty evolution.
void apply_hierarchy_assimilation(
    ParticleData& particles,
    Real assimilation_rate,
    Real dt
);

/// Compute spatial culture correlation function.
/// Returns correlation values for distance bins [0, max_r).
[[nodiscard]] std::vector<Real> compute_culture_correlation(
    const ParticleData& particles,
    int n_bins,
    Real max_r
);

} // namespace politeia
