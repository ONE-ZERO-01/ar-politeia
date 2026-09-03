#include "core/config.hpp"
#include "core/particle_data.hpp"
#include "domain/cell_list.hpp"
#include "domain/morton.hpp"
#include "force/terrain_loader.hpp"
#include "integrator/langevin_integrator.hpp"
#include "interaction/resource_exchange.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <random>
#include <set>
#include <stdexcept>
#include <string>
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

std::filesystem::path temp_config_path() {
    return std::filesystem::temp_directory_path() / "politeia_active_path_test.cfg";
}

void test_config_parses_cycle3_exchange_keys() {
    const auto path = temp_config_path();
    {
        std::ofstream out(path);
        out << "domain_xmin = 0\n"
            << "domain_xmax = 10\n"
            << "domain_ymin = 0\n"
            << "domain_ymax = 10\n"
            << "exchange_noise_strength = 0.05\n"
            << "exchange_reversion_rate = 1.25\n"
            << "culture_enabled = false\n"
            << "technology_enabled = false\n";
    }
    const auto cfg = politeia::load_config(path.string());
    std::filesystem::remove(path);
    require(close(cfg.exchange_noise_strength, 0.05), "exchange noise not parsed");
    require(close(cfg.exchange_reversion_rate, 1.25), "reversion rate not parsed");
    require(!cfg.culture_enabled, "culture_enabled should be false");
    require(!cfg.technology_enabled, "technology_enabled should be false");
}

void test_particle_data_add_compact_alive_dead() {
    politeia::ParticleData particles(4, 2, 1);
    particles.set_id_seed(0);
    const politeia::Id id0 = particles.global_id(particles.add_particle(
        {0.0, 0.0}, {0.0, 0.0}, 1.0, 1.0, 20.0));
    const politeia::Id id1 = particles.global_id(particles.add_particle(
        {1.0, 0.0}, {0.0, 0.0}, 2.0, 1.0, 21.0));
    (void)particles.add_particle({2.0, 0.0}, {0.0, 0.0}, 3.0, 1.0, 22.0);
    require(id0 != id1, "global IDs should be unique");
    particles.mark_dead(1);
    const auto removed = particles.compact();
    require(removed == 1, "one dead particle should be removed");
    require(particles.count() == 2, "particle count should be two after compact");
    require(particles.status(0) == politeia::ParticleStatus::Alive, "particle 0 should be alive");
    require(particles.status(1) == politeia::ParticleStatus::Alive, "particle 1 should be alive");
}

void test_cell_list_matches_bruteforce() {
    constexpr std::size_t n = 20;
    constexpr politeia::Real cutoff = 1.5;
    std::vector<politeia::Real> x_data(2 * n);
    std::mt19937_64 rng(1234);
    std::uniform_real_distribution<politeia::Real> dist(0.0, 10.0);
    for (std::size_t i = 0; i < n; ++i) {
        x_data[2 * i] = dist(rng);
        x_data[2 * i + 1] = dist(rng);
    }

    politeia::CellList cells;
    cells.init(0.0, 10.0, 0.0, 10.0, cutoff);
    cells.build(x_data.data(), static_cast<politeia::Index>(n));

    std::set<std::pair<politeia::Index, politeia::Index>> actual;
    const auto cutoff_sq = cutoff * cutoff;
    cells.for_each_pair(
        x_data.data(), static_cast<politeia::Index>(n), cutoff_sq,
        [&](politeia::Index i, politeia::Index j, politeia::Real,
            politeia::Real, politeia::Real) {
            actual.insert({i, j});
        }
    );

    std::set<std::pair<politeia::Index, politeia::Index>> expected;
    for (politeia::Index i = 0; i < static_cast<politeia::Index>(n); ++i) {
        for (politeia::Index j = i + 1; j < static_cast<politeia::Index>(n); ++j) {
            const auto dx = x_data[2 * j] - x_data[2 * i];
            const auto dy = x_data[2 * j + 1] - x_data[2 * i + 1];
            const auto r2 = dx * dx + dy * dy;
            if (r2 > 0.0 && r2 < cutoff_sq) {
                expected.insert({i, j});
            }
        }
    }
    require(actual == expected, "cell-list neighbor pairs differ from brute force");
}

