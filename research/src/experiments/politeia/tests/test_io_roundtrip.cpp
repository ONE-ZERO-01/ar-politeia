#include "core/config.hpp"
#include "core/particle_data.hpp"
#include "io/checkpoint.hpp"
#include "climate/climate_grid.hpp"
#include "river/river_field.hpp"

#include <cmath>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>

namespace {

bool close(double lhs, double rhs, double tolerance = 1e-12) {
    return std::abs(lhs - rhs) <= tolerance;
}

void require(bool condition, const char* message) {
    if (!condition) {
        throw std::runtime_error(message);
    }
}

std::filesystem::path temp_path(const std::string& name) {
    return std::filesystem::temp_directory_path() / name;
}

void test_checkpoint_roundtrip() {
    politeia::ParticleData src(4, 2, 1);
    src.set_id_seed(0);
    const auto i0 = src.add_particle({0.0, 0.0}, {0.1, -0.2}, 3.5, 1.25, 27.0);
    const auto i1 = src.add_particle({1.0, 2.0}, {-0.3, 0.4}, 7.5, 2.5, 31.0);

    src.sex(i0) = 0;
    src.sex(i1) = 1;
    src.last_birth_time(i0) = 12.0;
    src.last_birth_time(i1) = 13.0;
    src.superior(i0) = src.global_id(i1);
    src.loyalty(i0) = 0.65;
    src.superior(i1) = -1;
    src.loyalty(i1) = 0.0;
    src.culture(i0, 0) = 0.2;
    src.culture(i0, 1) = -0.4;
    src.culture(i1, 0) = 0.8;
    src.culture(i1, 1) = 0.1;
    src.immunity(i0, 0) = 0.3;
    src.immunity(i1, 0) = 0.9;

    politeia::SimConfig cfg;
    cfg.dt = 0.01;
    const auto path = temp_path("politeia_checkpoint_roundtrip.bin");
    politeia::write_checkpoint(path.string(), src, cfg, "", 7, 0, 1);

    politeia::ParticleData dst(0, 2, 1);
    std::uint64_t step = 0;
    double time = 0.0;
    politeia::read_checkpoint(path.string(), dst, step, time, 0, 1);
    std::filesystem::remove(path);

    require(dst.count() == 2, "checkpoint particle count mismatch");
    require(step == 7, "checkpoint step mismatch");
    require(close(time, 0.07), "checkpoint time mismatch");
    require(close(dst.wealth(0), 3.5), "checkpoint wealth mismatch");
    require(close(dst.epsilon(1), 2.5), "checkpoint epsilon mismatch");
    require(dst.sex(1) == 1, "checkpoint sex mismatch");
    require(close(dst.culture(0, 1), -0.4), "checkpoint culture mismatch");
    require(close(dst.immunity(1, 0), 0.9), "checkpoint immunity mismatch");
    require(dst.superior(0) == dst.global_id(1), "checkpoint superior mismatch");
    require(close(dst.loyalty(0), 0.65), "checkpoint loyalty mismatch");
}

void test_climate_ascii_roundtrip() {
    const auto path = temp_path("politeia_climate_roundtrip.asc");
    {
        std::ofstream out(path);
        out << "ncols 2\nnrows 2\nxllcorner 0\nyllcorner 0\ncellsize 1\nNODATA_value -9999\n"
            << "10 20\n30 40\n"
            << "ncols 2\nnrows 2\nxllcorner 0\nyllcorner 0\ncellsize 1\nNODATA_value -9999\n"
            << "100 200\n300 400\n";
    }

    politeia::ClimateGrid climate;
    climate.load_ascii(path.string());
    std::filesystem::remove(path);

    require(climate.nrows() == 2 && climate.ncols() == 2, "climate dimensions wrong");
    const auto south = climate.cell_at(0.0, 0.0);
    require(close(south.temperature, 30.0), "climate south temperature wrong");
    require(close(south.precipitation, 300.0), "climate south precipitation wrong");
}

void test_river_ascii_roundtrip() {
    const auto path = temp_path("politeia_river_roundtrip.asc");
    {
        std::ofstream out(path);
        out << "ncols 2\nnrows 2\nxllcorner 0\nyllcorner 0\ncellsize 1\nNODATA_value -9999\n"
            << "0.1 0.2\n0.3 0.4\n"
            << "ncols 2\nnrows 2\nxllcorner 0\nyllcorner 0\ncellsize 1\nNODATA_value -9999\n"
            << "0.5 0.6\n0.7 0.8\n";
    }

    politeia::RiverField river;
    river.load_ascii(path.string());
    std::filesystem::remove(path);

    require(river.nrows() == 2 && river.ncols() == 2, "river dimensions wrong");
    const auto south = river.cell_at(0.0, 0.0);
    require(close(south.proximity, 0.3), "river proximity wrong");
    require(close(south.discharge, 0.7), "river discharge wrong");
}

void test_river_ascii_single_band() {
    const auto path = temp_path("politeia_river_single_band.asc");
    {
        std::ofstream out(path);
        out << "ncols 2\nnrows 2\nxllcorner 0\nyllcorner 0\ncellsize 1\nNODATA_value -9999\n"
            << "0.1 0.2\n0.3 0.4\n";
    }

    politeia::RiverField river;
    river.load_ascii(path.string());
    std::filesystem::remove(path);

    require(river.nrows() == 2 && river.ncols() == 2, "single-band river dimensions wrong");
    require(close(river.discharge(0.0, 0.0), 0.0), "single-band river discharge should be zero");
}

} // namespace

int main() {
    test_checkpoint_roundtrip();
    test_climate_ascii_roundtrip();
    test_river_ascii_roundtrip();
    test_river_ascii_single_band();
    std::cout << "io roundtrip tests passed\n";
    return 0;
}
