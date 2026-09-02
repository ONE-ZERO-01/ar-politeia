#include "core/particle_data.hpp"
#include "domain/cell_list.hpp"
#include "interaction/resource_exchange.hpp"

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

/// Two particles within interaction range; n=2 exercises the serial
/// `for_each_pair` path (n < 256), which updates wealth in place.
politeia::ParticleData make_pair(Real w0, Real w1, Real eps0 = 1.0, Real eps1 = 1.0) {
    politeia::ParticleData particles(2);
    (void)particles.add_particle({0.0, 0.0}, {0.0, 0.0}, w0, eps0, 20.0);
    (void)particles.add_particle({1.0, 0.0}, {0.0, 0.0}, w1, eps1, 20.0);
    return particles;
}

politeia::CellList make_cells() {
    politeia::CellList cells;
    cells.init(0.0, 100.0, 0.0, 100.0, 2.5);
    return cells;
}

politeia::ExchangeParams make_params(Real rate, Real noise) {
    politeia::ExchangeParams params;
    params.exchange_rate = rate;
    params.noise_strength = noise;
    params.cutoff = 2.5;
    params.ability_saturation_w = 5.0;
    return params;
}

Real run_step(
    politeia::ParticleData& particles,
    politeia::CellList& cells,
    const politeia::ExchangeParams& params,
    std::uint64_t step
) {
    cells.build(particles.x_data(), particles.count());
    return politeia::exchange_resources(particles, cells, params, nullptr, nullptr, nullptr, step);
}

void test_equal_state_is_absorbing_with_noise() {
    auto particles = make_pair(5.0, 5.0);
    auto cells = make_cells();
    auto params = make_params(0.003, 0.5);
    (void)run_step(particles, cells, params, 0);
    require(close(particles.wealth(0), 5.0), "equal state: particle 0 drifted");
    require(close(particles.wealth(1), 5.0), "equal state: particle 1 drifted");
}

void test_zero_sum_conservation_across_steps() {
    auto particles = make_pair(10.0, 2.0);
    auto cells = make_cells();
    auto params = make_params(0.003, 0.5);
    const Real total = particles.wealth(0) + particles.wealth(1);
    for (std::uint64_t step = 0; step < 200; ++step) {
        (void)run_step(particles, cells, params, step);
        const Real now = particles.wealth(0) + particles.wealth(1);
        require(
            close(now, total, 1e-9),
            "zero-sum conservation violated across steps"
        );
    }
}

void test_non_negative_under_strong_noise() {
    auto particles = make_pair(1.0, 1000.0);
    auto cells = make_cells();
    auto params = make_params(0.0, 2.0);
    for (std::uint64_t step = 0; step < 200; ++step) {
        (void)run_step(particles, cells, params, step);
        require(particles.wealth(0) >= 0.0, "particle 0 went negative");
        require(particles.wealth(1) >= 0.0, "particle 1 went negative");
    }
}

void test_mean_reversion_with_ability_tilt() {
    // Candidate C, noise disabled: the equal-split baseline mean-reverts (rich
    // loses toward the mean, poor gains toward the mean), while the ability
    // difference tilts the rich particle's share slightly above 1/2.
    auto particles = make_pair(10.0, 2.0);
    auto cells = make_cells();
    auto params = make_params(0.003, 0.0);
    const Real w0 = particles.wealth(0);
    const Real w1 = particles.wealth(1);
    const Real mean = (w0 + w1) / 2.0;
    (void)run_step(particles, cells, params, 0);
    require(particles.wealth(0) < w0, "rich particle did not lose toward mean");
    require(particles.wealth(1) > w1, "poor particle did not gain toward mean");
    require(particles.wealth(0) > mean, "ability tilt did not keep rich share above 1/2");
    require(
        close(particles.wealth(0) + particles.wealth(1), w0 + w1, 1e-12),
        "drift-only exchange is not zero-sum"
    );
}

void test_ability_diff_drives_direction() {
    // Equal wealth but different ability: the higher-ability agent should gain.
    auto particles = make_pair(5.0, 5.0, /*eps0=*/3.0, /*eps1=*/1.0);
    auto cells = make_cells();
    auto params = make_params(0.003, 0.0);
    (void)run_step(particles, cells, params, 0);
    require(
        particles.wealth(0) > 5.0,
        "higher-ability particle did not gain from equal wealth"
    );
    require(
        close(particles.wealth(0) + particles.wealth(1), 10.0, 1e-12),
        "ability-driven exchange is not zero-sum"
    );
}

} // namespace

int main() {
    test_equal_state_is_absorbing_with_noise();
    test_zero_sum_conservation_across_steps();
    test_non_negative_under_strong_noise();
    test_mean_reversion_with_ability_tilt();
    test_ability_diff_drives_direction();
    std::cout << "exchange kernel invariant tests passed\n";
    return 0;
}
