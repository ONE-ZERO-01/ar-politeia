/// @file resource_exchange.cpp
/// @brief 对称资源交换规则、资源产出/消耗、生存阈值
///
/// 物理背景（研究方案 §2.6.2）：
///   交换规则必须是标签对称的：交换 i↔j 后结果只变符号。
///   不平等不是规则偏袒产生的，而是从状态差异中自发涌现的。
///
/// 交换公式（Cycle 3，候选 C，连续时间均分回复再分配）：
///   A_i = w_i × ε_i / (w_i + w_ref)     （饱和能力，A 严格单调增）
///   D_ij = (A_i − A_j) / (A_i + A_j)
///   share = w_i/(w_i+w_j)
///   share' = share + dt·[k·(1/2−share) + η_d·D_ij] + √dt·η_n·|D_ij|·s_ij
///   w_i' = share'·(w_i+w_j),  w_j' = (1−share')·(w_i+w_j)
///
/// 物理类比：引力 F=Gm1m2/r² 也是完全对称的，但大质量体依然吸引更多物质。
/// 同理，交换规则对称，但能力强者自然获益更多。
/// 与旧核（Δw ∝ min(w_i,w_j)）的区别：转移量 ∝ 总财富 (w_i+w_j)，
/// 财富悬殊时涨落仍充分作用，漂移—扩散平衡产生非平凡稳态。
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

/// Deterministic antisymmetric sign for a pair at time step `step`, keyed by
/// the particles' stable global IDs (gi, gj) and a per-stream seed (S07).
///
/// Returns s with s(i,j) = −s(j,i), reproducible across runs, and independent
/// of the traversal direction — so the OpenMP `for_neighbors_of` path (which
/// visits each pair from both endpoints) stays exactly zero-sum. Using stable
/// GIDs (not array indices) keeps the per-pair draw invariant under storage
/// reordering, migration and restart; mixing in `seed` makes distinct
/// replicate_seed runs resample the exchange stream independently.
inline Real antisymmetric_sign(std::uint64_t gi, std::uint64_t gj,
                               std::uint64_t step, std::uint64_t seed) {
    const std::uint64_t lo = (gi < gj) ? gi : gj;
    const std::uint64_t hi = (gi < gj) ? gj : gi;
    const std::uint64_t key = splitmix64(seed ^ lo)
                            ^ (splitmix64(hi) * 0x9e3779b97f4a7c15ULL)
                            ^ (step * 0xd6e8feb86659fd93ULL);
    const std::uint64_t r = splitmix64(key);
    const Real mag = ((r >> 63) & 1ULL) ? 1.0 : -1.0;
    return (gi < gj) ? mag : -mag;
}

/// Exchange stream identifier: mixed with the base seed so exchange draws use
/// their own sub-stream, independent of motion/population streams (WP2.1).
constexpr std::uint64_t EXCHANGE_STREAM_ID = 0x9e3779b97f4a7c15ULL;

} // namespace

