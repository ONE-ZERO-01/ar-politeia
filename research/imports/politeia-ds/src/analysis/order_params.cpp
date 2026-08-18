#include "analysis/order_params.hpp"

#include <algorithm>
#include <cmath>
#include <numeric>

namespace politeia {

Real compute_gini(const ParticleData& particles) {
    const Index n = particles.count();
    if (n <= 1) return 0.0;

    // Collect positive wealths
    std::vector<Real> w;
    w.reserve(n);
    for (Index i = 0; i < n; ++i) {
        if (particles.status(i) == ParticleStatus::Alive) {
            w.push_back(std::max(0.0, particles.wealth(i)));
        }
    }

    if (w.empty()) return 0.0;

    std::sort(w.begin(), w.end());
    const auto m = static_cast<Real>(w.size());
    const Real total = std::accumulate(w.begin(), w.end(), 0.0);

    if (total < 1e-15) return 0.0;

    // Gini = (2 * Σ_i (i+1)*w_i) / (m * Σ w_i) - (m+1)/m
    Real weighted_sum = 0.0;
    for (std::size_t i = 0; i < w.size(); ++i) {
        weighted_sum += static_cast<Real>(i + 1) * w[i];
    }

    return (2.0 * weighted_sum) / (m * total) - (m + 1.0) / m;
}

std::vector<Index> compute_wealth_histogram(
    const ParticleData& particles,
    int n_bins,
    Real max_wealth
) {
    std::vector<Index> bins(n_bins, 0);
    const Real bin_width = max_wealth / n_bins;
    const Index n = particles.count();

    for (Index i = 0; i < n; ++i) {
        if (particles.status(i) != ParticleStatus::Alive) continue;
        Real w = std::max(0.0, particles.wealth(i));
        int bin = static_cast<int>(w / bin_width);
        if (bin >= n_bins) bin = n_bins - 1;
        bins[bin]++;
    }

    return bins;
}

WealthStats compute_wealth_stats(const ParticleData& particles) {
    const Index n = particles.count();
    WealthStats stats;

    std::vector<Real> w;
    w.reserve(n);
    for (Index i = 0; i < n; ++i) {
        if (particles.status(i) == ParticleStatus::Alive) {
            w.push_back(particles.wealth(i));
        }
    }

    if (w.empty()) return stats;

    std::sort(w.begin(), w.end());
    const auto m = w.size();

    stats.total = std::accumulate(w.begin(), w.end(), 0.0);
    stats.mean = stats.total / m;
    stats.min_val = w.front();
    stats.max_val = w.back();
    stats.median = (m % 2 == 0) ? 0.5 * (w[m / 2 - 1] + w[m / 2]) : w[m / 2];

    Real var = 0.0;
    for (auto v : w) {
        var += (v - stats.mean) * (v - stats.mean);
    }
    stats.stddev = std::sqrt(var / m);

    return stats;
}

} // namespace politeia
