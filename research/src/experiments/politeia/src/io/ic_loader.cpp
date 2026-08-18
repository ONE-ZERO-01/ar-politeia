/// @file ic_loader.cpp
/// @brief Load initial conditions from a CSV file.

#include "io/ic_loader.hpp"

#include <cmath>
#include <fstream>
#include <sstream>
#include <stdexcept>
#include <iostream>
#include <algorithm>
#include <unordered_map>

namespace politeia {

namespace {

std::string strip(const std::string& s) {
    auto a = s.find_first_not_of(" \t\r\n");
    if (a == std::string::npos) return "";
    return s.substr(a, s.find_last_not_of(" \t\r\n") - a + 1);
}

std::vector<std::string> split_csv_line(const std::string& line) {
    std::vector<std::string> fields;
    std::stringstream ss(line);
    std::string field;
    while (std::getline(ss, field, ',')) {
        fields.push_back(strip(field));
    }
    return fields;
}

} // namespace

Index load_initial_conditions(
    const std::string& filepath,
    ParticleData& particles,
    const SimConfig& cfg,
    std::mt19937_64& rng,
    int rank
) {
    if (rank != 0) return 0;

    std::ifstream file(filepath);
    if (!file.is_open()) {
        throw std::runtime_error("Cannot open initial conditions file: " + filepath);
    }

    std::string header_line;
    if (!std::getline(file, header_line)) {
        throw std::runtime_error("Empty initial conditions file: " + filepath);
    }

    auto headers = split_csv_line(header_line);
    std::unordered_map<std::string, int> col_idx;
    for (int i = 0; i < static_cast<int>(headers.size()); ++i) {
        col_idx[headers[i]] = i;
    }

    if (col_idx.find("x") == col_idx.end() || col_idx.find("y") == col_idx.end()) {
        throw std::runtime_error("Initial conditions CSV must have 'x' and 'y' columns");
    }

    auto get_col = [&](const std::string& name) -> int {
        auto it = col_idx.find(name);
        return (it != col_idx.end()) ? it->second : -1;
    };

    const int ix = col_idx["x"];
    const int iy = col_idx["y"];
    const int iw = get_col("w");
    const int ieps = get_col("eps");
    const int iage = get_col("age");
    const int isex = get_col("sex");

    std::vector<int> iculture;
    for (int d = 0; d < cfg.culture_dim; ++d) {
        iculture.push_back(get_col("c" + std::to_string(d)));
    }

    std::normal_distribution<Real> dist_cv(0.0, 1.0);
    std::uniform_real_distribution<Real> dist_sex(0.0, 1.0);
    std::normal_distribution<Real> dist_p(0.0, std::sqrt(cfg.temperature));

    // Age pyramid: approximate a pre-industrial stationary population
    // with crude death rate ~0.03/yr → survival function S(a) ≈ exp(-0.03*a)
    // truncated at max_age=70. Sampling via inverse CDF: a = -ln(1-U*(1-exp(-λ*max)))/λ
    constexpr Real PYRAMID_LAMBDA = 0.03;
    constexpr Real PYRAMID_MAX_AGE = 70.0;
    const Real exp_term = std::exp(-PYRAMID_LAMBDA * PYRAMID_MAX_AGE);
    std::uniform_real_distribution<Real> dist_u01(0.0, 1.0);
    auto sample_pyramid_age = [&]() -> Real {
        Real u = dist_u01(rng);
        return -std::log(1.0 - u * (1.0 - exp_term)) / PYRAMID_LAMBDA;
    };

    Index count = 0;
    std::string line;
    int lineno = 1;

    while (std::getline(file, line)) {
        ++lineno;
        line = strip(line);
        if (line.empty() || line[0] == '#') continue;

        auto fields = split_csv_line(line);
        if (static_cast<int>(fields.size()) <= std::max(ix, iy)) {
            std::cerr << "IC line " << lineno << ": too few fields, skipping\n";
            continue;
        }

        Real x = std::stod(fields[ix]);
        Real y = std::stod(fields[iy]);

        Real w = (iw >= 0 && iw < static_cast<int>(fields.size()))
                 ? std::stod(fields[iw]) : cfg.initial_wealth;
        Real eps = (ieps >= 0 && ieps < static_cast<int>(fields.size()))
                   ? std::stod(fields[ieps]) : 1.0;
        Real age;
        if (cfg.age_pyramid) {
            age = sample_pyramid_age();
        } else {
            age = (iage >= 0 && iage < static_cast<int>(fields.size()))
                       ? std::stod(fields[iage]) : 20.0;
        }

        Vec2 pos = {x, y};
        Vec2 mom = {dist_p(rng), dist_p(rng)};
        Index idx = particles.add_particle(pos, mom, w, eps, age);

        if (cfg.gender_enabled) {
            if (isex >= 0 && isex < static_cast<int>(fields.size())) {
                particles.sex(idx) = static_cast<uint8_t>(std::stoi(fields[isex]));
            } else {
                particles.sex(idx) = (dist_sex(rng) < cfg.sex_ratio) ? 1 : 0;
            }
        }

        for (int d = 0; d < cfg.culture_dim; ++d) {
            if (iculture[d] >= 0 && iculture[d] < static_cast<int>(fields.size())) {
                particles.culture(idx, d) = std::stod(fields[iculture[d]]);
            } else {
                particles.culture(idx, d) = dist_cv(rng);
            }
        }

        ++count;
        if (cfg.initial_particles > 0 &&
            count >= static_cast<Index>(cfg.initial_particles)) {
            break;
        }
    }

    std::cout << "Loaded " << count << " particles from " << filepath << "\n";
    return count;
}

} // namespace politeia
