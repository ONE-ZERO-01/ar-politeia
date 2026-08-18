#include "analysis/network_analysis.hpp"

#include <algorithm>
#include <cmath>
#include <numeric>
#include <queue>

namespace politeia {

// ─── InteractionNetwork (per-particle hash map accumulator) ─────────

void InteractionNetwork::resize(Index n) {
    inflows_.resize(n);
}

void InteractionNetwork::record_transfer(Index i, Index j, Real dw) {
    if (std::abs(dw) < 1e-15 || i == j) return;

    // Positive dw means i gains from j → j provides resources to i
    // We track: for each "gainer", who provides the most?
    Index gainer, donor;
    Real amount;
    if (dw > 0) {
        gainer = i; donor = j; amount = dw;
    } else {
        gainer = j; donor = i; amount = -dw;
    }

    if (gainer >= static_cast<Index>(inflows_.size())) return;
    inflows_[gainer][donor] += amount;
}

void InteractionNetwork::batch_record(const FlowRecord* records, std::size_t count) {
    for (std::size_t k = 0; k < count; ++k) {
        record_transfer(records[k].i, records[k].j, records[k].dw);
    }
}

void InteractionNetwork::reset() {
    for (auto& m : inflows_) m.clear();
    total_edges_ = 0;
}

std::vector<Index> InteractionNetwork::build_dominance_graph(
    Index n_particles,
    Real threshold
) const {
    constexpr Index NO_PARENT = static_cast<Index>(-1);
    std::vector<Index> dominator(n_particles, NO_PARENT);

    for (Index j = 0; j < n_particles && j < static_cast<Index>(inflows_.size()); ++j) {
        Real best = threshold;
        Index best_donor = NO_PARENT;

        for (const auto& [donor, amount] : inflows_[j]) {
            if (amount > best && donor < n_particles) {
                best = amount;
                best_donor = donor;
            }
        }
        dominator[j] = best_donor;
    }

    // Break cycles using O(N) generation-stamp algorithm
    std::vector<Index> visit_stamp(n_particles, 0);
    std::vector<Index> visit_origin(n_particles, NO_PARENT);
    Index generation = 0;

    for (Index i = 0; i < n_particles; ++i) {
        if (dominator[i] == NO_PARENT) continue;

        ++generation;
        Index node = i;
        while (node != NO_PARENT && visit_stamp[node] != generation) {
            if (visit_stamp[node] != 0 && visit_origin[node] != i) break;
            visit_stamp[node] = generation;
            visit_origin[node] = i;
            node = dominator[node];
        }

        if (node != NO_PARENT && visit_stamp[node] == generation && visit_origin[node] == i) {
            Index cycle_node = node;
            Index weakest_node = cycle_node;
            Real weakest_flow = 1e30;

            Index curr = cycle_node;
            do {
                auto it = inflows_[curr].find(dominator[curr]);
                Real flow = (it != inflows_[curr].end()) ? it->second : 0.0;
                if (flow < weakest_flow) {
                    weakest_flow = flow;
                    weakest_node = curr;
                }
                curr = dominator[curr];
            } while (curr != cycle_node);

            dominator[weakest_node] = NO_PARENT;
        }
    }

    return dominator;
}

// ─── Effective power (bottom-up tree aggregation) ─────────────────

std::vector<Real> compute_effective_power(
    const std::vector<Index>& dominator,
    const ParticleData& particles
) {
    constexpr Index NO_PARENT = static_cast<Index>(-1);
    const Index n = dominator.size();

    std::vector<std::vector<Index>> children(n);
    for (Index i = 0; i < n; ++i) {
        if (dominator[i] != NO_PARENT && dominator[i] < n) {
            children[dominator[i]].push_back(i);
        }
    }

    std::vector<Real> power(n, 0.0);
    std::vector<int> in_deg(n, 0);
    for (Index i = 0; i < n; ++i) {
        if (dominator[i] != NO_PARENT && dominator[i] < n) {
            in_deg[dominator[i]]++;
        }
    }

    std::queue<Index> q;
    for (Index i = 0; i < n; ++i) {
        power[i] = std::max(0.0, (i < particles.count()) ? particles.wealth(i) : 0.0);
        if (in_deg[i] == 0) q.push(i);
    }

    while (!q.empty()) {
        Index node = q.front();
        q.pop();
        Index parent = dominator[node];
        if (parent != NO_PARENT && parent < n) {
            power[parent] += power[node];
            in_deg[parent]--;
            if (in_deg[parent] == 0) q.push(parent);
        }
    }

    return power;
}

// ─── Hierarchy metrics ───────────────────────────────────────────

HierarchyMetrics compute_hierarchy_metrics(
    const std::vector<Index>& dominator,
    const ParticleData& particles
) {
    constexpr Index NO_PARENT = static_cast<Index>(-1);
    const Index n = dominator.size();
    HierarchyMetrics m;
    if (n == 0) return m;

    std::vector<std::vector<Index>> children(n);
    std::vector<Index> roots;

    for (Index i = 0; i < n; ++i) {
        if (dominator[i] == NO_PARENT) {
            roots.push_back(i);
        } else if (dominator[i] < n) {
            children[dominator[i]].push_back(i);
        }
    }

    m.n_components = roots.size();

    std::vector<int> depth(n, 0);
    Index max_component_size = 0;
    int total_children = 0;
    int non_leaf_count = 0;

    for (Index root : roots) {
        std::queue<Index> bfs;
        bfs.push(root);
        Index comp_size = 0;

        while (!bfs.empty()) {
            Index node = bfs.front();
            bfs.pop();
            comp_size++;

            if (!children[node].empty()) {
                total_children += children[node].size();
                non_leaf_count++;
            }

            for (Index child : children[node]) {
                depth[child] = depth[node] + 1;
                if (depth[child] > static_cast<int>(m.max_depth)) {
                    m.max_depth = depth[child];
                }
                bfs.push(child);
            }
        }

        if (comp_size > max_component_size) {
            max_component_size = comp_size;
        }
    }

    m.largest_component = max_component_size;
    m.largest_fraction = (n > 0) ? static_cast<Real>(max_component_size) / n : 0.0;
    m.mean_branching = (non_leaf_count > 0) ? static_cast<Real>(total_children) / non_leaf_count : 0.0;

    // Ψ: feudalism-centralism parameter
    Real psi_sum = 0.0;
    int psi_count = 0;

    for (Index i = 0; i < n; ++i) {
        if (depth[i] == 1 && !children[i].empty()) {
            std::queue<Index> sub_bfs;
            sub_bfs.push(i);
            Real subtree_w = 0.0;
            while (!sub_bfs.empty()) {
                Index node = sub_bfs.front();
                sub_bfs.pop();
                if (node < particles.count()) {
                    subtree_w += std::max(0.0, particles.wealth(node));
                }
                for (Index c : children[node]) sub_bfs.push(c);
            }
            Real self_w = (i < particles.count()) ? std::max(0.0, particles.wealth(i)) : 0.0;
            if (subtree_w > 1e-15) {
                psi_sum += self_w / subtree_w;
                psi_count++;
            }
        }
    }
    m.psi = (psi_count > 0) ? psi_sum / psi_count : 0.0;

    return m;
}

// ─── Build dominator from explicit superior pointers ─────────────

std::vector<Index> build_dominator_from_superior(
    const ParticleData& particles
) {
    constexpr Index NO_PARENT = static_cast<Index>(-1);
    const Index n = particles.count();
    std::vector<Index> dominator(n, NO_PARENT);

    for (Index i = 0; i < n; ++i) {
        if (particles.status(i) != ParticleStatus::Alive) continue;

        Id sup_gid = particles.superior(i);
        if (sup_gid < 0) continue;

        Index sup_local = particles.gid_to_local(sup_gid);
        if (sup_local != NO_PARENT &&
            particles.status(sup_local) == ParticleStatus::Alive)
        {
            dominator[i] = sup_local;
        }
    }

    return dominator;
}

} // namespace politeia
