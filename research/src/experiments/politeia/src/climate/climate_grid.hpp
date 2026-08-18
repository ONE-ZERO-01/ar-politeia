#pragma once

/// @file climate_grid.hpp
/// @brief Climate subsystem for Politeia
///
/// Provides spatially-varying climate data (temperature, precipitation) that
/// couples into resource production, carrying capacity, mortality, movement
/// friction, and plague trigger rates.
///
/// Supports three data sources:
///   1. External file (Koppen-Geiger or custom ESRI ASCII grid)
///   2. Procedural generation from latitude + elevation formulas
///   3. Uniform fallback (climate_enabled = false)
///
/// Time-varying modes: static, drift (linear/piecewise), seasonal.

#include "core/types.hpp"

#include <string>
#include <vector>

namespace politeia {

class TerrainGrid;  // forward declaration for elevation queries

struct ClimateFactors {
    Real production_factor = 1.0;   // multiplier on resource production R(x)
    Real carrying_factor = 1.0;     // multiplier on carrying capacity K(x)
    Real mortality_addition = 0.0;  // additive extra mortality rate
    Real friction_factor = 1.0;     // multiplier on effective friction
    Real plague_factor = 1.0;       // multiplier on plague trigger rate
};

struct ClimateCell {
    Real temperature = 15.0;    // annual mean temperature (degC)
    Real precipitation = 800.0; // annual precipitation (mm)
};

enum class ClimateTimeMode {
    Static,
    Drift,
    Seasonal
};

struct DriftSegment {
    Index start_step;
    Real delta_T;  // temperature offset at this step
};

class ClimateGrid {
public:
    ClimateGrid() = default;

    /// Load climate data from ESRI ASCII Grid file.
    /// File should contain two bands: temperature (degC) and precipitation (mm).
    /// Format: standard 6-line header, then nrows*ncols temperature values,
    /// then another 6-line header + nrows*ncols precipitation values.
    void load_ascii(const std::string& filepath);

    /// Generate procedural climate from latitude and (optionally) elevation.
    /// @param terrain Optional terrain grid for elevation-based correction.
    void generate_procedural(int nrows, int ncols,
                             Real xmin, Real ymin, Real xmax, Real ymax,
                             const TerrainGrid* terrain = nullptr);

    /// Query interpolated climate at world position (x = longitude, y = latitude).
    [[nodiscard]] ClimateCell cell_at(Real x, Real y) const noexcept;

    /// Compute all coupling factors at a given position.
    [[nodiscard]] ClimateFactors factors_at(Real x, Real y,
                                            Real mortality_scale,
                                            Real friction_scale,
                                            Real plague_scale) const noexcept;

    /// Advance time-varying climate by one update interval.
    /// @param current_step The current simulation step (for drift schedule lookup).
    void advance(Index current_step, ClimateTimeMode mode,
                 Real drift_rate, Real season_amplitude, Real season_period,
                 Real dt);

    /// Parse drift schedule string "step:delta_T, step:delta_T, ..."
    void set_drift_schedule(const std::string& schedule);

    [[nodiscard]] bool loaded() const noexcept { return !temp_data_.empty(); }
    [[nodiscard]] int nrows() const noexcept { return nrows_; }
    [[nodiscard]] int ncols() const noexcept { return ncols_; }

private:
    std::vector<Real> temp_data_;    // base temperature field (row-major)
    std::vector<Real> precip_data_;  // base precipitation field (row-major)
    int nrows_ = 0, ncols_ = 0;
    Real xmin_ = 0, ymin_ = 0;
    Real cellsize_ = 1.0;

    Real time_offset_T_ = 0.0;  // current temporal temperature offset

    std::vector<DriftSegment> drift_schedule_;

    [[nodiscard]] Real interp(const std::vector<Real>& field, Real x, Real y) const noexcept;

    static Real harshness(Real T, Real P) noexcept;
    static Real production_factor(Real T, Real P) noexcept;
};

} // namespace politeia