void test_morton_roundtrip_and_domain_mapping() {
    constexpr std::array<std::pair<std::uint32_t, std::uint32_t>, 4> grid = {{
        {0, 0}, {3, 7}, {1023, 0}, {7, 1023}
    }};
    for (const auto& [gx, gy] : grid) {
        const auto key = politeia::encode_morton_2d(gx, gy);
        std::uint32_t rx = 0, ry = 0;
        politeia::decode_morton_2d(key, rx, ry);
        require(rx == gx && ry == gy, "Morton encode/decode roundtrip failed");
    }

    politeia::Real x = -1.0, y = -1.0;
    politeia::morton_to_point(
        politeia::point_to_morton(0.0, 0.0, 0.0, 10.0, 0.0, 10.0, 10),
        x, y, 0.0, 10.0, 0.0, 10.0, 10);
    require(x >= 0.0 && x <= 10.0 && y >= 0.0 && y <= 10.0,
            "Morton point mapping escaped the domain");
}

void test_terrain_ascii_y_orientation_and_synthetic() {
    const auto path = std::filesystem::temp_directory_path() / "politeia_active_path_terrain.asc";
    {
        std::ofstream out(path);
        out << "ncols 2\n"
            << "nrows 2\n"
            << "xllcorner 0\n"
            << "yllcorner 0\n"
            << "cellsize 1\n"
            << "NODATA_value -9999\n"
            << "10 20\n"
            << "30 40\n";
    }

    politeia::TerrainGrid grid;
    grid.load_ascii(path.string());
    std::filesystem::remove(path);
    require(grid.nrows() == 2 && grid.ncols() == 2, "ASCII grid dimensions wrong");
    require(close(grid.at(0, 0), 30.0), "southern row not loaded into data row 0");
    require(close(grid.at(1, 1), 20.0), "northern row not loaded into data row 1");
    require(close(grid.h_min(), 10.0), "ASCII h_min wrong");
    require(close(grid.h_max(), 40.0), "ASCII h_max wrong");

    politeia::TerrainGrid synthetic;
    synthetic.generate_synthetic(4, 5, 0.0, 0.0, 4.0, 4.0, "valley");
    require(synthetic.nrows() == 4 && synthetic.ncols() == 5, "synthetic dimensions wrong");
    require(std::isfinite(synthetic.h_min()) && std::isfinite(synthetic.h_max()),
            "synthetic min/max not finite");
    require(synthetic.h_min() < synthetic.h_max(), "valley synthetic min/max invalid");
}

void test_integrator_no_force_and_boundary() {
    politeia::ParticleData particles(1);
    (void)particles.add_particle({0.5, 0.5}, {0.0, 0.0}, 1.0, 1.0, 20.0);
    politeia::CellList cells;
    cells.init(0.0, 1.0, 0.0, 1.0, 1.0);
    politeia::LangevinIntegrator integrator(
        0.1, 1.0, 0.0, 0.0,
        {0.0, 1.0, 1.0},
        {},
        0.0, 1.0, 0.0, 1.0,
        42);
    const auto state = integrator.step(particles, cells);
    require(std::isfinite(state.kinetic_energy), "kinetic energy not finite");
    require(close(particles.position(0)[0], 0.5), "zero-force particle moved in x");
    require(close(particles.position(0)[1], 0.5), "zero-force particle moved in y");

    particles.set_position(0, {0.99, 0.5});
    particles.set_momentum(0, {1.0, 0.0});
    (void)integrator.step(particles, cells);
    require(particles.position(0)[0] <= 1.0, "boundary reflection did not keep x inside");
    require(particles.momentum(0)[0] < 0.0, "boundary reflection did not reverse x momentum");
}

void test_resource_dynamics_formula() {
    politeia::ParticleData particles(1);
    (void)particles.add_particle({0.0, 0.0}, {0.0, 0.0}, 10.0, 1.0, 20.0);
    const politeia::Real potential[] = {-2.0};
    politeia::apply_resource_dynamics(
        particles,
        /*dt=*/1.0,
        /*consumption_rate=*/1.0,
        /*base_production=*/1.0,
        potential,
        /*terrain_production_enabled=*/true,
        /*terrain_production_scale=*/4.0,
        /*density_factor=*/nullptr,
        /*river_proximity_at_particle=*/nullptr,
        /*river_resource_enabled=*/false,
        /*river_resource_strength=*/0.0,
        /*river_resource_alpha=*/1.0,
        /*wealth_decay_rate=*/0.1
    );
    // production=1*4*max(0,-(-2))*1*1=8
    // consumption=1*1=1, decay=0.1*10*1=1 => 10+8-1-1=16
    require(close(particles.wealth(0), 16.0), "resource dynamics formula mismatch");
}

} // namespace

int main() {
    test_config_parses_cycle3_exchange_keys();
    test_particle_data_add_compact_alive_dead();
    test_cell_list_matches_bruteforce();
    test_morton_roundtrip_and_domain_mapping();
    test_terrain_ascii_y_orientation_and_synthetic();
    test_integrator_no_force_and_boundary();
    test_resource_dynamics_formula();
    std::cout << "active path tests passed\n";
    return 0;
}
