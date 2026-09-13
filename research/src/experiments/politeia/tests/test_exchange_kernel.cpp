#include "core/particle_data.hpp"
#include "domain/cell_list.hpp"
#include "interaction/resource_exchange.hpp"

#include <array>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <utility>

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
    params.reversion_rate = 1.0;
    params.cutoff = 2.5;
    params.ability_saturation_w = 5.0;
    return params;
}

Real run_step(
    politeia::ParticleData& particles,
    politeia::CellList& cells,
    const politeia::ExchangeParams& params,
    Real dt,
    std::uint64_t step,
    std::uint64_t base_seed = 0,
    politeia::ExchangeDiagnostics* diag = nullptr
) {
    cells.build(particles.x_data(), particles.count());
    return politeia::exchange_resources(
        particles, cells, params, dt, nullptr, nullptr, nullptr,
        step, base_seed, diag);
}

void test_equal_state_is_absorbing_with_noise() {
    auto particles = make_pair(5.0, 5.0);
    auto cells = make_cells();
    auto params = make_params(0.003, 0.5);
    (void)run_step(particles, cells, params, 0.01, 0);
    require(close(particles.wealth(0), 5.0), "equal state: particle 0 drifted");
    require(close(particles.wealth(1), 5.0), "equal state: particle 1 drifted");
}

void test_zero_sum_conservation_across_steps() {
    auto particles = make_pair(10.0, 2.0);
    auto cells = make_cells();
    auto params = make_params(0.003, 0.5);
    const Real total = particles.wealth(0) + particles.wealth(1);
    for (std::uint64_t step = 0; step < 200; ++step) {
        (void)run_step(particles, cells, params, 0.01, step);
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
        (void)run_step(particles, cells, params, 0.01, step);
        require(particles.wealth(0) >= 0.0, "particle 0 went negative");
        require(particles.wealth(1) >= 0.0, "particle 1 went negative");
    }
}

void test_mean_reversion_with_ability_tilt() {
    // Candidate C (continuous-time), noise disabled: the mean-reversion term
    // k·(1/2 − share) makes the rich lose toward the mean and the poor gain,
    // while the ability difference still biases the rich particle's share
    // slightly above 1/2 (single dt=0.01 step, so the displacement is small).
    auto particles = make_pair(10.0, 2.0);
    auto cells = make_cells();
    auto params = make_params(0.003, 0.0);
    const Real w0 = particles.wealth(0);
    const Real w1 = particles.wealth(1);
    const Real mean = (w0 + w1) / 2.0;
    (void)run_step(particles, cells, params, 0.01, 0);
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
    (void)run_step(particles, cells, params, 0.01, 0);
    require(
        particles.wealth(0) > 5.0,
        "higher-ability particle did not gain from equal wealth"
    );
    require(
        close(particles.wealth(0) + particles.wealth(1), 10.0, 1e-12),
        "ability-driven exchange is not zero-sum"
    );
}

void test_dt_zero_is_noop() {
    auto particles = make_pair(10.0, 2.0);
    auto cells = make_cells();
    auto params = make_params(0.5, 0.5);
    (void)run_step(particles, cells, params, 0.0, 0);
    require(close(particles.wealth(0), 10.0), "dt=0 changed particle 0 wealth");
    require(close(particles.wealth(1), 2.0), "dt=0 changed particle 1 wealth");
}

void test_multi_particle_zero_sum() {
    politeia::ParticleData particles(8);
    const std::array<std::array<politeia::Real, 2>, 5> positions = {{
        {{0.0, 0.0}},
        {{1.0, 0.0}},
        {{0.5, 0.8}},
        {{1.2, 0.9}},
        {{0.2, 1.1}},
    }};
    const std::array<politeia::Real, 5> wealth = {{10.0, 2.0, 5.0, 1.0, 7.0}};
    const std::array<politeia::Real, 5> eps = {{1.0, 3.0, 2.0, 1.5, 0.5}};
    for (std::size_t i = 0; i < positions.size(); ++i) {
        (void)particles.add_particle(
            {positions[i][0], positions[i][1]},
            {0.0, 0.0},
            wealth[i],
            eps[i],
            20.0
        );
    }
    auto cells = make_cells();
    auto params = make_params(0.5, 0.5);
    const politeia::Real total = 10.0 + 2.0 + 5.0 + 1.0 + 7.0;
    for (std::uint64_t step = 0; step < 100; ++step) {
        (void)run_step(particles, cells, params, 0.01, step);
        politeia::Real now = 0.0;
        for (politeia::Index i = 0; i < particles.count(); ++i) {
            now += particles.wealth(i);
        }
        require(close(now, total, 1e-8), "multi-particle zero-sum conservation violated");
    }
}

