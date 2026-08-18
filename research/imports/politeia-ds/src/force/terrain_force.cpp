/// @file terrain_force.cpp
/// @brief 地形外势力计算
///
/// 物理背景：高斯势阱模拟自然地理对人类的吸引力。
///   V(x,y) = −depth × exp(−r²/(2w²))
///   F = −∇V = (depth/w²) × exp(−r²/(2w²)) × (x−cx, y−cy)
///
/// 社会类比：
///   - 势阱中心 = 河流/绿洲/肥沃平原的位置
///   - depth（深度）= 这片土地有多宜居/肥沃
///   - width（宽度）= 宜居区域的范围有多大
///   - 力的方向指向势阱中心 = 人自然被好的生存环境吸引
///   - 多个势阱 = 多条河谷 = 多个潜在的文明发源地
///
/// 研究方案对应：这就是为什么四大文明都起源于大河流域——势能最低谷的聚集效应。

#include "force/terrain_force.hpp"

#include <cmath>
#include <vector>

namespace politeia {

Real terrain_potential(Real x, Real y, const TerrainParams& params) {
    // 计算位置 (x,y) 处的地形势能：所有高斯势阱的叠加
    Real V = 0.0;
    for (const auto& w : params.wells) {
        const Real dx = x - w.cx;    // 到势阱中心的距离分量
        const Real dy = y - w.cy;
        const Real r2 = dx * dx + dy * dy;
        const Real inv_2w2 = 1.0 / (2.0 * w.width * w.width);
        V += -w.depth * std::exp(-r2 * inv_2w2);
        // V < 0 在势阱中心（好的生存环境），V → 0 远离势阱（荒野）
    }
    return V;
}

Real compute_terrain_forces(
    const Real* __restrict__ x_data,
    Real* __restrict__ force,
    Index count,
    const TerrainParams& params
) {
    Real total_pe = 0.0;

    #pragma omp parallel for schedule(static) reduction(+:total_pe) if(count > 256)
    for (Index i = 0; i < count; ++i) {
        const Real xi = x_data[2 * i];
        const Real yi = x_data[2 * i + 1];

        Real fx = 0.0, fy = 0.0;

        for (const auto& w : params.wells) {
            const Real dx = xi - w.cx;    // 粒子到势阱中心的偏移
            const Real dy = yi - w.cy;
            const Real r2 = dx * dx + dy * dy;
            const Real inv_2w2 = 1.0 / (2.0 * w.width * w.width);
            const Real gauss = w.depth * std::exp(-r2 * inv_2w2);

            // 力 = −dV/dx = −(−depth) × exp(…) × (−2dx/(2w²))
            //     = depth × exp(…) × dx/w²
            // 方向：指向势阱中心（吸引力）
            // 物理含义：越远离河谷，被拉回的力越强（但随距离指数衰减）
            const Real coeff = gauss / (w.width * w.width);
            fx -= coeff * dx;  // 负号：力指向中心（dx > 0 时 fx < 0）
            fy -= coeff * dy;

            total_pe += -gauss;
        }

        force[2 * i]     += fx;
        force[2 * i + 1] += fy;
    }

    return total_pe;
}

} // namespace politeia
