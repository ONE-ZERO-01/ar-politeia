#include "core/config.hpp"
#include "core/particle_data.hpp"
#include "interaction/resource_exchange.hpp"

#include <cassert>
#include <cmath>
#include <iostream>

namespace {

bool close(double lhs, double rhs, double tolerance = 1e-12) {
    return std::abs(lhs - rhs) <= tolerance;
}

void test_explicit_channel_config() {
    const auto cfg = politeia::load_config("channel_config.cfg");
    assert(close(cfg.terrain_scale, 2.0));
    assert(!cfg.terrain_force_enabled);
    assert(close(cfg.terrain_force_scale, 3.0));
    assert(cfg.terrain_production_enabled);
    assert(close(cfg.terrain_production_scale, 4.0));
    assert(!cfg.mortality_enabled);
}

void test_production_switch_and_scale() {
    politeia::ParticleData particles(1);
    const auto particle_index = particles.add_particle(
        {0.0, 0.0}, {0.0, 0.0}, 10.0, 1.0, 20.0
    );
    assert(particle_index == 0);
    const politeia::Real terrain_potential[] = {-2.0};

    politeia::apply_resource_dynamics(
        particles,
        1.0,
        0.0,
        1.0,
        terrain_potential,
        false,
        4.0
    );
    assert(close(particles.wealth(0), 10.0));

    politeia::apply_resource_dynamics(
        particles,
        1.0,
        0.0,
        1.0,
        terrain_potential,
        true,
        4.0
    );
    assert(close(particles.wealth(0), 18.0));
}

} // namespace

int main() {
    test_explicit_channel_config();
    test_production_switch_and_scale();
    std::cout << "cycle1 channel tests passed\n";
    return 0;
}