void test_deterministic_reproducibility() {
    auto first = make_pair(10.0, 2.0);
    auto second = make_pair(10.0, 2.0);
    auto cells1 = make_cells();
    auto cells2 = make_cells();
    auto params = make_params(0.5, 0.5);
    for (std::uint64_t step = 0; step < 20; ++step) {
        (void)run_step(first, cells1, params, 0.01, step);
        (void)run_step(second, cells2, params, 0.01, step);
    }
    require(close(first.wealth(0), second.wealth(0), 1e-12), "deterministic run 0 mismatch");
    require(close(first.wealth(1), second.wealth(1), 1e-12), "deterministic run 1 mismatch");
}

// --- S02: zero-wealth boundary policy ---

void test_zero_wealth_endpoint_reflows_from_positive_neighbour() {
    // (0, W): the zero-wealth particle is allowed to enter, and the mean
    // reversion + ability drift pulls wealth back from the positive neighbour.
    auto particles = make_pair(0.0, 10.0);
    auto cells = make_cells();
    auto params = make_params(0.003, 0.0);  // noise off for a deterministic sign
    (void)run_step(particles, cells, params, 0.01, 0);
    require(particles.wealth(0) > 0.0, "zero-wealth particle did not receive reflow");
    require(close(particles.wealth(0) + particles.wealth(1), 10.0, 1e-12),
            "zero-wealth reflow broke zero-sum");
}

void test_wealth_endpoint_reflows_to_zero_neighbour() {
    // (W, 0): symmetric case — the second (zero) particle receives reflow.
    auto particles = make_pair(10.0, 0.0);
    auto cells = make_cells();
    auto params = make_params(0.003, 0.0);
    (void)run_step(particles, cells, params, 0.01, 0);
    require(particles.wealth(1) > 0.0, "zero-wealth neighbour did not receive reflow");
    require(close(particles.wealth(0) + particles.wealth(1), 10.0, 1e-12),
            "zero-wealth reflow broke zero-sum");
}

void test_both_zero_wealth_is_noop() {
    auto particles = make_pair(0.0, 0.0);
    auto cells = make_cells();
    auto params = make_params(0.003, 0.5);
    politeia::ExchangeDiagnostics diag;
    (void)run_step(particles, cells, params, 0.01, 0, 0, &diag);
    require(close(particles.wealth(0), 0.0, 1e-15) &&
            close(particles.wealth(1), 0.0, 1e-15),
            "zero-zero pair must stay zero");
    require(diag.active_pairs == 0, "zero-total pair must not be active");
}

void test_negative_wealth_is_declared_not_skipped() {
    auto particles = make_pair(-1.0, 10.0);
    auto cells = make_cells();
    auto params = make_params(0.003, 0.5);
    politeia::ExchangeDiagnostics diag;
    (void)run_step(particles, cells, params, 0.01, 0, 0, &diag);
    require(diag.negative_wealth_encounters == 1,
            "negative-wealth pair must be recorded");
    // No transfer happens (conservation of the declared state), so the
    // positive endpoint is untouched.
    require(close(particles.wealth(1), 10.0, 1e-12),
            "negative-wealth pair must not transfer");

    // R05: the same invalid state must fail business validation even without
    // a neighbour pair — the full-population check is pair-independent.
    bool threw = false;
    try {
        politeia::validate_particle_state(particles);
    } catch (const std::runtime_error&) {
        threw = true;
    }
    require(threw, "validate_particle_state must reject negative wealth");
}

void test_nonfinite_wealth_is_declared_not_silent() {
    // NaN/Inf comparisons are false under <=/<, so the kernel must check
    // finiteness explicitly (R05) and record a non-finite encounter.
    for (politeia::Real bad : {std::numeric_limits<politeia::Real>::quiet_NaN(),
                               std::numeric_limits<politeia::Real>::infinity()}) {
        auto particles = make_pair(bad, 10.0);
        auto cells = make_cells();
        auto params = make_params(0.003, 0.5);
        politeia::ExchangeDiagnostics diag;
        (void)run_step(particles, cells, params, 0.01, 0, 0, &diag);
        require(diag.nonfinite_encounters == 1,
                "non-finite wealth must be recorded as a non-finite encounter");
        require(close(particles.wealth(1), 10.0, 1e-12),
                "non-finite wealth must not corrupt the neighbour");
    }
}

// --- S07: stable-GID + seed sub-stream ---

void test_exchange_seed_changes_stream() {
    // Different base seeds must resample the exchange stream (WP2.1): with
    // noise on, the same pair under two seeds drifts apart.
    auto run_with_seed = [](std::uint64_t seed) {
        auto particles = make_pair(10.0, 2.0);
        auto cells = make_cells();
        auto params = make_params(0.5, 0.5);
        for (std::uint64_t step = 0; step < 50; ++step) {
            (void)run_step(particles, cells, params, 0.01, step, seed);
        }
        return particles.wealth(0);
    };
    const Real wa = run_with_seed(1);
    const Real wb = run_with_seed(2);
    require(!close(wa, wb, 1e-9), "different seeds produced identical exchange stream");
}

