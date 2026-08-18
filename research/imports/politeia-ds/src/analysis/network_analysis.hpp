#pragma once

#include "core/types.hpp"
#include "core/particle_data.hpp"
#include "domain/cell_list.hpp"

#include <vector>
#include <unordered_map>
#include <algorithm>

namespace politeia {

/// Tracks net resource flow per particle over a time window.
/// Architecture: per-particle small hash maps instead of one giant global map.
/// Each particle tracks its donors independently, giving O(1) amortized
/// insertion and excellent cache locality for the build_dominance_graph scan.
class InteractionNetwork {
public:
    InteractionNetwork() = default;

    /// Pre-allocate for N particles.
    void resize(Index n);

    /// Record a resource transfer: positive dw means i gains from j.
    void record_transfer(Index i, Index j, Real dw);

    /// Batch-record transfers from parallel buffers.
    struct FlowRecord { Index i; Index j; Real dw; };
    void batch_record(const FlowRecord* records, std::size_t count);

    /// Reset accumulated flows (call at each analysis window).
    void reset();

    /// Build directed dominance graph from accumulated flows.
    /// Returns dominator[j] = i means i dominates j (net inflow > threshold).
    [[nodiscard]] std::vector<Index> build_dominance_graph(
        Index n_particles,
        Real threshold
    ) const;

    [[nodiscard]] std::size_t num_edges() const { return total_edges_; }

private:
    // Per-particle map: donor_index → accumulated net inflow
    std::vector<std::unordered_map<Index, Real>> inflows_;
    std::size_t total_edges_ = 0;
};

/// Hierarchy metrics computed from dominance graph.
struct HierarchyMetrics {
    Index max_depth = 0;
    Real mean_branching = 0.0;
    Index largest_component = 0;
    Index n_components = 0;
    Real largest_fraction = 0.0;
    Real psi = 0.0;
    Real power_gini = 0.0;
};

[[nodiscard]] HierarchyMetrics compute_hierarchy_metrics(
    const std::vector<Index>& dominator,
    const ParticleData& particles
);

[[nodiscard]] std::vector<Real> compute_effective_power(
    const std::vector<Index>& dominator,
    const ParticleData& particles
);

[[nodiscard]] std::vector<Index> build_dominator_from_superior(
    const ParticleData& particles
);

} // namespace politeia
