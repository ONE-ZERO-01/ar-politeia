#pragma once

/// @file loyalty.hpp
/// @brief 依附关系与忠诚度系统（研究方案 §2.3 阶段4）
///
/// 当交互网络分析检测到稳定的单向资源流时，将隐式的
/// 支配关系转化为显式的 superior_i 指针和 L_ij 忠诚度权重。
///
/// 忠诚度演化方程：
///   dL_ij/dt = α·protection(j→i) − β·tax_rate(j→i) − γ·|c⃗_i−c⃗_j| + η(t)
///
/// 触发事件：
///   L_ij < L_rebel  → 叛乱（断裂依附）
///   L_ij < L_switch → 投靠（转移依附）
///   群体性崩塌       → 王朝覆灭
///
/// 有效权力（派生量）：
///   Power_i = Σ_{j ∈ subtree(i)} w_j × L_path(i,j)

#include "core/types.hpp"
#include "core/particle_data.hpp"
#include "domain/cell_list.hpp"
#include "analysis/network_analysis.hpp"

#include <random>
#include <vector>

namespace politeia {

struct LoyaltyParams {
    Real protection_gain = 0.03;  // α: loyalty increase from protection
    Real tax_drain = 0.1;         // β: loyalty decrease from taxation
    Real culture_penalty = 0.02;  // γ: loyalty decrease per unit culture distance
    Real noise_sigma = 0.01;      // η: random loyalty fluctuation
    Real tax_rate = 0.05;         // fraction of subordinate wealth extracted per step
    Real tax_efficiency = 0.5;    // fraction of collected tax that reaches the superior
                                  // (1-efficiency) is lost to administrative friction

    Real rebel_threshold = 0.1;   // L < this → rebellion (break link)
    Real switch_threshold = 0.2;  // L < this → may switch to better superior
    Real attachment_threshold = 0.05; // net resource flow ratio to form attachment

    Real initial_loyalty = 0.5;   // L_ij when attachment first forms
    Real loyalty_clamp_min = 0.0;
    Real loyalty_clamp_max = 1.0;

    Real succession_loyalty_factor = 0.85; // L *= this on leader death (was 0.7)
    Real succession_heir_loyalty_cap = 0.8; // heir's loyalty to inherited superior cap (was 0.6)

    int max_hierarchy_depth = 10; // max allowed chain depth (prevents unrealistic H=200+)
};

/// Detect stable unidirectional resource flows from the interaction network
/// and establish new superior_i attachments.
/// Only creates attachments for particles that are currently root nodes (superior == -1).
/// Returns the number of new attachments formed.
[[nodiscard]] Index form_attachments(
    ParticleData& particles,
    const InteractionNetwork& network,
    const LoyaltyParams& params
);

/// Evolve loyalty L_ij for all particles with a superior.
/// Applies: protection gain, tax drain, culture distance penalty, noise.
void evolve_loyalty(
    ParticleData& particles,
    const LoyaltyParams& params,
    Real dt,
    std::mt19937_64& rng
);

/// Process rebellion, defection, and dynasty collapse.
/// - L < rebel_threshold → break attachment (particle becomes root)
/// - L < switch_threshold → may switch to a nearby stronger superior
/// - If a root loses all subordinates → dynasty collapse
/// Returns number of links broken.
[[nodiscard]] Index process_loyalty_events(
    ParticleData& particles,
    const CellList& cells,
    const LoyaltyParams& params,
    std::mt19937_64& rng
);

/// Apply taxation: superior extracts tax_rate fraction of each subordinate's wealth.
/// Protection: superior distributes protection_share to subordinates.
void apply_taxation(
    ParticleData& particles,
    const LoyaltyParams& params,
    Real dt
);

/// Compute effective power Power_i = Σ_{j ∈ subtree(i)} w_j × L_path(i,j).
/// Returns power for each particle (0 for non-root, >0 for leaders).
[[nodiscard]] std::vector<Real> compute_effective_power(
    const ParticleData& particles
);

/// War enhancement parameters (26E)
struct ConquestParams {
    Real power_ratio = 1.5;
    Real base_prob = 0.01;
    Real initial_loyalty = 0.3;

    bool war_cost_enabled = false;
    Real war_cost_attacker = 0.1;
    Real war_cost_defender = 0.2;

    bool war_casualties_enabled = false;
    Real war_casualty_rate = 0.05;

    bool pillage_enabled = false;
    Real pillage_fraction = 0.3;

    bool deterrence_enabled = false;
    Real deterrence_ratio = 3.0;
};

/// Attempt conquest with configurable war mechanics.
/// Returns number of conquests.
[[nodiscard]] Index attempt_conquest(
    ParticleData& particles,
    const CellList& cells,
    const std::vector<Real>& power,
    Real interaction_range,
    std::mt19937_64& rng,
    const ConquestParams& cparams = ConquestParams{},
    int max_hierarchy_depth = 10
);

/// Repair dangling superior pointers after compact().
/// Maps old indices to new indices; sets superior = -1 if the old superior is dead.
void repair_superior_after_compact(
    ParticleData& particles,
    const std::vector<Index>& old_to_new_map,
    Index old_count
);

// ─── Phase 14: 世袭继承 ──────────────────────────────────

/// Process succession when a leader dies:
/// 1. Find all direct subordinates of the dead leader
/// 2. Select heir: subordinate with highest (wealth × loyalty) product
/// 3. Transfer subordinates to heir; heir becomes new root or inherits dead leader's superior
/// 4. Distribute estate (dead leader's wealth) among heir and subordinates
/// Must be called BEFORE mark_dead or compact for dying particles.
/// Returns number of successions processed.
[[nodiscard]] Index process_succession(
    ParticleData& particles,
    const std::vector<Index>& dying_indices,
    const LoyaltyParams& params = LoyaltyParams{}
);

/// Assign newborn child to parent's hierarchy.
/// Child inherits the superior of parent_a (or parent_b if parent_a has none).
/// Sets initial child loyalty based on parent loyalty.
void inherit_hierarchy(
    ParticleData& particles,
    Index child_idx,
    Index parent_a,
    Index parent_b,
    const LoyaltyParams& params = LoyaltyParams{}
);

/// Break superior cycles and shorten chains deeper than max_hierarchy_depth.
/// Returns number of superior links modified.
[[nodiscard]] Index repair_hierarchy_graph(
    ParticleData& particles,
    int max_hierarchy_depth
);

} // namespace politeia
