#include "core/particle_data.hpp"
#include "domain/cell_list.hpp"
#include "interaction/culture_dynamics.hpp"
#include "interaction/loyalty.hpp"
#include "population/reproduction.hpp"
#include "population/plague.hpp"
#include "population/carrying_capacity.hpp"
#include "climate/climate_grid.hpp"
#include "force/terrain_loader.hpp"
#include "analysis/order_params.hpp"
#include "analysis/phase_transition.hpp"
#include "analysis/polity.hpp"

#include <cmath>
#include <cstdint>
#include <iostream>
#include <random>
#include <stdexcept>
#include <vector>

namespace {

bool close(double lhs, double rhs, double tolerance = 1e-12) {
    return std::abs(lhs - rhs) <= tolerance;
}

void require(bool condition, const char* message) {
    if (!condition) {
        throw std::runtime_error(message);
    }
}

politeia::ParticleData make_repro_pair(politeia::Real w0, politeia::Real w1) {
    politeia::ParticleData particles(4, 2);
    (void)particles.add_particle({0.0, 0.0}, {0.0, 0.0}, w0, 1.0, 25.0);
    (void)particles.add_particle({0.2, 0.0}, {0.0, 0.0}, w1, 1.0, 25.0);
    return particles;
}

politeia::CellList make_cells() {
    politeia::CellList cells;
    cells.init(0.0, 10.0, 0.0, 10.0, 2.5);
    return cells;
}

void test_fertility_guards_invalid_window() {
    politeia::ReproductionParams params;
    params.puberty_age = 20.0;
    params.menopause_age = 20.0;
    require(close(politeia::fertility(20.0, params), 0.0),
            "zero-length fertility window should return zero");

    params.menopause_age = 30.0;
    params.peak_fertility_age = 20.0;
    require(close(politeia::fertility(20.0, params), 0.0),
            "peak at puberty should be guarded");
}

void test_culture_correlation_guards_invalid_bins() {
    politeia::ParticleData particles(0, 2);
    require(politeia::compute_culture_correlation(particles, 0, 1.0).empty(),
            "zero bins should return an empty vector");
    require(politeia::compute_culture_correlation(particles, 2, 0.0).empty(),
            "zero max_r should return an empty vector");
}

void test_attempt_reproduction_counts_actual_births() {
    {
        auto particles = make_repro_pair(10.0, 10.0);
        auto cells = make_cells();
        politeia::ReproductionParams params;
        params.max_fertility = 1.0;
        params.gestation_time = 0.0;
        params.nursing_time = 0.0;
        params.mate_range = 3.0;
        params.min_wealth_to_breed = 0.0;
        params.wealth_birth_cost = 0.3;
        params.culture_mate_threshold = 10.0;
        params.mutation_strength = 0.0;
        std::mt19937_64 rng(1);
        cells.build(particles.x_data(), particles.count());
        const auto born = politeia::attempt_reproduction(
            particles, cells, params, 100.0, rng);
        require(born == 1 && particles.count() == 3,
                "eligible parents should produce exactly one child");
    }
    {
        auto particles = make_repro_pair(0.0, 0.0);
        auto cells = make_cells();
        politeia::ReproductionParams params;
        params.max_fertility = 1.0;
        params.gestation_time = 0.0;
        params.nursing_time = 0.0;
        params.mate_range = 3.0;
        params.min_wealth_to_breed = 0.0;
        params.wealth_birth_cost = 0.3;
        params.culture_mate_threshold = 10.0;
        params.mutation_strength = 0.0;
        std::mt19937_64 rng(1);
        cells.build(particles.x_data(), particles.count());
        const auto born = politeia::attempt_reproduction(
            particles, cells, params, 100.0, rng);
        require(born == 0 && particles.count() == 2,
                "zero-wealth parents should not count a birth");
    }
}

void test_process_succession_distributes_estate_completely() {
    politeia::ParticleData particles(3, 2);
    const auto leader = particles.add_particle(
        {0.0, 0.0}, {0.0, 0.0}, 100.0, 1.0, 50.0);
    const auto heir = particles.add_particle(
        {0.0, 0.0}, {0.0, 0.0}, 0.0, 1.0, 20.0);
    (void)leader;
    particles.superior(heir) = particles.global_id(0);
    particles.loyalty(heir) = 0.5;

    politeia::LoyaltyParams params;
    const auto successions = politeia::process_succession(
        particles, {0}, params);
    require(successions == 1, "one succession should be processed");
    require(close(particles.wealth(0), 0.0), "dead leader estate not cleared");
    require(close(particles.wealth(1), 100.0),
            "single heir should receive the full estate");
}

void test_one_cell_environment_grids_are_finite() {
    politeia::ClimateGrid climate;
    climate.generate_procedural(1, 1, 0.0, 0.0, 1.0, 1.0, nullptr);
    const auto cell = climate.cell_at(0.5, 0.5);
    require(std::isfinite(cell.temperature) && std::isfinite(cell.precipitation),
            "one-cell climate query should be finite");

    politeia::TerrainGrid terrain;
    terrain.generate_synthetic(1, 2, 0.0, 0.0, 2.0, 2.0, "valley");
    require(terrain.nrows() == 1 && terrain.ncols() == 2,
            "one-row terrain dimensions should be preserved");
    require(std::isfinite(terrain.h_min()) && std::isfinite(terrain.h_max()),
            "one-row terrain extrema should be finite");
}

void test_analysis_guards_and_polity_depth() {
    politeia::ParticleData particles(0, 2);
    require(politeia::compute_wealth_histogram(particles, 0, 1.0).empty(),
            "zero-bin wealth histogram should be empty");

    politeia::OrderParamTracker tracker("guard", 0, 0.0, 0.0);
    require(!tracker.push(0.0, 0.0),
            "zero-window phase tracker should not trigger");

    politeia::ParticleData chain(3, 2);
    const auto root = chain.add_particle({0.0, 0.0}, {0.0, 0.0}, 1.0, 1.0, 20.0);
    const auto mid = chain.add_particle({0.0, 0.0}, {0.0, 0.0}, 1.0, 1.0, 20.0);
    const auto leaf = chain.add_particle({0.0, 0.0}, {0.0, 0.0}, 1.0, 1.0, 20.0);
    chain.superior(mid) = chain.global_id(root);
    chain.superior(leaf) = chain.global_id(mid);

    const auto polities = politeia::detect_polities(chain);
    require(polities.size() == 1, "chain should form one polity");
    require(polities[0].depth == 2, "three-particle chain should have depth two");
}

void test_population_guards() {
    politeia::ParticleData empty(0, 2);
    politeia::CellList cells;
    cells.init(0.0, 1.0, 0.0, 1.0, 1.0);
    const auto density = politeia::compute_local_density(empty, cells, 0.0);
    require(density.empty(), "empty population density should be empty");

    politeia::PlagueManager manager;
    manager.init(0, 0);
    std::mt19937_64 rng(1);
    require(manager.update(empty, cells, politeia::PlagueParams{}, 0.0, 0.1, rng) == 0,
            "empty population plague update should be zero");
}

} // namespace

int main() {
    test_fertility_guards_invalid_window();
    test_culture_correlation_guards_invalid_bins();
    test_attempt_reproduction_counts_actual_births();
    test_process_succession_distributes_estate_completely();
    test_one_cell_environment_grids_are_finite();
    test_analysis_guards_and_polity_depth();
    test_population_guards();
    std::cout << "module invariant tests passed\n";
    return 0;
}