Real exchange_resources(
    ParticleData& particles,
    const CellList& cells,
    const ExchangeParams& params,
    Real dt,
    InteractionNetwork* network,
    const Real* terrain_potential_at_particle,
    const Real* river_proximity_at_particle,
    std::uint64_t step,
    std::uint64_t base_seed,
    ExchangeDiagnostics* diag
) {
    // R04: when exchange is disabled the kernel is a strict no-op — no drift,
    // no noise, no reversion, no network recording. This is the single source
    // of truth for "no-exchange" control conditions.
    if (!params.enabled) {
        return 0.0;
    }

    const Real cutoff_sq = params.cutoff * params.cutoff;
    const Real eta = params.exchange_rate;
    const Real eta_n = params.noise_strength;
    const Real k = params.reversion_rate;
    const Real sqrt_dt = std::sqrt(dt);
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

    // Per-stream exchange seed (S07): exchange draws get their own sub-stream,
    // independent of motion/population streams, keyed by the base seed.
    const std::uint64_t stream_seed = base_seed ^ EXCHANGE_STREAM_ID;

    // Candidate C (Cycle 3): multiplicative reallocation with serial in-place
    // updates. share ∈ [0,1] keeps both endpoints non-negative and each pair
    // exactly zero-sum, eliminating the accumulated-clamp negative-wealth bug
    // of the candidate-B OpenMP dw_buf path. The perturbation is proportional
    // to total wealth (w_i+w_j), so it stays effective even when the wealth
    // gap is large — this is what yields a non-trivial steady state.
    cells.for_each_pair(x, n, cutoff_sq,
        [&](Index i, Index j, Real dx, Real dy, Real r2) {
            if (particles.status(i) != ParticleStatus::Alive) return;
            if (particles.status(j) != ParticleStatus::Alive) return;

            const Real wi = w[i];
            const Real wj = w[j];

            // R05: finiteness first — NaN/Inf comparisons are false under <=/<
            // so they would otherwise slip through to the arithmetic below.
            if (!std::isfinite(wi) || !std::isfinite(wj)
                || !std::isfinite(eps[i]) || !std::isfinite(eps[j])) {
                if (diag) ++diag->nonfinite_encounters;
                return;
            }
            // Negative wealth/ability is a declared error, checked before the
            // zero-total early-out so (-2,1)/(-1,-1) are not silently skipped.
            if (wi < 0.0 || wj < 0.0 || eps[i] < 0.0 || eps[j] < 0.0) {
                if (diag) ++diag->negative_wealth_encounters;
                return;
            }
            const Real total = wi + wj;

            // S02 boundary policy: only a non-positive total is a no-op. A
            // single zero endpoint is allowed to enter — share ∈ [0,1] keeps
            // both endpoints valid — so a positive neighbour can drive reflow.
            if (total <= 0.0) return;

            Real Ai, Aj;
            if (use_saturation) {
                Ai = eps[i] * wi / (wi + w_ref);
                Aj = eps[j] * wj / (wj + w_ref);
            } else {
                Ai = wi * eps[i];
                Aj = wj * eps[j];
            }
            const Real A_sum = Ai + Aj;
            if (A_sum < 1e-15) {
                if (diag) ++diag->degenerate_ability_encounters;
                return;
            }

            const Real D = (Ai - Aj) / A_sum;
            const Real absD = std::abs(D);
            const Real s = antisymmetric_sign(
                static_cast<std::uint64_t>(particles.global_id(i)),
                static_cast<std::uint64_t>(particles.global_id(j)),
                step, stream_seed);

            // Continuous-time mean-reverting reallocation (candidate C,
            // dt-convergent): drift is O(dt), fluctuation is O(sqrt(dt)).
            // share' = share + dt·[k·(1/2 − share) + η_d·D] + sqrt(dt)·η_n·|D|·s
            const Real share0 = wi / total;
            Real drift = k * (0.5 - share0) + eta * D;
            Real noise = eta_n * absD * s;

            if (barrier) {
                Real delta_h = std::abs(terrain_potential_at_particle[i]
                                      - terrain_potential_at_particle[j]);
                const Real atten = std::exp(-delta_h * inv_barrier_scale);
                drift *= atten;
                noise *= atten;
            }
            if (river_bonus) {
                const Real prox = std::min(
                    std::max(0.0, river_proximity_at_particle[i]),
                    std::max(0.0, river_proximity_at_particle[j])
                );
                const Real boost = 1.0 + params.river_exchange_strength * prox;
                drift *= boost;
                noise *= boost;
            }

            Real share = share0 + dt * drift + sqrt_dt * noise;
            if (share < 0.0) { share = 0.0; if (diag) ++diag->clamp_events; }
            if (share > 1.0) { share = 1.0; if (diag) ++diag->clamp_events; }

            const Real wi_new = share * total;
            const Real dw = wi_new - wi;

            w[i] = wi_new;
            w[j] = total - wi_new;

            if (diag) ++diag->active_pairs;
            const Real dw_abs = std::abs(dw);
            if (diag && dw_abs > 1e-15) ++diag->nonzero_transfer_pairs;

            if (network && dw_abs > 1e-15) {
                network->record_transfer(i, j, dw);
            }
            total_transferred += dw_abs;
        }
    );

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
