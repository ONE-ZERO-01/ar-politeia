/// @file resource_exchange.cpp
/// @brief 对称资源交换规则、资源产出/消耗、生存阈值
///
/// 物理背景（研究方案 §2.6.2）：
///   交换规则必须是标签对称的：交换 i↔j 后结果只变符号。
///   不平等不是规则偏袒产生的，而是从状态差异中自发涌现的。
///
/// 交换公式：
///   A_i = w_i × ε_i      （综合能力 = 财富 × 技术）
///   Δw = η × (A_i − A_j) / (A_i + A_j) × min(w_i, w_j)
///
/// 物理类比：引力 F=Gm1m2/r² 也是完全对称的，但大质量体依然吸引更多物质。
/// 同理，交换规则对称，但能力强者自然获益更多。
///
/// 资源产出：
///   dw = R(x) × ε × dt − consumption × dt
///   R(x) = base_production × max(0, −V(x))
///   在地形势阱中心（V < 0），产出高；远离势阱，产出低。
///   技术水平 ε 放大同一块土地的产出——这就是 ε 的乘性效应。

#include "interaction/resource_exchange.hpp"
#include "analysis/network_analysis.hpp"

#include <cmath>
#include <algorithm>
#include <vector>

#ifdef POLITEIA_USE_OPENMP
#include <omp.h>
#endif

