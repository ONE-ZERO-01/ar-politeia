#pragma once
/// @file ic_loader.hpp
/// @brief Load initial conditions from a CSV file.
///
/// CSV format (header required, order-independent):
///   x,y            — position (required)
///   w              — wealth (optional, default = initial_wealth)
///   eps            — epsilon (optional, default = 1.0)
///   age            — age (optional, default = 20.0)
///   sex            — sex: 0=female, 1=male (optional, default = random)
///   c0,c1,...      — culture vector components (optional, default = random)
///
/// Any column not present in the CSV uses its default value.
/// The number of rows determines initial_particles (overrides cfg value).

#include "core/types.hpp"
#include "core/particle_data.hpp"
#include "core/config.hpp"

#include <string>
#include <random>

namespace politeia {

/// Load particles from a CSV initial-conditions file.
/// Returns the number of particles loaded.
/// Only rank 0 should call this; other ranks get 0 particles and will
/// receive their share after SFC redistribution.
Index load_initial_conditions(
    const std::string& filepath,
    ParticleData& particles,
    const SimConfig& cfg,
    std::mt19937_64& rng,
    int rank
);

} // namespace politeia
