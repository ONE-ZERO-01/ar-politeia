#pragma once

#include <cstddef>
#include <cstdint>
#include <array>

namespace politeia {

using Real = double;
using Index = std::size_t;
using Id = std::int64_t;

constexpr int SPATIAL_DIM = 2;

using Vec2 = std::array<Real, SPATIAL_DIM>;

enum class ParticleStatus : std::uint8_t {
    Alive = 0,
    Dead = 1,
    Pregnant = 2,
    Nursing = 3,
};

} // namespace politeia
