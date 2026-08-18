#pragma once

/// @file social_force.hpp
/// @brief 人际空间交互力：聚居吸引 + 竞争排斥
///
/// 借鉴 Lennard-Jones 势的数学形式，但物理含义完全不同：
///   - 短程吸引：人是社会动物，倾向于聚居合作（狩猎、防御、取暖）
///   - 超短程排斥：两人不能占据同一位置，过近导致资源竞争
///   - sigma（σ）：人际"舒适距离"——聚居但不拥挤的平衡点
///   - epsilon（ε_social）：人际吸引强度——决定聚集的紧密程度
///   - cutoff：社交视野半径——超过此距离的人互不可见

#include "core/types.hpp"
#include "domain/cell_list.hpp"

namespace politeia {

/// 人际空间交互力的参数
struct SocialForceParams {
    Real epsilon = 1.0;   // 吸引强度（势阱深度）
    Real sigma = 1.0;     // 舒适距离（平衡点）
    Real cutoff = 2.5;    // 社交视野半径
};

/// 计算人际空间交互力（聚居吸引 + 竞争排斥）。
/// 使用 Lennard-Jones 势的数学形式，但社会含义为：
///   r < σ：排斥（资源竞争，太挤了）
///   r > σ：吸引（社会合作需求）
///   r > cutoff：无交互（太远，互不相识）
///
/// 力满足 Newton 第三定律（对称规则），每对只计算一次。
/// 返回总人际交互势能。
[[nodiscard]] Real compute_social_forces(
    const Real* __restrict__ x_data,
    Real* __restrict__ force,
    Index count,
    const CellList& cells,
    const SocialForceParams& params
);

} // namespace politeia
