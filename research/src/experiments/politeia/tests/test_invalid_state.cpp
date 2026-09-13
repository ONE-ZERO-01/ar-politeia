#include "core/particle_data.hpp"

#include <cmath>
#include <iostream>
#include <limits>
#include <stdexcept>

namespace {

using politeia::Real;

void require(bool condition, const char* message) {
    if (!condition) {
        throw std::runtime_error(message);
    }
}

politeia::ParticleData make_single(Real w, Real eps = 1.0) {
    politeia::ParticleData particles(1);
    (void)particles.add_particle({0.0, 0.0}, {0.0, 0.0}, w, eps, 20.0);
    return particles;
}

bool throws_on(const politeia::ParticleData& particles) {
    try {
        politeia::validate_particle_state(particles);
    } catch (const std::runtime_error&) {
        return true;
    }
    return false;
}

// R05: validate_particle_state is pair-independent — an invalid particle with
// no neighbours at all must still fail.
void test_isolated_negative_wealth_fails() {
    auto particles = make_single(-1.0);
    require(throws_on(particles), "isolated negative wealth must fail");
}

void test_isolated_nan_wealth_fails() {
    auto particles = make_single(std::numeric_limits<Real>::quiet_NaN());
    require(throws_on(particles), "isolated NaN wealth must fail");
}

void test_isolated_inf_wealth_fails() {
    auto particles = make_single(std::numeric_limits<Real>::infinity());
    require(throws_on(particles), "isolated +Inf wealth must fail");
}

void test_isolated_negative_ability_fails() {
    auto particles = make_single(1.0, /*eps=*/-0.5);
    require(throws_on(particles), "isolated negative ability must fail");
}

void test_isolated_nan_ability_fails() {
    auto particles = make_single(1.0, std::numeric_limits<Real>::quiet_NaN());
    require(throws_on(particles), "isolated NaN ability must fail");
}

void test_valid_state_passes() {
    auto particles = make_single(1.0, 2.0);
    require(!throws_on(particles), "valid state must not fail");
}

void test_dead_particle_with_bad_wealth_is_ignored() {
    // Only alive particles are validated; a dead particle is skipped.
    auto particles = make_single(1.0);
    particles.set_status(0, politeia::ParticleStatus::Dead);
    particles.w_data()[0] = -5.0;
    require(!throws_on(particles), "dead particles are excluded from validation");
}

} // namespace

int main() {
    test_isolated_negative_wealth_fails();
    test_isolated_nan_wealth_fails();
    test_isolated_inf_wealth_fails();
    test_isolated_negative_ability_fails();
    test_isolated_nan_ability_fails();
    test_valid_state_passes();
    test_dead_particle_with_bad_wealth_is_ignored();
    std::cout << "invalid state failure semantics tests passed\n";
    return 0;
}
