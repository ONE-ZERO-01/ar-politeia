#include "core/config.hpp"
#include "core/particle_data.hpp"
#include "interaction/resource_exchange.hpp"

#include <cmath>
#include <iostream>
#include <stdexcept>

namespace {

bool close(double lhs, double rhs, double tolerance = 1e-12) {
    return std::abs(lhs - rhs) <= tolerance;
}

void require(bool condition, const char* message) {
    if (!condition) {
        throw std::runtime_error(message);
    }
}

void test_explicit_channel_config() {
    const auto cfg = politeia::load_config("channel_config.cfg");
    require(close(cfg.terrain_scale, 2.0), "legacy terrain scale was not parsed");
    require(!cfg.terrain_force_enabled, "terrain force switch was not parsed");
    require(close(cfg.terrain_force_scale, 3.0), "terrain force scale was not parsed");
    require(cfg.terrain_production_enabled, "terrain production switch was not parsed");
    require(
        close(cfg.terrain_production_scale, 4.0),
        "terrain production scale was not parsed"
    );
    require(!cfg.mortality_enabled, "mortality switch was not parsed");
}

void test_production_switch_and_scale() {
    politeia::ParticleData particles(1);
    const auto particle_index = particles.add_particle(
        {0.0, 0.0}, {0.0, 0.0}, 10.0, 1.0, 20.0
    );
    require(particle_index == 0, "unexpected particle index");
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
    require(close(particles.wealth(0), 10.0), "disabled production changed wealth");

    politeia::apply_resource_dynamics(
        particles,
        1.0,
        0.0,
        1.0,
        terrain_potential,
        true,
        4.0
    );
    require(close(particles.wealth(0), 18.0), "production scale was not applied");
}

} // namespace

int main() {
    test_explicit_channel_config();
    test_production_switch_and_scale();
    std::cout << "cycle1 channel tests passed\n";
    return 0;
}
