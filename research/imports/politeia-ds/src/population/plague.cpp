/// @file plague.cpp
/// @brief 瘟疫差异化打击模型实现
///
/// SIR 传播动力学 + 免疫向量差异化死亡率
///
/// 核心机制（研究方案 §2.3）：
///   触发：高密度区随机生成新病原体 k（Poisson 过程）
///   传播：S → I（空间接触传播，概率 ∝ 附近感染者数）
///   结果：I → R（康复，获得免疫 d^k=1）或 I → D（死亡）
///   死亡率：P_death = P₀ × (1 − d^k_i)
///     d^k_i = 1（有免疫）→ 不死
///     d^k_i = 0（无免疫）→ 死亡率 P₀（可达 30-90%）
///
/// 与模型核心要素的耦合：
///   地形势垒 → 隔离 → 免疫差异 → 接触时冲击
///   ε 跃迁 → 航海突破 → 跨越势垒 → 瘟疫传播
///   大群体 → 更多地方性病原体 → 接触小群体时是"瘟疫输出方"

#include "population/plague.hpp"

#include <cmath>
#include <algorithm>

namespace politeia {

void PlagueManager::init(Index n_particles, int n_pathogens) {
    n_pathogens_ = n_pathogens;
    sir_state_.resize(n_particles, InfectionState::Susceptible);
    infection_timer_.resize(n_particles, 0.0);
    active_pathogen_ = -1;
    infected_count_ = 0;
}

void PlagueManager::resize(Index new_count) {
    sir_state_.resize(new_count, InfectionState::Susceptible);
    infection_timer_.resize(new_count, 0.0);
}

Index PlagueManager::update(
    ParticleData& particles,
    const CellList& cells,
    const PlagueParams& params,
    Real local_density_estimate,
    Real dt,
    std::mt19937_64& rng
) {
    const Index n = particles.count();
    std::uniform_real_distribution<Real> uniform(0.0, 1.0);
    Index plague_deaths = 0;

    // 确保 SIR 状态数组与粒子数同步
    if (sir_state_.size() < n) {
        sir_state_.resize(n, InfectionState::Susceptible);
        infection_timer_.resize(n, 0.0);
    }

    // ============================================================
    // 1. 瘟疫触发：高密度区以 Poisson 过程生成新病原体
    // 社会含义：城市人口密集 → 更容易爆发瘟疫
    // ============================================================
    if (!has_active_plague()) {
        if (local_density_estimate > params.trigger_density) {
            if (uniform(rng) < params.trigger_rate * dt) {
                // 生成新病原体
                active_pathogen_ = static_cast<int>(uniform(rng) * n_pathogens_) % n_pathogens_;

                // 选择一个随机的"零号病人"
                std::uniform_int_distribution<Index> patient_dist(0, n - 1);
                Index patient_zero = patient_dist(rng);
                if (particles.status(patient_zero) == ParticleStatus::Alive) {
                    sir_state_[patient_zero] = InfectionState::Infected;
                    infection_timer_[patient_zero] = 0.0;
                    infected_count_ = 1;
                }
            }
        }
        if (!has_active_plague()) return 0;
    }

    const int pathogen = active_pathogen_;
    const Real cutoff_sq = params.infection_radius * params.infection_radius;
    const Real* __restrict__ x = particles.x_data();

    // ============================================================
    // 2. SIR 传播：S → I（空间接触传播）
    // 易感者接触到感染者时，以一定概率被感染
    // ============================================================
    std::vector<Index> new_infections;

    cells.for_each_pair(x, n, cutoff_sq,
        [&](Index i, Index j, Real dx, Real dy, Real r2) {
            if (particles.status(i) != ParticleStatus::Alive) return;
            if (particles.status(j) != ParticleStatus::Alive) return;

            // 一方感染，另一方易感 → 可能传播
            bool i_infected = (sir_state_[i] == InfectionState::Infected);
            bool j_infected = (sir_state_[j] == InfectionState::Infected);
            bool i_susceptible = (sir_state_[i] == InfectionState::Susceptible);
            bool j_susceptible = (sir_state_[j] == InfectionState::Susceptible);

            if (i_infected && j_susceptible) {
                if (uniform(rng) < params.infection_rate * dt) {
                    new_infections.push_back(j);
                }
            }
            if (j_infected && i_susceptible) {
                if (uniform(rng) < params.infection_rate * dt) {
                    new_infections.push_back(i);
                }
            }
        }
    );

    for (Index idx : new_infections) {
        if (sir_state_[idx] == InfectionState::Susceptible) {
            sir_state_[idx] = InfectionState::Infected;
            infection_timer_[idx] = 0.0;
            infected_count_++;
        }
    }

    // ============================================================
    // 3. 感染结果：I → R（康复）或 I → D（死亡）
    // 死亡率取决于免疫向量：P_death = P₀ × (1 − d^k_i)
    // 有免疫力（d^k=1）→ 必定康复
    // 无免疫力（d^k=0）→ 死亡率 = P₀
    // ============================================================
    for (Index i = 0; i < n; ++i) {
        if (sir_state_[i] != InfectionState::Infected) continue;
        if (particles.status(i) != ParticleStatus::Alive) continue;

        infection_timer_[i] += dt;

        // 感染期满后决定结局
        if (infection_timer_[i] >= params.recovery_time) {
            // 差异化死亡率：取决于免疫向量
            Real immunity = 0.0;
            if (particles.immune_dim() > 0 && pathogen < particles.immune_dim()) {
                immunity = particles.immunity(i, pathogen);
            }

            Real death_prob = params.base_mortality * (1.0 - immunity);

            if (uniform(rng) < death_prob) {
                // 死亡
                particles.mark_dead(i);
                sir_state_[i] = InfectionState::Susceptible;
                plague_deaths++;
            } else {
                // 康复：获得永久免疫
                sir_state_[i] = InfectionState::Recovered;
                if (particles.immune_dim() > 0 && pathogen < particles.immune_dim()) {
                    particles.immunity(i, pathogen) = 1.0;
                }
            }
            infected_count_--;
        }
    }

    // 瘟疫结束条件：无感染者
    if (infected_count_ <= 0) {
        active_pathogen_ = -1;
        infected_count_ = 0;
    }

    return plague_deaths;
}

void inherit_immunity(
    ParticleData& particles,
    Index child_idx,
    Index parent_a,
    Index parent_b,
    Real inheritance_factor
) {
    // 后代部分继承父母免疫力（研究方案 §2.5.4）
    // d^k_child = α × (d^k_mother + d^k_father) / 2
    // 新生代免疫力低于父代，需自身感染才能获得完全免疫
    const int m = particles.immune_dim();
    for (int k = 0; k < m; ++k) {
        Real parent_avg = 0.5 * (particles.immunity(parent_a, k) +
                                  particles.immunity(parent_b, k));
        particles.immunity(child_idx, k) = inheritance_factor * parent_avg;
    }
}

} // namespace politeia
