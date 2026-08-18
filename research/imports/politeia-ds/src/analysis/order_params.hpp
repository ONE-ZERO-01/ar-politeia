#pragma once

#include "core/types.hpp"
#include "core/particle_data.hpp"

#include <vector>

namespace politeia {

/// Compute Gini coefficient of wealth distribution.
/// G=0: perfect equality, G=1: perfect inequality.
[[nodiscard]] Real compute_gini(const ParticleData& particles);

/// Compute wealth distribution histogram.
/// Returns bin counts for [0, max_wealth] divided into n_bins.
[[nodiscard]] std::vector<Index> compute_wealth_histogram(
    const ParticleData& particles,
    int n_bins,
    Real max_wealth
);

/// Basic statistics of wealth.
struct WealthStats {
    Real mean = 0.0;
    Real median = 0.0;
    Real stddev = 0.0;
    Real min_val = 0.0;
    Real max_val = 0.0;
    Real total = 0.0;
};

[[nodiscard]] WealthStats compute_wealth_stats(const ParticleData& particles);

} // namespace politeia
