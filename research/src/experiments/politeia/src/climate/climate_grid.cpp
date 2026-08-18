/// @file climate_grid.cpp
/// @brief Climate subsystem implementation
///
/// Procedural climate model:
///   T(lat) = 30 - 0.7 * |lat|                  (latitude gradient)
///   T_adj  = T(lat) - 0.0065 * max(0, elev)    (elevation lapse rate)
///   P(lat) = 2000 * exp(-((|lat|-5)/25)^2)     (ITCZ peak + subtropical dry)
///
/// Coupling factors:
///   harshness(T,P) = sigmoid(|T-20|/15) + sigmoid((400-P)/200)
///   production_factor = exp(-((T-20)/15)^2) * min(1, P/400)
///   carrying_factor   = same as production_factor
///   mortality_add     = mortality_scale * harshness
///   friction_factor   = 1 + friction_scale * harshness
///   plague_factor     = 1 + plague_scale * max(0, (T-20)/10) * min(1, P/1000)

#include "climate/climate_grid.hpp"
#include "force/terrain_loader.hpp"

#include <cmath>
#include <fstream>
#include <sstream>
#include <stdexcept>
#include <algorithm>

namespace politeia {

namespace {

Real sigmoid(Real x) noexcept {
    return 1.0 / (1.0 + std::exp(-x));
}

std::string trim_ws(const std::string& s) {
    auto start = s.find_first_not_of(" \t\r\n");
    if (start == std::string::npos) return "";
    auto end = s.find_last_not_of(" \t\r\n");
    return s.substr(start, end - start + 1);
}

} // namespace

// --- Interpolation ---

Real ClimateGrid::interp(const std::vector<Real>& field, Real x, Real y) const noexcept {
    Real fx = (x - xmin_) / cellsize_;
    Real fy = (y - ymin_) / cellsize_;

    fx = std::max(0.0, std::min(fx, static_cast<Real>(ncols_ - 1)));
    fy = std::max(0.0, std::min(fy, static_cast<Real>(nrows_ - 1)));

    int ix = static_cast<int>(fx);
    int iy = static_cast<int>(fy);
    ix = std::min(ix, ncols_ - 2);
    iy = std::min(iy, nrows_ - 2);

    Real tx = fx - ix;
    Real ty = fy - iy;

    Real v00 = field[iy * ncols_ + ix];
    Real v10 = field[iy * ncols_ + ix + 1];
    Real v01 = field[(iy + 1) * ncols_ + ix];
    Real v11 = field[(iy + 1) * ncols_ + ix + 1];

    return (1 - tx) * (1 - ty) * v00 + tx * (1 - ty) * v10
         + (1 - tx) * ty * v01 + tx * ty * v11;
}

// --- Static helper functions ---

Real ClimateGrid::harshness(Real T, Real P) noexcept {
    Real temp_harsh = sigmoid((std::abs(T - 20.0) - 10.0) / 5.0);
    Real precip_harsh = sigmoid((400.0 - P) / 200.0);
    return temp_harsh + precip_harsh;
}

Real ClimateGrid::production_factor(Real T, Real P) noexcept {
    Real temp_f = std::exp(-((T - 20.0) / 15.0) * ((T - 20.0) / 15.0));
    Real precip_f = std::min(1.0, P / 400.0);
    return std::max(0.01, temp_f * precip_f);
}

// --- Query ---

ClimateCell ClimateGrid::cell_at(Real x, Real y) const noexcept {
    if (!loaded()) return ClimateCell{15.0, 800.0};

    ClimateCell c;
    c.temperature = interp(temp_data_, x, y) + time_offset_T_;
    c.precipitation = interp(precip_data_, x, y);
    return c;
}

ClimateFactors ClimateGrid::factors_at(Real x, Real y,
                                        Real mortality_scale,
                                        Real friction_scale,
                                        Real plague_scale) const noexcept {
    ClimateFactors f;
    if (!loaded()) return f;

    ClimateCell c = cell_at(x, y);
    Real T = c.temperature;
    Real P = c.precipitation;

    f.production_factor = production_factor(T, P);
    f.carrying_factor = production_factor(T, P);

    Real h = harshness(T, P);
    f.mortality_addition = mortality_scale * h;
    f.friction_factor = 1.0 + friction_scale * h;

    Real tropical_wet = std::max(0.0, (T - 20.0) / 10.0) * std::min(1.0, P / 1000.0);
    f.plague_factor = 1.0 + plague_scale * tropical_wet;

    return f;
}

// --- Procedural generation ---

void ClimateGrid::generate_procedural(int nrows, int ncols,
                                       Real xmin, Real ymin,
                                       Real xmax, Real ymax,
                                       const TerrainGrid* terrain) {
    nrows_ = nrows;
    ncols_ = ncols;
    xmin_ = xmin;
    ymin_ = ymin;
    cellsize_ = (xmax - xmin) / std::max(ncols - 1, 1);

    temp_data_.resize(nrows * ncols);
    precip_data_.resize(nrows * ncols);

    Real dy = (ymax - ymin) / std::max(nrows - 1, 1);

    for (int r = 0; r < nrows; ++r) {
        Real lat = ymin + r * dy;
        Real abs_lat = std::abs(lat);

        Real base_T = 30.0 - 0.7 * abs_lat;
        Real lat_shifted = abs_lat - 5.0;
        Real base_P = 2000.0 * std::exp(-(lat_shifted / 25.0) * (lat_shifted / 25.0));
        base_P = std::max(50.0, base_P);

        for (int c = 0; c < ncols; ++c) {
            Real lon = xmin + c * cellsize_;
            Real T = base_T;
            Real P = base_P;

            if (terrain && terrain->loaded()) {
                Real elev = terrain->elevation(lon, lat);
                T -= 0.0065 * std::max(0.0, elev);
                if (elev > 3000.0) {
                    P *= 0.5;
                }
            }

            temp_data_[r * ncols + c] = T;
            precip_data_[r * ncols + c] = P;
        }
    }

    time_offset_T_ = 0.0;
}

// --- File loading ---

void ClimateGrid::load_ascii(const std::string& filepath) {
    std::ifstream file(filepath);
    if (!file.is_open()) {
        throw std::runtime_error("Cannot open climate file: " + filepath);
    }

    auto read_header = [&](int& nr, int& nc, Real& xll, Real& yll, Real& cs) {
        std::string line, key;
        Real nodata = -9999.0;

        for (int i = 0; i < 6; ++i) {
            std::getline(file, line);
            std::istringstream iss(line);
            iss >> key;
            if (key == "ncols") iss >> nc;
            else if (key == "nrows") iss >> nr;
            else if (key == "xllcorner") iss >> xll;
            else if (key == "yllcorner") iss >> yll;
            else if (key == "cellsize") iss >> cs;
            else if (key == "NODATA_value") iss >> nodata;
        }
    };

    int nr1, nc1;
    Real xll1, yll1, cs1;
    read_header(nr1, nc1, xll1, yll1, cs1);

    nrows_ = nr1;
    ncols_ = nc1;
    xmin_ = xll1;
    ymin_ = yll1;
    cellsize_ = cs1;

    temp_data_.resize(nr1 * nc1);
    for (int r = nr1 - 1; r >= 0; --r) {
        for (int c = 0; c < nc1; ++c) {
            file >> temp_data_[r * nc1 + c];
        }
    }

    // Consume rest of current line after >> extraction to align for next getline-based header
    { std::string skip; std::getline(file, skip); }

    int nr2, nc2;
    Real xll2, yll2, cs2;
    read_header(nr2, nc2, xll2, yll2, cs2);

    precip_data_.resize(nr2 * nc2);
    for (int r = nr2 - 1; r >= 0; --r) {
        for (int c = 0; c < nc2; ++c) {
            file >> precip_data_[r * nc2 + c];
        }
    }

    time_offset_T_ = 0.0;
}

// --- Time-varying ---

void ClimateGrid::set_drift_schedule(const std::string& schedule) {
    drift_schedule_.clear();
    if (schedule.empty()) return;

    std::istringstream iss(schedule);
    std::string token;
    while (std::getline(iss, token, ',')) {
        token = trim_ws(token);
        auto colon = token.find(':');
        if (colon == std::string::npos) continue;
        DriftSegment seg;
        seg.start_step = std::stoull(token.substr(0, colon));
        seg.delta_T = std::stod(token.substr(colon + 1));
        drift_schedule_.push_back(seg);
    }

    std::sort(drift_schedule_.begin(), drift_schedule_.end(),
              [](const DriftSegment& a, const DriftSegment& b) {
                  return a.start_step < b.start_step;
              });
}

void ClimateGrid::advance(Index current_step, ClimateTimeMode mode,
                           Real drift_rate, Real season_amplitude,
                           Real season_period, Real dt) {
    switch (mode) {
    case ClimateTimeMode::Static:
        time_offset_T_ = 0.0;
        break;

    case ClimateTimeMode::Drift:
        if (!drift_schedule_.empty()) {
            Real offset = 0.0;
            for (const auto& seg : drift_schedule_) {
                if (current_step >= seg.start_step) {
                    offset = seg.delta_T;
                }
            }
            time_offset_T_ = offset;
        } else {
            time_offset_T_ = drift_rate * static_cast<Real>(current_step) * dt;
        }
        break;

    case ClimateTimeMode::Seasonal: {
        Real t = static_cast<Real>(current_step) * dt;
        Real drift_part = drift_rate * t;
        Real season_part = season_amplitude
            * std::cos(2.0 * 3.14159265358979323846 * t / season_period);
        time_offset_T_ = drift_part + season_part;
        break;
    }
    }
}

} // namespace politeia