namespace politeia {

namespace {

/// SplitMix64 finalizer: cheap, deterministic, no hidden state (OpenMP-safe).
inline std::uint64_t splitmix64(std::uint64_t x) {
    x += 0x9e3779b97f4a7c15ULL;
    x = (x ^ (x >> 30)) * 0xbf58476d1ce4e5b9ULL;
    x = (x ^ (x >> 27)) * 0x94d049bb133111ebULL;
    x = x ^ (x >> 31);
    return x;
}

/// Deterministic antisymmetric sign for pair (i,j) at time step `step`.
/// Returns s with s(i,j) = −s(j,i), reproducible across runs, and independent
/// of the traversal direction — so the OpenMP `for_neighbors_of` path (which
/// visits each pair from both endpoints) stays exactly zero-sum.
inline Real antisymmetric_sign(std::uint64_t i, std::uint64_t j, std::uint64_t step) {
    const std::uint64_t lo = (i < j) ? i : j;
    const std::uint64_t hi = (i < j) ? j : i;
    const std::uint64_t key = splitmix64(lo)
                            ^ (splitmix64(hi) * 0x9e3779b97f4a7c15ULL)
                            ^ (step * 0xd6e8feb86659fd93ULL);
    const std::uint64_t r = splitmix64(key);
    const Real mag = ((r >> 63) & 1ULL) ? 1.0 : -1.0;
    return (i < j) ? mag : -mag;
}

} // namespace

Real exchange_resources(
    ParticleData& particles,
    const CellList& cells,
    const ExchangeParams& params,
    InteractionNetwork* network,
    const Real* terrain_potential_at_particle,
    const Real* river_proximity_at_particle,
    std::uint64_t step
) {
    const Real cutoff_sq = params.cutoff * params.cutoff;
    const Real eta = params.exchange_rate;
    const Real eta_n = params.noise_strength;
    const bool barrier = params.terrain_barrier_enabled && terrain_potential_at_particle != nullptr;
    const Real inv_barrier_scale = barrier ? (1.0 / params.terrain_barrier_scale) : 0.0;
    const bool river_bonus = params.river_exchange_enabled && river_proximity_at_particle != nullptr;

    Real* __restrict__ w = particles.w_data();
    const Real* __restrict__ x = particles.x_data();
    const Real* __restrict__ eps = particles.eps_data();
    const Index n = particles.count();
    const Real w_ref = params.ability_saturation_w;
    const bool use_saturation = (w_ref > 0.0);

    Real total_transferred = 0.0;

#ifdef POLITEIA_USE_OPENMP
    std::vector<Real> dw_buf(n, 0.0);

    // Per-thread flow recording buffers (only allocated when network != nullptr)
    const int nthreads = omp_get_max_threads();
    struct FlowRecord { Index i; Index j; Real dw; };
    std::vector<std::vector<FlowRecord>> thread_flows;
    if (network) thread_flows.resize(nthreads);

    #pragma omp parallel for schedule(dynamic, 64) reduction(+:total_transferred) if(n > 256)
    for (Index i = 0; i < n; ++i) {
        if (particles.status(i) != ParticleStatus::Alive || w[i] <= 0.0) continue;

        cells.for_neighbors_of(i, x, n, cutoff_sq,
            [&](Index j, Real dx, Real dy, Real r2) {
                const Real wi = w[i];
                const Real wj = w[j];
                if (wj <= 0.0) return;

                Real Ai, Aj;
                if (use_saturation) {
                    Ai = eps[i] * wi / (wi + w_ref);
                    Aj = eps[j] * wj / (wj + w_ref);
                } else {
                    Ai = wi * eps[i];
                    Aj = wj * eps[j];
                }
                const Real A_sum = Ai + Aj;
                if (A_sum < 1e-15) return;

                const Real mn = std::min(wi, wj);
                const Real D = (Ai - Aj) / A_sum;
                const Real absD = std::abs(D);
                const Real s = antisymmetric_sign(
                    static_cast<std::uint64_t>(i),
                    static_cast<std::uint64_t>(j),
                    step);
                Real dw = mn * (eta * D + eta_n * absD * s);

                if (barrier) {
                    Real delta_h = std::abs(terrain_potential_at_particle[i]
                                          - terrain_potential_at_particle[j]);
                    dw *= std::exp(-delta_h * inv_barrier_scale);
                }
                if (river_bonus) {
                    const Real prox = std::min(
                        std::max(0.0, river_proximity_at_particle[i]),
                        std::max(0.0, river_proximity_at_particle[j])
                    );
                    dw *= 1.0 + params.river_exchange_strength * prox;
                }

                // Non-negativity clamp. From i's view, i gains dw and j loses
                // dw, so dw ∈ [−w_i, +w_j] keeps both endpoints non-negative.
                // The bound is direction-independent, so the j-view produces
                // −clamp(dw) = clamp(−dw), preserving exact zero-sum balance.
                dw = std::max(-wi, std::min(dw, wj));

                dw_buf[i] += dw;
                total_transferred += std::abs(dw);

                // Record flow for network (only from i<j to avoid double-counting)
                if (network && i < j && std::abs(dw) > 1e-15) {
                    int tid = omp_get_thread_num();
                    thread_flows[tid].push_back({i, j, dw});
                }
            }
        );
    }

    #pragma omp parallel for schedule(static) if(n > 256)
    for (Index i = 0; i < n; ++i) {
        w[i] += dw_buf[i];
    }

    // Merge per-thread flow records into the network (serial, but fast)
    if (network) {
        for (int t = 0; t < nthreads; ++t) {
            for (const auto& fr : thread_flows[t]) {
                network->record_transfer(fr.i, fr.j, fr.dw);
            }
        }
    }
#else
    cells.for_each_pair(x, n, cutoff_sq,
        [&](Index i, Index j, Real dx, Real dy, Real r2) {
            const Real wi = w[i];
            const Real wj = w[j];

            if (wi <= 0.0 || wj <= 0.0) return;

            Real Ai, Aj;
            if (use_saturation) {
                Ai = eps[i] * wi / (wi + w_ref);
                Aj = eps[j] * wj / (wj + w_ref);
            } else {
                Ai = wi * eps[i];
                Aj = wj * eps[j];
            }
            const Real A_sum = Ai + Aj;

            if (A_sum < 1e-15) return;

            const Real mn = std::min(wi, wj);
            const Real D = (Ai - Aj) / A_sum;
            const Real absD = std::abs(D);
            const Real s = antisymmetric_sign(
                static_cast<std::uint64_t>(i),
                static_cast<std::uint64_t>(j),
                step);
            Real dw = mn * (eta * D + eta_n * absD * s);

            if (barrier) {
                Real delta_h = std::abs(terrain_potential_at_particle[i]
                                      - terrain_potential_at_particle[j]);
                dw *= std::exp(-delta_h * inv_barrier_scale);
            }
            if (river_bonus) {
                const Real prox = std::min(
                    std::max(0.0, river_proximity_at_particle[i]),
                    std::max(0.0, river_proximity_at_particle[j])
                );
                dw *= 1.0 + params.river_exchange_strength * prox;
            }

            dw = std::max(-wi, std::min(dw, wj));

            w[i] += dw;
            w[j] -= dw;

            if (network && std::abs(dw) > 1e-15) {
                network->record_transfer(i, j, dw);
            }

            total_transferred += std::abs(dw);
        }
    );
#endif

    return total_transferred;
}

void apply_resource_dynamics(
    ParticleData& particles,
    Real dt,
    Real consumption_rate,
    Real base_production,
    const Real* terrain_potential_at_particle,
    bool terrain_production_enabled,
    Real terrain_production_scale,
    const Real* density_factor,
    const Real* river_proximity_at_particle,
    bool river_resource_enabled,
    Real river_resource_strength,
    Real river_resource_alpha,
    Real wealth_decay_rate
) {
    Real* __restrict__ w = particles.w_data();
    const Real* __restrict__ eps = particles.eps_data();
    const Index n = particles.count();

    #pragma omp parallel for schedule(static) if(n > 256)
    for (Index i = 0; i < n; ++i) {
        Real local_resource = 0.0;
        if (terrain_production_enabled && terrain_potential_at_particle != nullptr) {
            local_resource = base_production * terrain_production_scale
                           * std::max(0.0, -terrain_potential_at_particle[i]);
        }
        if (river_resource_enabled && river_proximity_at_particle != nullptr && local_resource > 0.0) {
            const Real prox = std::max(0.0, river_proximity_at_particle[i]);
            local_resource *= 1.0 + river_resource_strength * std::pow(prox, river_resource_alpha);
        }
        Real production = local_resource * eps[i] * dt;

        if (density_factor != nullptr) {
            production *= density_factor[i];
        }

        Real consumption = consumption_rate * dt;
        Real decay = wealth_decay_rate * std::max(0.0, w[i]) * dt;
        w[i] += production - consumption - decay;
    }
}

Index apply_survival_threshold(
    ParticleData& particles,
    Real threshold
) {
    Index deaths = 0;
    const Index n = particles.count();

    #pragma omp parallel for schedule(static) reduction(+:deaths) if(n > 256)
    for (Index i = 0; i < n; ++i) {
        if (particles.status(i) == ParticleStatus::Alive && particles.wealth(i) < threshold) {
            particles.mark_dead(i);
            ++deaths;
        }
    }

    return deaths;
}

} // namespace politeia
