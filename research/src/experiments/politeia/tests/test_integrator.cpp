#include "core/particle_data.hpp"
#include "domain/cell_list.hpp"
#include "force/social_force.hpp"
#include "force/terrain_force.hpp"
#include "integrator/langevin_integrator.hpp"

#include <cmath>
#include <cstdint>
#include <iostream>
#include <stdexcept>

namespace {

using politeia::Real;

bool close(double lhs, double rhs, double tolerance = 1e-12) {
    return std::abs(lhs - rhs) <= tolerance;
}

void require(bool condition, const char* message) {
    if (!condition) {
        throw std::runtime_error(message);
    }
}

/// S06 regression: with T=0 (noise disabled) and friction>0, a force-free
/// particle's momentum must decay every step. The closed-form BBK factor is
///   p_{n+1} = p_n · (1 − γ·dt/2)²
/// per step, so the OpenMP no-noise branch must include the −(dt/2)·γ·p term.
/// Before the fix, the OpenMP branch dropped friction, leaving |p| constant.
void test_free_particle_momentum_decay_no_noise() {
    const Real dt = 0.01;
    const Real friction = 1.0;
    const Real mass = 1.0;

    politeia::LangevinIntegrator integrator(
        dt, mass, friction, /*temperature=*/0.0,
        politeia::SocialForceParams{0.0, 1.0, 2.5},  // epsilon=0 → no social force
        politeia::TerrainParams{},                    // empty wells → no terrain force
        0.0, 100.0, 0.0, 100.0,
        /*seed=*/42, nullptr, 1.0);

    politeia::ParticleData particles(2);
    (void)particles.add_particle({50.0, 50.0}, {1.0, 0.0}, 5.0, 1.0, 20.0);

    politeia::CellList cells;
    cells.init(0.0, 100.0, 0.0, 100.0, 2.5);

    const Real p0 = 1.0;
    const Real factor = (1.0 - 0.5 * friction * dt);
    const Real per_step = factor * factor;  // (1 − γ·dt/2)²

    Real prev = p0;
    const std::uint64_t steps = 100;
    for (std::uint64_t s = 0; s < steps; ++s) {
        (void)integrator.step(particles, cells);
        const Real px = particles.momentum(0)[0];
        const Real py = particles.momentum(0)[1];
        require(std::abs(py) < 1e-15, "y momentum should stay zero");
        require(px < prev * (1.0 - 1e-12),
                "momentum did not decay (friction missing)");
        prev = px;
    }

    const Real expected = p0 * std::pow(per_step, static_cast<double>(steps));
    const Real actual = particles.momentum(0)[0];
    require(close(actual, expected, 1e-9),
            "momentum decay does not match closed-form BBK factor");
}

void test_free_particle_no_friction_no_damping() {
    // γ=0, T=0: pure Velocity-Verlet, momentum must be exactly conserved.
    politeia::LangevinIntegrator integrator(
        0.01, 1.0, /*friction=*/0.0, /*temperature=*/0.0,
        politeia::SocialForceParams{0.0, 1.0, 2.5},
        politeia::TerrainParams{},
        0.0, 100.0, 0.0, 100.0,
        /*seed=*/42, nullptr, 1.0);

    politeia::ParticleData particles(2);
    (void)particles.add_particle({50.0, 50.0}, {1.0, 0.5}, 5.0, 1.0, 20.0);

    politeia::CellList cells;
    cells.init(0.0, 100.0, 0.0, 100.0, 2.5);

    for (std::uint64_t s = 0; s < 50; ++s) {
        (void)integrator.step(particles, cells);
        const auto p = particles.momentum(0);
        require(close(p[0], 1.0, 1e-12) && close(p[1], 0.5, 1e-12),
                "frictionless momentum not conserved");
    }
}

} // namespace

int main() {
    test_free_particle_momentum_decay_no_noise();
    test_free_particle_no_friction_no_damping();
    std::cout << "integrator tests passed\n";
    return 0;
}
