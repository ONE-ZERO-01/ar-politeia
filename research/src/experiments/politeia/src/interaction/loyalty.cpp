/// @file loyalty.cpp
/// @brief 依附关系、忠诚度演化、叛乱与征服

#include "interaction/loyalty.hpp"
#include "interaction/culture_dynamics.hpp"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <unordered_map>
#include <unordered_set>
#include <vector>

namespace politeia {

// ─── 辅助: 计算粒子在层级链中的深度（到根的距离） ─────────

static int chain_depth_of(const ParticleData& particles, Index i) {
    const Index n = particles.count();
    static thread_local std::vector<uint32_t> depth_stamp;
    if (depth_stamp.size() < n) depth_stamp.assign(n, 0);

    static uint32_t depth_gen = 0;
    if (++depth_gen == 0) {
        std::fill(depth_stamp.begin(), depth_stamp.end(), 0);
        depth_gen = 1;
    }

    int depth = 0;
    Index cur = i;
    constexpr int SAFETY_LIMIT = 300;
    while (depth < SAFETY_LIMIT) {
        if (depth_stamp[cur] == depth_gen) break;
        depth_stamp[cur] = depth_gen;
        Id sup_gid = particles.superior(cur);
        if (sup_gid < 0) break;
        Index sup_local = particles.gid_to_local(sup_gid);
        if (sup_local == static_cast<Index>(-1)) break;
        if (particles.status(sup_local) != ParticleStatus::Alive) break;
        cur = sup_local;
        ++depth;
    }
    return depth;
}

static bool is_ancestor_of(
    const ParticleData& particles, Index start, Index target, int max_steps = 32
) {
    Index cur = start;
    for (int step = 0; step < max_steps; ++step) {
        if (cur == target) return true;
        Id sup_gid = particles.superior(cur);
        if (sup_gid < 0) return false;
        Index sup_local = particles.gid_to_local(sup_gid);
        if (sup_local == static_cast<Index>(-1)) return false;
        if (particles.status(sup_local) != ParticleStatus::Alive) return false;
        cur = sup_local;
    }
    return false;
}

static bool would_create_cycle(
    const ParticleData& particles, Index sub_idx, Index sup_idx
) {
    if (sub_idx == sup_idx) return true;
    return is_ancestor_of(particles, sup_idx, sub_idx);
}

static bool attachment_within_depth_limit(
    const ParticleData& particles, Index sup_idx, int max_hierarchy_depth
) {
    if (max_hierarchy_depth <= 0) return true;
    // New subordinate would be at depth chain_depth(sup) + 1.
    return chain_depth_of(particles, sup_idx) + 1 <= max_hierarchy_depth;
}

// ─── 依附形成 ─────────────────────────────────────────────

Index form_attachments(
    ParticleData& particles,
    const InteractionNetwork& network,
    const LoyaltyParams& params
) {
    const Index n = particles.count();
    if (n == 0) return 0;

    auto dominator = network.build_dominance_graph(n, params.attachment_threshold);

    Index formed = 0;
    for (Index i = 0; i < n; ++i) {
        if (particles.status(i) != ParticleStatus::Alive) continue;
        if (particles.superior(i) != -1) continue;

        Id dom = dominator[i];
        if (dom >= 0 && static_cast<Index>(dom) < n
            && particles.status(static_cast<Index>(dom)) == ParticleStatus::Alive)
        {
            auto dom_idx = static_cast<Index>(dom);
            if (dom_idx == i) continue;
            if (would_create_cycle(particles, i, dom_idx)) continue;
            if (!attachment_within_depth_limit(
                    particles, dom_idx, params.max_hierarchy_depth)) continue;

            particles.superior(i) = particles.global_id(dom_idx);
            particles.loyalty(i) = params.initial_loyalty;
            ++formed;
        }
    }

    return formed;
}

// ─── 忠诚度演化 ───────────────────────────────────────────

void evolve_loyalty(
    ParticleData& particles,
    const LoyaltyParams& params,
    Real dt,
    std::mt19937_64& rng
) {
    std::normal_distribution<Real> noise(0.0, params.noise_sigma);
    const Index n = particles.count();

    for (Index i = 0; i < n; ++i) {
        if (particles.status(i) != ParticleStatus::Alive) continue;

        Id sup_gid = particles.superior(i);
        if (sup_gid < 0) continue;

        Index j = particles.gid_to_local(sup_gid);
        if (j == static_cast<Index>(-1) || particles.status(j) != ParticleStatus::Alive) {
            particles.superior(i) = -1;
            particles.loyalty(i) = 0.0;
            continue;
        }

        Real protection = 0.0;
        if (particles.wealth(j) > 0) {
            protection = params.protection_gain *
                std::min(1.0, particles.wealth(j) / (particles.wealth(i) + 1e-10));
        }

        Real tax_cost = params.tax_drain * params.tax_rate;
        Real c_dist = culture_distance(particles, i, j);
        Real culture_cost = params.culture_penalty * c_dist;
        Real eta = noise(rng);

        Real dL = (protection - tax_cost - culture_cost + eta) * dt;
        Real L = particles.loyalty(i) + dL;

        particles.loyalty(i) = std::clamp(L,
            params.loyalty_clamp_min, params.loyalty_clamp_max);
    }
}

// ─── 叛乱与投靠 ───────────────────────────────────────────

Index process_loyalty_events(
    ParticleData& particles,
    const CellList& cells,
    const LoyaltyParams& params,
    std::mt19937_64& rng
) {
    const Index n = particles.count();
    Index broken = 0;

    for (Index i = 0; i < n; ++i) {
        if (particles.status(i) != ParticleStatus::Alive) continue;

        Id sup_gid = particles.superior(i);
        if (sup_gid < 0) continue;

        Real L = particles.loyalty(i);

        if (L < params.rebel_threshold) {
            particles.superior(i) = -1;
            particles.loyalty(i) = 0.0;
            ++broken;
            continue;
        }

        if (L < params.switch_threshold) {
            Real cutoff_sq = 2.5 * 2.5;
            Id best_sup_gid = -1;
            Index sup_local = particles.gid_to_local(sup_gid);
            Real best_w = (sup_local != static_cast<Index>(-1))
                          ? particles.wealth(sup_local) : 0.0;

            cells.for_neighbors_of(i, particles.x_data(), n, cutoff_sq,
                [&](Index j, Real dx, Real dy, Real r2) {
                    if (j == i) return;
                    if (particles.status(j) != ParticleStatus::Alive) return;
                    if (particles.superior(j) != -1) return;
                    if (particles.wealth(j) > best_w) {
                        best_w = particles.wealth(j);
                        best_sup_gid = particles.global_id(j);
                    }
                }
            );

            if (best_sup_gid >= 0 && best_sup_gid != sup_gid) {
                Index best_local = particles.gid_to_local(best_sup_gid);
                if (best_local != static_cast<Index>(-1) &&
                    !would_create_cycle(particles, i, best_local) &&
                    attachment_within_depth_limit(
                        particles, best_local, params.max_hierarchy_depth))
                {
                    particles.superior(i) = best_sup_gid;
                    particles.loyalty(i) = params.initial_loyalty * 0.8;
                    ++broken;
                }
            }
        }
    }

    return broken;
}

// ─── 税收与保护 ───────────────────────────────────────────

void apply_taxation(
    ParticleData& particles,
    const LoyaltyParams& params,
    Real dt
) {
    const Index n = particles.count();

    for (Index i = 0; i < n; ++i) {
        if (particles.status(i) != ParticleStatus::Alive) continue;

        Id sup_gid = particles.superior(i);
        if (sup_gid < 0) continue;

        Index j = particles.gid_to_local(sup_gid);
        if (j == static_cast<Index>(-1) || particles.status(j) != ParticleStatus::Alive) continue;

        Real tax = params.tax_rate * particles.wealth(i) * dt;
        tax = std::min(tax, particles.wealth(i) * 0.5);

        if (tax > 0) {
            particles.wealth(i) -= tax;
            particles.wealth(j) += tax * params.tax_efficiency;
        }
    }
}

// ─── 有效权力计算 ─────────────────────────────────────────

std::vector<Real> compute_effective_power(const ParticleData& particles) {
    const Index n = particles.count();
    std::vector<Real> power(n, 0.0);

    for (Index i = 0; i < n; ++i) {
        if (particles.status(i) != ParticleStatus::Alive) continue;

        Real w = std::max(0.0, particles.wealth(i));
        Real L_product = 1.0;

        Index cur = i;
        int depth = 0;
        constexpr int MAX_DEPTH = 100;

        while (depth < MAX_DEPTH) {
            Id sup_gid = particles.superior(cur);
            if (sup_gid < 0) {
                power[cur] += w * L_product;
                break;
            }
            Index sup_local = particles.gid_to_local(sup_gid);
            if (sup_local == static_cast<Index>(-1)) {
                // Superior on another rank — treat cur as local root
                power[cur] += w * L_product;
                break;
            }
            L_product *= particles.loyalty(cur);
            cur = sup_local;
            ++depth;
        }
    }

    return power;
}

// ─── 征服 ─────────────────────────────────────────────────

Index attempt_conquest(
    ParticleData& particles,
    const CellList& cells,
    const std::vector<Real>& power,
    Real interaction_range,
    std::mt19937_64& rng,
    const ConquestParams& cparams,
    int max_hierarchy_depth
) {
    const Index n = particles.count();
    const Real cutoff_sq = interaction_range * interaction_range;
    std::uniform_real_distribution<Real> uniform(0.0, 1.0);
    Index conquests = 0;
    
    // DEBUG: count root nodes and neighbors
    Index n_roots = 0, n_pairs = 0, n_power_ok = 0, n_deter = 0, n_reg = 0;

    for (Index i = 0; i < n; ++i) {
        if (particles.status(i) != ParticleStatus::Alive) continue;
        if (particles.superior(i) != -1) continue;
        if (power[i] < 1e-10) continue;
        ++n_roots;

        cells.for_neighbors_of(i, particles.x_data(), n, cutoff_sq,
            [&](Index j, Real dx, Real dy, Real r2) {
                if (j == i || j >= n) return;
                if (particles.status(j) != ParticleStatus::Alive) return;
                if (particles.superior(j) != -1) return;
                if (would_create_cycle(particles, j, i)) return;
                if (!attachment_within_depth_limit(
                        particles, i, max_hierarchy_depth)) return;
                ++n_pairs;

                // Deterrence: overwhelming power causes automatic submission
                if (cparams.deterrence_enabled &&
                    power[i] > power[j] * cparams.deterrence_ratio) {
                    particles.superior(j) = particles.global_id(i);
                    particles.loyalty(j) = cparams.initial_loyalty * 0.5;
                    ++conquests;
                    ++n_deter;
                    return;
                }

                if (power[i] > power[j] * cparams.power_ratio) {
                    ++n_power_ok;
                    Real p_conquer = cparams.base_prob * (power[i] / (power[i] + power[j]));
                    if (uniform(rng) < p_conquer) {
                        ++n_reg;
                        // War cost: attacker and defender pay wealth
                        if (cparams.war_cost_enabled) {
                            Real cost_i = particles.wealth(i) * cparams.war_cost_attacker;
                            Real cost_j = particles.wealth(j) * cparams.war_cost_defender;
                            particles.wealth(i) -= std::min(cost_i, particles.wealth(i) * 0.5);
                            particles.wealth(j) -= std::min(cost_j, particles.wealth(j) * 0.5);
                        }

                        // Pillage: transfer wealth from defender to attacker
                        if (cparams.pillage_enabled) {
                            Real loot = particles.wealth(j) * cparams.pillage_fraction;
                            particles.wealth(j) -= loot;
                            particles.wealth(i) += loot;
                        }

                        // War casualties: probabilistically kill subordinates
                        if (cparams.war_casualties_enabled) {
                            Id gid_j = particles.global_id(j);
                            for (Index k = 0; k < n; ++k) {
                                if (particles.status(k) != ParticleStatus::Alive) continue;
                                if (particles.superior(k) != gid_j) continue;
                                if (uniform(rng) < cparams.war_casualty_rate) {
                                    particles.mark_dead(k);
                                }
                            }
                        }

                        particles.superior(j) = particles.global_id(i);
                        particles.loyalty(j) = cparams.initial_loyalty;
                        ++conquests;
                    }
                }
            }
        );
    }

    // DEBUG: print stats
    fprintf(stderr, "[conquest] n=%d roots=%d pairs=%d power_ok=%d deter=%d reg=%d total=%d\n",
            (int)n, (int)n_roots, (int)n_pairs, (int)n_power_ok, (int)n_deter, (int)n_reg, (int)conquests);
    
    return conquests;
}

// ─── compact 后修复 ───────────────────────────────────────

void repair_superior_after_compact(
    ParticleData& particles,
    const std::vector<Index>& /*old_to_new*/,
    Index /*old_count*/
) {
    // With global IDs, compact doesn't invalidate superior pointers.
    // Just clear superiors that point to particles no longer on this rank.
    const Index n = particles.count();
    for (Index i = 0; i < n; ++i) {
        Id sup_gid = particles.superior(i);
        if (sup_gid < 0) continue;

        Index sup_local = particles.gid_to_local(sup_gid);
        if (sup_local == static_cast<Index>(-1) ||
            particles.status(sup_local) != ParticleStatus::Alive) {
            particles.superior(i) = -1;
            particles.loyalty(i) = 0.0;
        }
    }
}

// ─── 世袭继承 ─────────────────────────────────────────────

Index process_succession(
    ParticleData& particles,
    const std::vector<Index>& dying_indices,
    const LoyaltyParams& params
) {
    const Index n = particles.count();
    if (dying_indices.empty() || n == 0) return 0;

    // Collect dying global IDs for fast lookup
    std::unordered_map<Id, bool> dying_gids;
    for (Index d : dying_indices) {
        if (d < n) dying_gids[particles.global_id(d)] = true;
    }

    Index successions = 0;

    for (Index dead_idx : dying_indices) {
        if (dead_idx >= n) continue;
        Id dead_gid = particles.global_id(dead_idx);

        // Collect direct subordinates (those whose superior is the dead leader's gid)
        std::vector<Index> subordinates;
        for (Index i = 0; i < n; ++i) {
            if (dying_gids.count(particles.global_id(i))) continue;
            if (particles.status(i) != ParticleStatus::Alive) continue;
            if (particles.superior(i) == dead_gid) {
                subordinates.push_back(i);
            }
        }

        if (subordinates.empty()) continue;

        Index heir = subordinates[0];
        Real best_score = particles.wealth(heir) * particles.loyalty(heir);
        for (size_t k = 1; k < subordinates.size(); ++k) {
            Index s = subordinates[k];
            Real score = particles.wealth(s) * particles.loyalty(s);
            if (score > best_score) {
                best_score = score;
                heir = s;
            }
        }

        // Heir inherits the dead leader's superior (already a global ID)
        Id dead_superior_gid = particles.superior(dead_idx);
        if (dead_superior_gid >= 0 && !dying_gids.count(dead_superior_gid)) {
            Index dead_sup_local = particles.gid_to_local(dead_superior_gid);
            if (dead_sup_local != static_cast<Index>(-1) &&
                particles.status(dead_sup_local) == ParticleStatus::Alive &&
                !would_create_cycle(particles, heir, dead_sup_local) &&
                attachment_within_depth_limit(
                    particles, dead_sup_local, params.max_hierarchy_depth))
            {
                particles.superior(heir) = dead_superior_gid;
                particles.loyalty(heir) = std::min(
                    params.succession_heir_loyalty_cap, particles.loyalty(heir));
            } else {
                particles.superior(heir) = -1;
                particles.loyalty(heir) = 0.0;
            }
        } else {
            particles.superior(heir) = -1;
            particles.loyalty(heir) = 0.0;
        }

        Id heir_gid = particles.global_id(heir);
        for (Index s : subordinates) {
            if (s == heir) continue;
            if (!would_create_cycle(particles, s, heir) &&
                attachment_within_depth_limit(
                    particles, heir, params.max_hierarchy_depth))
            {
                particles.superior(s) = heir_gid;
                particles.loyalty(s) *= params.succession_loyalty_factor;
            }
        }

        Real estate = std::max(0.0, particles.wealth(dead_idx));
        if (estate > 0 && !subordinates.empty()) {
            Real heir_share = estate * 0.5;
            Real rest_share = estate * 0.5 / static_cast<Real>(subordinates.size() - 1 + 1);

            particles.wealth(heir) += heir_share;
            for (Index s : subordinates) {
                if (s != heir) {
                    particles.wealth(s) += rest_share;
                }
            }
            particles.wealth(dead_idx) = 0.0;
        }

        ++successions;
    }

    return successions;
}

// ─── 新生儿层级继承 ───────────────────────────────────────

void inherit_hierarchy(
    ParticleData& particles,
    Index child_idx,
    Index parent_a,
    Index parent_b,
    const LoyaltyParams& params
) {
    auto try_set_superior = [&](Index sup_idx) -> bool {
        if (would_create_cycle(particles, child_idx, sup_idx)) return false;
        if (!attachment_within_depth_limit(
                particles, sup_idx, params.max_hierarchy_depth)) return false;
        particles.superior(child_idx) = particles.global_id(sup_idx);
        return true;
    };

    Id sup_a = particles.superior(parent_a);
    Id sup_b = particles.superior(parent_b);

    if (sup_a >= 0) {
        Index sup_a_local = particles.gid_to_local(sup_a);
        if (sup_a_local != static_cast<Index>(-1) &&
            particles.status(sup_a_local) == ParticleStatus::Alive &&
            try_set_superior(sup_a_local))
        {
            particles.loyalty(child_idx) =
                std::min(0.8, particles.loyalty(parent_a) * 0.9);
            return;
        }
    }
    if (sup_b >= 0) {
        Index sup_b_local = particles.gid_to_local(sup_b);
        if (sup_b_local != static_cast<Index>(-1) &&
            particles.status(sup_b_local) == ParticleStatus::Alive &&
            try_set_superior(sup_b_local))
        {
            particles.loyalty(child_idx) =
                std::min(0.8, particles.loyalty(parent_b) * 0.9);
            return;
        }
    }

    // Both parents are roots — attach to a parent only if depth allows.
    Id gid_a = particles.global_id(parent_a);
    Id gid_b = particles.global_id(parent_b);
    bool a_is_leader = false, b_is_leader = false;
    const Index n = particles.count();
    for (Index i = 0; i < n; ++i) {
        if (i == child_idx) continue;
        if (particles.superior(i) == gid_a) a_is_leader = true;
        if (particles.superior(i) == gid_b) b_is_leader = true;
    }

    if (a_is_leader && try_set_superior(parent_a)) {
        particles.loyalty(child_idx) = 0.8;
    } else if (b_is_leader && try_set_superior(parent_b)) {
        particles.loyalty(child_idx) = 0.8;
    }
}

Index repair_hierarchy_graph(ParticleData& particles, int max_hierarchy_depth) {
    const Index n = particles.count();
    Index repaired = 0;

    // O(1) cycle marking per walk (avoid per-particle unordered_set allocation).
    static thread_local std::vector<uint32_t> visit_stamp;
    if (visit_stamp.size() < n) visit_stamp.assign(n, 0);

    static uint32_t visit_gen = 0;
    if (++visit_gen == 0) {
        std::fill(visit_stamp.begin(), visit_stamp.end(), 0);
        visit_gen = 1;
    }
    const uint32_t gen = visit_gen;

    for (Index i = 0; i < n; ++i) {
        if (particles.status(i) != ParticleStatus::Alive) continue;
        if (particles.superior(i) < 0) continue;

        Index cur = i;
        bool cycle = false;
        bool dangling = false;
        while (true) {
            if (visit_stamp[cur] == gen) {
                cycle = true;
                break;
            }
            visit_stamp[cur] = gen;
            Id sup_gid = particles.superior(cur);
            if (sup_gid < 0) break;
            Index sup_local = particles.gid_to_local(sup_gid);
            if (sup_local == static_cast<Index>(-1) ||
                particles.status(sup_local) != ParticleStatus::Alive) {
                dangling = true;
                break;
            }
            cur = sup_local;
        }

        if (cycle || dangling) {
            particles.superior(i) = -1;
            particles.loyalty(i) = 0.0;
            ++repaired;
            continue;
        }

        if (max_hierarchy_depth <= 0) continue;

        int depth = chain_depth_of(particles, i);
        if (depth <= max_hierarchy_depth) continue;

        const int excess = depth - max_hierarchy_depth;
        cur = i;
        for (int s = 0; s <= excess; ++s) {
            Id sup_gid = particles.superior(cur);
            if (sup_gid < 0) break;
            Index sup_local = particles.gid_to_local(sup_gid);
            if (sup_local == static_cast<Index>(-1) ||
                particles.status(sup_local) != ParticleStatus::Alive) {
                break;
            }
            cur = sup_local;
        }
        particles.superior(i) = particles.global_id(cur);
        ++repaired;
    }

    return repaired;
}

} // namespace politeia
