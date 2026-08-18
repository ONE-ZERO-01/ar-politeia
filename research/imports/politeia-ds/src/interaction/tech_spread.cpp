/// @file tech_spread.cpp
/// @brief 技术演化：ε 的三重演化机制 + 财富 Poisson 跳跃
///
/// 物理背景（研究方案 §2.4）：
///   dε = α·|c⃗|·ε·dt   +   [接触传播]   +   Δε·dN(t)
///        ↑ 缓慢漂移         ↑ 扩散          ↑ Poisson 跳跃
///
/// 三种 ε 演化机制：
///   1. 缓慢漂移：知识量|c⃗|越高、技术ε越高，改良速度越快（马太效应/正反馈）
///   2. 接触传播：高 ε 的人教低 ε 的邻居——火的使用从一个部落传到另一个
///   3. Poisson 跳跃：重大技术突破（火→冶铁→蒸汽机→电力）是离散的跳跃
///      跳跃概率 ∝ |c⃗|：知识越多，突破概率越高
///
/// 财富 Poisson 跳跃（研究方案 §2.3）：
///   人生大多平淡（高斯扩散），偶有改变命运的大事件（Poisson 跳跃）
///   正跳跃：发现矿藏、意外继承（运气好）
///   负跳跃：被抢劫、火灾毁坏财产（运气差）
///
/// 这将模型从纯 Langevin 升级为 Lévy-type Jump-Diffusion。

#include "interaction/tech_spread.hpp"

#include <cmath>
#include <algorithm>

#ifdef POLITEIA_USE_OPENMP
#include <omp.h>
#endif