void test_exchange_invariant_to_storage_reorder() {
    // Same physical pair (GIDs 100/200) with wealth attached to GID, but the
    // storage order is swapped. The physical particle gid=100 must evolve
    // identically because the per-pair sign depends on stable GIDs, not array
    // indices (S07). Before the fix the noise sign was index-based and this
    // test fails.
    auto run = [](bool swap_storage) {
        politeia::ParticleData particles(2);
        const politeia::Id gid_low = 100;
        const politeia::Id gid_high = 200;
        if (!swap_storage) {
            (void)particles.add_particle_with_gid({0.0, 0.0}, {0.0, 0.0}, 10.0, 1.0, 20.0, gid_low);
            (void)particles.add_particle_with_gid({1.0, 0.0}, {0.0, 0.0}, 2.0, 1.0, 20.0, gid_high);
        } else {
            (void)particles.add_particle_with_gid({0.0, 0.0}, {0.0, 0.0}, 2.0, 1.0, 20.0, gid_high);
            (void)particles.add_particle_with_gid({1.0, 0.0}, {0.0, 0.0}, 10.0, 1.0, 20.0, gid_low);
        }
        auto cells = make_cells();
        auto params = make_params(0.003, 0.5);
        (void)run_step(particles, cells, params, 0.01, 0, 42);
        return particles.wealth(particles.gid_to_local(gid_low));
    };
    const Real wa = run(false);
    const Real wb = run(true);
    require(close(wa, wb, 1e-12),
            "storage reorder changed the physical pair's transfer");
}

// --- R08: locked-parameter boundary diagnostics ---

void test_exchange_enabled_false_is_noop() {
    auto particles = make_pair(10.0, 2.0);
    auto cells = make_cells();
    auto params = make_params(0.5, 0.5);
    params.enabled = false;  // R04 master switch
    politeia::ExchangeDiagnostics diag;
    const Real transferred = run_step(particles, cells, params, 0.01, 0, 42, &diag);
    require(transferred == 0.0, "disabled exchange must transfer nothing");
    require(close(particles.wealth(0), 10.0, 1e-15)
            && close(particles.wealth(1), 2.0, 1e-15),
            "disabled exchange must not change wealth");
    require(diag.active_pairs == 0 && diag.nonzero_transfer_pairs == 0,
            "disabled exchange must record no activity");
}

void test_nonzero_transfer_pairs_distinct_from_active_pairs() {
    // Locked params k=1, eta=0.5, noise=0.05 (R08). Equal state enters the
    // computation (active) but transfers nothing (dw=0); unequal state does both.
    {
        auto particles = make_pair(5.0, 5.0);
        auto cells = make_cells();
        auto params = make_params(0.5, 0.05);
        politeia::ExchangeDiagnostics diag;
        (void)run_step(particles, cells, params, 0.01, 0, 42, &diag);
        require(diag.active_pairs == 1, "equal pair must enter the computation");
        require(diag.nonzero_transfer_pairs == 0, "equal pair must transfer zero");
    }
    {
        auto particles = make_pair(10.0, 2.0);
        auto cells = make_cells();
        auto params = make_params(0.5, 0.05);
        politeia::ExchangeDiagnostics diag;
        (void)run_step(particles, cells, params, 0.01, 0, 42, &diag);
        require(diag.active_pairs == 1, "unequal pair must enter the computation");
        require(diag.nonzero_transfer_pairs == 1, "unequal pair must transfer");
    }
}

} // namespace

int main() {
    test_equal_state_is_absorbing_with_noise();
    test_zero_sum_conservation_across_steps();
    test_non_negative_under_strong_noise();
    test_mean_reversion_with_ability_tilt();
    test_ability_diff_drives_direction();
    test_dt_zero_is_noop();
    test_multi_particle_zero_sum();
    test_deterministic_reproducibility();
    test_zero_wealth_endpoint_reflows_from_positive_neighbour();
    test_wealth_endpoint_reflows_to_zero_neighbour();
    test_both_zero_wealth_is_noop();
    test_negative_wealth_is_declared_not_skipped();
    test_nonfinite_wealth_is_declared_not_silent();
    test_exchange_seed_changes_stream();
    test_exchange_invariant_to_storage_reorder();
    test_exchange_enabled_false_is_noop();
    test_nonzero_transfer_pairs_distinct_from_active_pairs();
    std::cout << "exchange kernel invariant tests passed\n";
    return 0;
}
