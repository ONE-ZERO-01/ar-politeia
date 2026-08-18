#pragma once

/// @file terrain_loader.hpp
/// @brief 真实地形数据加载器
///
/// 将 DEM（数字高程模型）数据加载为 2D 高程网格，并提供：
///   - 双线性插值查询任意点的高程
///   - 梯度（地形力）计算
///   - 高程 → 势能转换（高地势能高，河谷势能低）
///
/// 支持格式：
///   1. ESRI ASCII Grid (.asc)：标准 GIS 格式
///   2. Raw binary float64：row-major 二进制矩阵
///
/// 势能模型：
///   V(x,y) = scale * (h(x,y) - h_min)
///   河谷低洼处 V ≈ 0（势能最低），高山 V > 0（势能高）
///   人群被梯度力吸引到河谷 —— 模拟四大文明起源于大河流域

#include "core/types.hpp"

#include <string>
#include <vector>

namespace politeia {

/// 2D 高程网格
class TerrainGrid {
public:
    TerrainGrid() = default;

    /// 从 ESRI ASCII Grid (.asc) 加载
    /// 格式：6 行头部（ncols, nrows, xllcorner, yllcorner, cellsize, NODATA_value）
    ///       后跟 nrows × ncols 的高程数据（空格分隔）
    void load_ascii(const std::string& filepath);

    /// 从 raw binary (float64, row-major) 加载
    /// @param nrows, ncols 网格维度
    /// @param xmin, ymin, cellsize 空间范围
    void load_binary(const std::string& filepath,
                     int nrows, int ncols,
                     Real xmin, Real ymin, Real cellsize);

    /// 生成合成地形用于测试
    /// @param type "valley" — 中心河谷，"ridge" — 中心山脊，"flat" — 平坦
    void generate_synthetic(int nrows, int ncols,
                            Real xmin, Real ymin,
                            Real xmax, Real ymax,
                            const std::string& type = "valley");

    /// 双线性插值查询高程 h(x,y)
    /// 越界点返回边界值（clamp）
    [[nodiscard]] Real elevation(Real x, Real y) const noexcept;

    /// 高程梯度 ∇h(x,y)，用中心差分
    /// 返回 {dh/dx, dh/dy}
    [[nodiscard]] Vec2 gradient(Real x, Real y) const noexcept;

    /// 高程 → 势能：V(x,y) = scale * (h(x,y) - h_min)
    /// 河谷最低处 V = 0
    [[nodiscard]] Real potential(Real x, Real y, Real scale) const noexcept;

    /// 势能梯度（力 = -∇V = -scale * ∇h）
    [[nodiscard]] Vec2 force(Real x, Real y, Real scale) const noexcept;

    // --- 访问器 ---
    [[nodiscard]] bool loaded() const noexcept { return !data_.empty(); }
    [[nodiscard]] int nrows() const noexcept { return nrows_; }
    [[nodiscard]] int ncols() const noexcept { return ncols_; }
    [[nodiscard]] Real xmin() const noexcept { return xmin_; }
    [[nodiscard]] Real ymin() const noexcept { return ymin_; }
    [[nodiscard]] Real xmax() const noexcept { return xmin_ + (ncols_ - 1) * cellsize_; }
    [[nodiscard]] Real ymax() const noexcept { return ymin_ + (nrows_ - 1) * cellsize_; }
    [[nodiscard]] Real cellsize() const noexcept { return cellsize_; }
    [[nodiscard]] Real h_min() const noexcept { return h_min_; }
    [[nodiscard]] Real h_max() const noexcept { return h_max_; }

    /// 直接访问网格值 data[row * ncols + col]
    [[nodiscard]] Real at(int row, int col) const noexcept;

private:
    std::vector<Real> data_;   // row-major: data_[row * ncols_ + col]
    int nrows_ = 0, ncols_ = 0;
    Real xmin_ = 0, ymin_ = 0;
    Real cellsize_ = 1.0;
    Real nodata_ = -9999.0;
    Real h_min_ = 0, h_max_ = 0;

    void compute_minmax();
};

/// 使用 TerrainGrid 计算所有粒子的地形力。
/// 如果 grid 未加载（!grid.loaded()），不做任何操作并返回 0。
/// @param scale 高程 → 势能的缩放因子（正值，越大地形吸引力越强）
/// @return 总地形势能
[[nodiscard]] Real compute_grid_terrain_forces(
    const Real* __restrict__ x_data,
    Real* __restrict__ force,
    Index count,
    const TerrainGrid& grid,
    Real scale
);

/// 计算粒子处的地形势能（用于资源产出）。
/// 负值表示好的位置（河谷），0 表示高地。
/// @return V(x,y) = -scale * (h_max - h(x,y))，河谷处为负（最肥沃）
[[nodiscard]] Real grid_terrain_potential(
    Real x, Real y,
    const TerrainGrid& grid,
    Real scale
);

} // namespace politeia
