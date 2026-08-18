#pragma once

#include "core/types.hpp"
#include "core/particle_data.hpp"
#include "domain/cell_list.hpp"
#include "force/social_force.hpp"
#include "force/terrain_force.hpp"
#include "force/terrain_loader.hpp"

#include <random>

namespace politeia {

struct IntegratorState {
    Real kinetic_energy = 0.0;
    Real social_potential = 0.0;   // 人际交互势能
    Real terrain_potential = 0.0;

    [[nodiscard]] Real total_energy() const noexcept {
        return kinetic_energy + social_potential + terrain_potential;
    }
};

/// BBK (Brünger-Brooks-Karplus) integrator for Langevin dynamics.
///
/// Equation of motion:
///   m·q̈ = F(q) − γ·q̇ + ξ(t)
///   ⟨ξ(t)·ξ(t')⟩ = 2·γ·m·k_B·T·δ(t−t')
///
/// When γ=0 and T=0, this reduces to standard Velocity-Verlet.
/// Phase 1: use γ=0, T=0 for deterministic dynamics (energy conservation test).
/// Phase 3: enable γ>0, T>0 for full Langevin dynamics.
class LangevinIntegrator {
public:
    /// @param dt       Time step
    /// @param mass     Particle mass
    /// @param friction Friction coefficient γ (0 = no dissipation)
    /// @param temperature Temperature T (0 = no random force)
    /// @param social   人际空间交互力参数
    /// @param terrain  Terrain potential parameters
    /// @param seed     RNG seed
    LangevinIntegrator(
        Real dt, Real mass, Real friction, Real temperature,
        SocialForceParams social, TerrainParams terrain,
        Real domain_xmin, Real domain_xmax,
        Real domain_ymin, Real domain_ymax,
        std::uint64_t seed = 42,
        const TerrainGrid* terrain_grid = nullptr,
        Real terrain_scale = 1.0
    );

    /// Perform one BBK time step. Returns energy diagnostics.
    [[nodiscard]] IntegratorState step(ParticleData& particles, CellList& cells);

    void set_dt(Real dt) noexcept { dt_ = dt; }
    void set_friction(Real gamma) noexcept { friction_ = gamma; update_noise_amplitude(); }
    void set_temperature(Real T) noexcept { temperature_ = T; update_noise_amplitude(); }

    [[nodiscard]] Real dt() const noexcept { return dt_; }
    [[nodiscard]] Real friction() const noexcept { return friction_; }
    [[nodiscard]] Real temperature() const noexcept { return temperature_; }
    [[nodiscard]] bool is_deterministic() const noexcept { return friction_ == 0.0 && temperature_ == 0.0; }

private:
    Real dt_;
    Real mass_;
    Real inv_mass_;
    Real friction_;       // γ
    Real temperature_;    // T
    Real noise_amp_;      // σ = sqrt(2·γ·m·k_B·T·dt)

    SocialForceParams social_;
    TerrainParams terrain_;
    const TerrainGrid* terrain_grid_ = nullptr;
    Real terrain_scale_ = 1.0;

    Real domain_xmin_, domain_xmax_;
    Real domain_ymin_, domain_ymax_;

    std::mt19937_64 rng_;
    std::normal_distribution<Real> normal_{0.0, 1.0};

    void update_noise_amplitude();

    std::pair<Real, Real> compute_forces(ParticleData& particles, CellList& cells);
    [[nodiscard]] Real compute_kinetic(const ParticleData& particles) const;
    void apply_boundary(ParticleData& particles) const;
};

} // namespace politeia
