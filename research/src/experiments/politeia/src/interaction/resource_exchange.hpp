#pragma once

#include "core/types.hpp"
#include "core/particle_data.hpp"
#include "domain/cell_list.hpp"

namespace politeia {

struct ExchangeParams {
    Real exchange_rate = 0.003; // η: fraction of min(w_i,w_j) exchanged per interaction
    Real cutoff = 2.5;         // 交互距离（与人际交互力的社交视野半径一致）
    bool terrain_barrier_enabled = false;
    Real terrain_barrier_scale = 5.0;  // h0: larger = weaker barrier effect
    bool river_exchange_enabled = false;
    Real river_exchange_strength = 0.5;
    Real ability_saturation_w = 5.0;   // w_ref: wealth half-saturation for diminishing returns
                                       // A_i = ε_i × w_i/(w_i + w_ref)
                                       // Set 0 to disable (use A_i = ε_i × w_i)
};

/// Perform symmetric resource exchange between neighboring particles.
///
/// Rule (research proposal §2.6.2):
///   A_i = w_i × f(ε_i),  A_j = w_j × f(ε_j)
///   Δw = η × (A_i − A_j) / (A_i + A_j) × min(w_i, w_j)
///
/// This rule is symmetric under label exchange i↔j.
/// Inequality emerges from state differences, not from biased rules.
///
namespace detail { class InteractionNetworkBase; }

/// Forward declaration for optional network recording.
class InteractionNetwork;

/// Returns total absolute wealth transferred (diagnostic).
/// If network is non-null, records transfers for hierarchy detection.
/// terrain_potential_at_particle: per-particle terrain potential for barrier computation (optional).
[[nodiscard]] Real exchange_resources(
    ParticleData& particles,
    const CellList& cells,
    const ExchangeParams& params,
    class InteractionNetwork* network = nullptr,
    const Real* terrain_potential_at_particle = nullptr,
    const Real* river_proximity_at_particle = nullptr
);

/// Apply per-step resource consumption and terrain-based production.
///
/// Each particle consumes a fixed amount per step and gains from local
/// terrain resource rate R(x).
///   dw = R(x) × f(ε) × dt − consumption × dt
/// When density_factor is provided (size N, values in [0,1]),
/// production is scaled by density_factor[i] = min(1, K/ρ).
void apply_resource_dynamics(
    ParticleData& particles,
    Real dt,
    Real consumption_rate,
    Real base_production,
    const Real* terrain_potential_at_particle,
    bool terrain_production_enabled = true,
    Real terrain_production_scale = 1.0,
    const Real* density_factor = nullptr,
    const Real* river_proximity_at_particle = nullptr,
    bool river_resource_enabled = false,
    Real river_resource_strength = 0.0,
    Real river_resource_alpha = 1.0,
    Real wealth_decay_rate = 0.0
);

/// Mark particles with w < threshold as dead.
/// Returns number of particles marked dead.
[[nodiscard]] Index apply_survival_threshold(
    ParticleData& particles,
    Real threshold
);

} // namespace politeia
