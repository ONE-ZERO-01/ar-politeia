/// @file social_force.cpp
/// @brief 人际空间交互力计算
///
/// 借鉴 Lennard-Jones 势的数学形式来模拟人际吸引和排斥：
///   V(r) = 4ε [(σ/r)¹² − (σ/r)⁶]
///   F(r) = 24ε [2(σ/r)¹² − (σ/r)⁶] / r
///
/// 社会类比：
///   - (σ/r)¹² 排斥项：两人不能占据同一位置，过近导致资源竞争
///   - (σ/r)⁶  吸引项：人是社会动物，中等距离倾向聚居合作
///   - σ：人际"舒适距离"——既不太远（孤立）也不太近（冲突）
///   - ε：人际吸引强度——决定聚集的紧密程度
///
/// 实现要点：
///   - 截断平移：V(r_cut) = 0，避免截断处的能量不连续
///   - Newton 第三定律：F_i = -F_j，每对只计算一次（对称规则）
///   - 力封顶 F_MAX：防止初始化时偶然重叠的粒子对产生数值爆炸
///
/// 研究方案 §2.6.2：这是"对称规则"的核心之一。规则本身不偏袒任何人，
/// 聚集行为（部落/村落的形成）是涌现的，不是预设的。

#include "force/social_force.hpp"

#include <cmath>
#include <vector>

#ifdef POLITEIA_USE_OPENMP
#include <omp.h>
#endif

namespace politeia {

Real compute_social_forces(
    const Real* __restrict__ x_data,
    Real* __restrict__ force,
    Index count,
    const CellList& cells,
    const SocialForceParams& params
) {
    const Real sigma2 = params.sigma * params.sigma;
    const Real cutoff_sq = params.cutoff * params.cutoff;
    const Real eps4 = 4.0 * params.epsilon;
    const Real eps24 = 24.0 * params.epsilon;

    // 截断平移量：保证势能在截断距离处连续为零
    const Real sr2_cut = sigma2 / cutoff_sq;
    const Real sr6_cut = sr2_cut * sr2_cut * sr2_cut;
    const Real e_shift = eps4 * (sr6_cut * sr6_cut - sr6_cut);

    constexpr Real F_MAX = 30.0;

    // Soft-core minimum distance: prevents both force and energy singularity
    // when particles overlap. r² is clamped to (0.5σ)², bounding the
    // per-pair LJ energy to ~48ε — comparable to the well depth.
    // Forces at r < r_min are already capped by F_MAX, so this primarily
    // improves energy diagnostics without changing dynamics.
    const Real r_min_sq = 0.25 * sigma2;

#ifdef POLITEIA_USE_OPENMP
    // OpenMP 版本：每个粒子独立计算自己的邻居力（无 Newton 第三定律），
    // 计算量翻倍但完全消除写竞争，适合线程并行。
    // 势能每对计算两次，除以 2 修正。
    Real total_pe = 0.0;

    #pragma omp parallel for schedule(dynamic, 64) reduction(+:total_pe) if(count > 256)
    for (Index i = 0; i < count; ++i) {
        Real fi_x = 0.0, fi_y = 0.0;
        Real pe_i = 0.0;

        cells.for_neighbors_of(i, x_data, count, cutoff_sq,
            [&](Index j, Real dx, Real dy, Real r2) {
                const Real r2_eff = std::max(r2, r_min_sq);
                const Real sr2 = sigma2 / r2_eff;
                const Real sr6 = sr2 * sr2 * sr2;
                const Real sr12 = sr6 * sr6;

                Real f_over_r = eps24 * (2.0 * sr12 - sr6) / r2_eff;

                const Real f_over_r_max = F_MAX / std::sqrt(r2_eff);
                if (f_over_r > f_over_r_max) f_over_r = f_over_r_max;
                if (f_over_r < -f_over_r_max) f_over_r = -f_over_r_max;

                fi_x -= f_over_r * dx;
                fi_y -= f_over_r * dy;

                pe_i += eps4 * (sr12 - sr6) - e_shift;
            }
        );

        // Per-particle total force cap: prevents KE explosion in
        // high-density regions where many overlapping neighbors each
        // contribute F_MAX, producing cumulative forces >> F_MAX.
        // Value chosen so that F*dt << v_thermal = sqrt(T): for T=0.3, dt=0.01,
        // F_TOTAL_MAX=50 gives dp=0.5 ≈ v_thermal, preventing single-step
        // momentum changes from dominating thermal fluctuations.
        constexpr Real F_TOTAL_MAX = 50.0;
        const Real fi_mag = std::sqrt(fi_x * fi_x + fi_y * fi_y);
        if (fi_mag > F_TOTAL_MAX) {
            const Real scale = F_TOTAL_MAX / fi_mag;
            fi_x *= scale;
            fi_y *= scale;
        }

        force[2 * i]     += fi_x;
        force[2 * i + 1] += fi_y;
        total_pe += pe_i;
    }

    return total_pe * 0.5;  // each pair counted twice
#else
    Real total_pe = 0.0;

    cells.for_each_pair(x_data, count, cutoff_sq,
        [&](Index i, Index j, Real dx, Real dy, Real r2) {
            const Real r2_eff = std::max(r2, r_min_sq);
            const Real sr2 = sigma2 / r2_eff;
            const Real sr6 = sr2 * sr2 * sr2;
            const Real sr12 = sr6 * sr6;

            Real f_over_r = eps24 * (2.0 * sr12 - sr6) / r2_eff;

            const Real f_over_r_max = F_MAX / std::sqrt(r2_eff);
            if (f_over_r > f_over_r_max) f_over_r = f_over_r_max;
            if (f_over_r < -f_over_r_max) f_over_r = -f_over_r_max;

            const Real fx = f_over_r * dx;
            const Real fy = f_over_r * dy;

            force[2 * i]     -= fx;
            force[2 * i + 1] -= fy;
            force[2 * j]     += fx;
            force[2 * j + 1] += fy;

            total_pe += eps4 * (sr12 - sr6) - e_shift;
        }
    );

    constexpr Real F_TOTAL_MAX_SEQ = 50.0;
    for (Index i = 0; i < count; ++i) {
        const Real fx = force[2 * i];
        const Real fy = force[2 * i + 1];
        const Real fmag = std::sqrt(fx * fx + fy * fy);
        if (fmag > F_TOTAL_MAX_SEQ) {
            const Real s = F_TOTAL_MAX_SEQ / fmag;
            force[2 * i]     *= s;
            force[2 * i + 1] *= s;
        }
    }

    return total_pe;
#endif
}

} // namespace politeia
