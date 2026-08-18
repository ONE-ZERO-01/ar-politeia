#pragma once

/// @file morton.hpp
/// @brief Morton (Z-order) 空间填充曲线编码/解码
///
/// Morton 曲线将 2D 坐标 (x, y) 映射为 1D 整数 key，保持空间局域性。
/// 用于大规模并行粒子模拟的负载均衡——按 Morton key 排序后均匀切割，
/// 使每个 MPI rank 管理的粒子数相等，同时保证空间上相邻的粒子
/// 大概率分配到同一个或相邻的 rank。
///
/// 编码方法：bit interleave（位交错）
///   x = 0b1010, y = 0b0011
///   key = 0b01_00_10_11 = 交替取 y 和 x 的每一位
///
/// 性能：编码/解码都是 O(1) 的位操作，无分支，适合热点路径。

#include "core/types.hpp"
#include <cstdint>

namespace politeia {

using MortonKey = std::uint64_t;

/// 将 2D 网格坐标 (gx, gy) 编码为 64-bit Morton key。
/// gx, gy 均为无符号 32-bit 整数（最多支持 2^32 × 2^32 的网格）。
[[nodiscard]] inline MortonKey encode_morton_2d(std::uint32_t gx, std::uint32_t gy) noexcept {
    // "magic bits" 展开：将 32-bit 整数的每一位分散到偶数位上
    auto expand_bits = [](std::uint32_t v) noexcept -> std::uint64_t {
        std::uint64_t u = v;
        u = (u | (u << 16)) & 0x0000FFFF0000FFFF;
        u = (u | (u <<  8)) & 0x00FF00FF00FF00FF;
        u = (u | (u <<  4)) & 0x0F0F0F0F0F0F0F0F;
        u = (u | (u <<  2)) & 0x3333333333333333;
        u = (u | (u <<  1)) & 0x5555555555555555;
        return u;
    };
    // x 占偶数位，y 占奇数位
    return expand_bits(gx) | (expand_bits(gy) << 1);
}

/// 从 64-bit Morton key 解码出 2D 网格坐标 (gx, gy)。
inline void decode_morton_2d(MortonKey key, std::uint32_t& gx, std::uint32_t& gy) noexcept {
    auto compact_bits = [](std::uint64_t u) noexcept -> std::uint32_t {
        u &= 0x5555555555555555;
        u = (u | (u >>  1)) & 0x3333333333333333;
        u = (u | (u >>  2)) & 0x0F0F0F0F0F0F0F0F;
        u = (u | (u >>  4)) & 0x00FF00FF00FF00FF;
        u = (u | (u >>  8)) & 0x0000FFFF0000FFFF;
        u = (u | (u >> 16)) & 0x00000000FFFFFFFF;
        return static_cast<std::uint32_t>(u);
    };
    gx = compact_bits(key);       // 偶数位 → x
    gy = compact_bits(key >> 1);  // 奇数位 → y
}

/// 将连续坐标 (x, y) 映射到 Morton key。
/// 先将浮点坐标量化到 [0, 2^level) 的整数网格，再编码。
[[nodiscard]] inline MortonKey point_to_morton(
    Real x, Real y,
    Real xmin, Real xmax, Real ymin, Real ymax,
    int level
) noexcept {
    const auto grid_size = static_cast<std::uint32_t>(1u << level);
    const Real inv_dx = grid_size / (xmax - xmin);
    const Real inv_dy = grid_size / (ymax - ymin);

    auto gx = static_cast<std::uint32_t>((x - xmin) * inv_dx);
    auto gy = static_cast<std::uint32_t>((y - ymin) * inv_dy);

    // 边界钳位
    if (gx >= grid_size) gx = grid_size - 1;
    if (gy >= grid_size) gy = grid_size - 1;

    return encode_morton_2d(gx, gy);
}

/// 从 Morton key 反算连续坐标（cell 中心点）。
inline void morton_to_point(
    MortonKey key,
    Real& x, Real& y,
    Real xmin, Real xmax, Real ymin, Real ymax,
    int level
) noexcept {
    std::uint32_t gx, gy;
    decode_morton_2d(key, gx, gy);

    const auto grid_size = static_cast<std::uint32_t>(1u << level);
    x = xmin + (gx + 0.5) * (xmax - xmin) / grid_size;
    y = ymin + (gy + 0.5) * (ymax - ymin) / grid_size;
}

} // namespace politeia
