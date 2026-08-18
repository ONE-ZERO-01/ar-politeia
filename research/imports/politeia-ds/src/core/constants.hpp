#pragma once

#include "types.hpp"

namespace politeia::constants {

// Simulation defaults
constexpr Real DEFAULT_DT = 0.01;
constexpr Real DEFAULT_TEMPERATURE = 1.0;
constexpr Real DEFAULT_FRICTION = 1.0;

// 人际空间交互力参数（借鉴 LJ 势数学形式）
constexpr Real DEFAULT_SOCIAL_STRENGTH = 1.0;       // 人际吸引强度
constexpr Real DEFAULT_SOCIAL_DISTANCE = 1.0;       // 人际舒适距离
constexpr Real DEFAULT_INTERACTION_RANGE = 2.5;     // 社交视野半径

// Resource defaults
constexpr Real DEFAULT_INITIAL_WEALTH = 5.0;
constexpr Real DEFAULT_SURVIVAL_THRESHOLD = 0.1;
constexpr Real DEFAULT_CONSUMPTION_RATE = 0.002;

// Reproduction defaults
constexpr Real DEFAULT_PUBERTY_AGE = 15.0;
constexpr Real DEFAULT_MENOPAUSE_AGE = 45.0;
constexpr Real DEFAULT_GESTATION_TIME = 0.75;  // ~10 months in year units
constexpr Real DEFAULT_NURSING_TIME = 1.5;

// Cultural vector
constexpr int DEFAULT_CULTURE_DIM = 2;

// Mortality
constexpr Real DEFAULT_ACCIDENT_RATE = 1e-4;
constexpr Real DEFAULT_GOMPERTZ_BETA = 0.085;  // Gompertz aging parameter

} // namespace politeia::constants