namespace politeia {

JumpStats evolve_technology(
    ParticleData& particles,
    const CellList& cells,
    const TechParams& params,
    Real dt,
    std::mt19937_64& rng,
    const Real* river_proximity_at_particle
) {
    const Index n = particles.count();
    const int cd = particles.culture_dim();
    Real* __restrict__ eps = particles.eps_data();
    Real* __restrict__ w = particles.w_data();
    const Real* __restrict__ x = particles.x_data();

    std::uniform_real_distribution<Real> uniform(0.0, 1.0);
    JumpStats stats;

    // ============================================================
    // 机制 1：缓慢漂移  dε = α × |c⃗| × ε × dt
    // 物理含义：日常的渐进式技术改良
    // |c⃗|（知识量）越高，改良越快（读书人改良工具的能力更强）
    // ε（现有技术）越高，改良越快（站在巨人肩上）
    // 两者相乘形成正反馈/马太效应：技术进步加速技术进步
    // ============================================================
    for (Index i = 0; i < n; ++i) {
        if (particles.status(i) != ParticleStatus::Alive) continue;

        Real c_norm = 0.0;
        for (int k = 0; k < cd; ++k) {
            c_norm += particles.culture(i, k) * particles.culture(i, k);
        }
        c_norm = std::sqrt(c_norm);

        eps[i] += params.drift_rate * c_norm * eps[i] * dt;
    }

    // ============================================================
    // 机制 2：接触传播  Δε_i = rate × (ε_j − ε_i) × dt
    // 物理含义：高技术者教低技术邻居
    // 类似热扩散：ε 从高处流向低处，直到均匀
    // 受地形势垒阻隔（只在 spread_range 内传播）
    // 社会类比：火的使用从一个部落传到另一个，但山脉阻断传播
    // ============================================================
    {
        const Real cutoff_sq = params.spread_range * params.spread_range;
        std::vector<Real> d_eps(n, 0.0);

#ifdef POLITEIA_USE_OPENMP
        #pragma omp parallel for schedule(dynamic, 64) if(n > 256)
        for (Index i = 0; i < n; ++i) {
            if (particles.status(i) != ParticleStatus::Alive) continue;

            cells.for_neighbors_of(i, x, n, cutoff_sq,
                [&](Index j, Real dx, Real dy, Real r2) {
                    if (particles.status(j) != ParticleStatus::Alive) return;

                    Real diff = eps[j] - eps[i];
                    Real transfer = params.spread_rate * diff * dt;
                    if (params.river_enabled && river_proximity_at_particle != nullptr) {
                        const Real prox = std::min(
                            std::max(0.0, river_proximity_at_particle[i]),
                            std::max(0.0, river_proximity_at_particle[j])
                        );
                        transfer *= 1.0 + params.river_strength * prox;
                    }

                    d_eps[i] += transfer;
                }
            );
        }
#else
        cells.for_each_pair(x, n, cutoff_sq,
            [&](Index i, Index j, Real dx, Real dy, Real r2) {
                if (particles.status(i) != ParticleStatus::Alive) return;
                if (particles.status(j) != ParticleStatus::Alive) return;

                Real diff = eps[j] - eps[i];
                Real transfer = params.spread_rate * diff * dt;
                if (params.river_enabled && river_proximity_at_particle != nullptr) {
                    const Real prox = std::min(
                        std::max(0.0, river_proximity_at_particle[i]),
                        std::max(0.0, river_proximity_at_particle[j])
                    );
                    transfer *= 1.0 + params.river_strength * prox;
                }

                d_eps[i] += transfer;
                d_eps[j] -= transfer;
            }
        );
#endif

        #pragma omp parallel for schedule(static) if(n > 256)
        for (Index i = 0; i < n; ++i) {
            if (particles.status(i) == ParticleStatus::Alive) {
                eps[i] += d_eps[i];
                if (eps[i] < 0.1) eps[i] = 0.1;
            }
        }
    }

    // ============================================================
    // 机制 3：ε Poisson 跳跃（技术突破）
    // 物理含义：重大技术发现不是连续的——火的发现、冶铁术、蒸汽机
    //   是离散的跳跃事件（Poisson 过程），不是渐进的
    // 跳跃概率 = λ × (1 + κ × |c⃗|) × dt
    //   知识越多（|c⃗|越大），发生突破的概率越高
    // 跳跃幅度 = Δε × ε_i（相对跳跃：技术越高，突破越大）
    // ============================================================
    for (Index i = 0; i < n; ++i) {
        if (particles.status(i) != ParticleStatus::Alive) continue;

        Real c_norm = 0.0;
        for (int k = 0; k < cd; ++k) {
            c_norm += particles.culture(i, k) * particles.culture(i, k);
        }
        c_norm = std::sqrt(c_norm);

        Real jump_prob = params.jump_base_rate * (1.0 + params.jump_knowledge_scale * c_norm) * dt;

        if (uniform(rng) < jump_prob) {
            eps[i] += params.jump_magnitude * eps[i];
            stats.eps_jumps++;
        }
    }

    // ============================================================
    // 机制 4：财富 Poisson 跳跃（运气/厄运）
    // 物理含义：人生中大多数时候平淡（高斯噪声覆盖），
    //   但偶尔有改变命运的大事件（Poisson 跳跃）
    // 正跳跃：发现矿藏、意外继承、贸易暴利
    // 负跳跃：被抢劫、自然灾害毁坏财产、火灾
    // 这使得财富分布从高斯变为厚尾（Pareto 幂律）
    // ============================================================
    for (Index i = 0; i < n; ++i) {
        if (particles.status(i) != ParticleStatus::Alive) continue;

        // 正跳跃（好运）
        if (uniform(rng) < params.wealth_jump_rate_pos * dt) {
            w[i] += params.wealth_jump_fraction * w[i];
            stats.wealth_jumps_pos++;
        }

        // 负跳跃（厄运）
        if (uniform(rng) < params.wealth_jump_rate_neg * dt) {
            w[i] -= params.wealth_jump_fraction * w[i];
            if (w[i] < 0.0) w[i] = 0.0;  // 财富不能为负
            stats.wealth_jumps_neg++;
        }
    }

    return stats;
}

Real compute_mean_epsilon(const ParticleData& particles) {
    // 计算所有存活个体的平均技术水平
    Real sum = 0.0;
    Index count = 0;
    for (Index i = 0; i < particles.count(); ++i) {
        if (particles.status(i) == ParticleStatus::Alive) {
            sum += particles.epsilon(i);
            count++;
        }
    }
    return (count > 0) ? sum / count : 0.0;
}

} // namespace politeia
