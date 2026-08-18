/// @file terrain_loader.cpp
/// @brief 真实地形加载、插值与力计算

#include "force/terrain_loader.hpp"

#include <algorithm>
#include <cmath>
#include <fstream>
#include <sstream>
#include <stdexcept>

namespace politeia {

// ─── 数据访问 ─────────────────────────────────────────────

Real TerrainGrid::at(int row, int col) const noexcept {
    row = std::clamp(row, 0, nrows_ - 1);
    col = std::clamp(col, 0, ncols_ - 1);
    return data_[static_cast<std::size_t>(row) * ncols_ + col];
}

void TerrainGrid::compute_minmax() {
    if (data_.empty()) return;
    h_min_ = *std::min_element(data_.begin(), data_.end());
    h_max_ = *std::max_element(data_.begin(), data_.end());
}

// ─── ASCII Grid 加载 ──────────────────────────────────────

void TerrainGrid::load_ascii(const std::string& filepath) {
    std::ifstream file(filepath);
    if (!file.is_open()) {
        throw std::runtime_error("Cannot open terrain file: " + filepath);
    }

    auto read_header = [&](const std::string& expected_key) -> double {
        std::string key;
        double val;
        if (!(file >> key >> val)) {
            throw std::runtime_error("Failed to read header: " + expected_key);
        }
        return val;
    };

    ncols_ = static_cast<int>(read_header("ncols"));
    nrows_ = static_cast<int>(read_header("nrows"));
    xmin_ = read_header("xllcorner");
    ymin_ = read_header("yllcorner");
    cellsize_ = read_header("cellsize");
    nodata_ = read_header("NODATA_value");

    data_.resize(static_cast<std::size_t>(nrows_) * ncols_);

    // ASCII grid 行序：第一行是最北（最大 y），最后一行是最南（最小 y）
    for (int r = nrows_ - 1; r >= 0; --r) {
        for (int c = 0; c < ncols_; ++c) {
            Real val;
            if (!(file >> val)) {
                throw std::runtime_error("Unexpected EOF at row=" +
                    std::to_string(r) + " col=" + std::to_string(c));
            }
            if (val == nodata_) val = 0.0;
            data_[static_cast<std::size_t>(r) * ncols_ + c] = val;
        }
    }

    compute_minmax();
}

// ─── Binary 加载 ──────────────────────────────────────────

void TerrainGrid::load_binary(const std::string& filepath,
                              int nrows, int ncols,
                              Real xmin, Real ymin, Real cellsize) {
    nrows_ = nrows;
    ncols_ = ncols;
    xmin_ = xmin;
    ymin_ = ymin;
    cellsize_ = cellsize;

    const auto total = static_cast<std::size_t>(nrows_) * ncols_;
    data_.resize(total);

    std::ifstream file(filepath, std::ios::binary);
    if (!file.is_open()) {
        throw std::runtime_error("Cannot open terrain binary: " + filepath);
    }

    file.read(reinterpret_cast<char*>(data_.data()),
              static_cast<std::streamsize>(total * sizeof(Real)));
    if (!file) {
        throw std::runtime_error("Incomplete read of terrain binary: " + filepath);
    }

    compute_minmax();
}

// ─── 合成地形 ─────────────────────────────────────────────

void TerrainGrid::generate_synthetic(int nrows, int ncols,
                                     Real xmin, Real ymin,
                                     Real xmax, Real ymax,
                                     const std::string& type) {
    nrows_ = nrows;
    ncols_ = ncols;
    xmin_ = xmin;
    ymin_ = ymin;
    cellsize_ = (ncols > 1) ? (xmax - xmin) / (ncols - 1) : 1.0;

    data_.resize(static_cast<std::size_t>(nrows) * ncols);

    const Real cx = 0.5 * (xmin + xmax);
    const Real cy = 0.5 * (ymin + ymax);
    const Real rx = 0.25 * (xmax - xmin);
    const Real ry = 0.25 * (ymax - ymin);

    for (int r = 0; r < nrows; ++r) {
        for (int c = 0; c < ncols; ++c) {
            Real x = xmin + c * cellsize_;
            Real y = ymin + r * ((ymax - ymin) / (nrows - 1));
            Real dx = (x - cx) / rx;
            Real dy = (y - cy) / ry;
            Real r2 = dx * dx + dy * dy;

            Real h;
            if (type == "valley") {
                // 中心低洼河谷，四周高山
                h = 100.0 * (1.0 - std::exp(-r2));

            } else if (type == "ridge") {
                // 中心山脊，四周低平原
                h = 100.0 * std::exp(-r2);

            } else if (type == "river") {
                // 河流流域：一条蜿蜒河谷从左到右贯穿，两侧高地
                // 模拟黄河/尼罗河/两河流域
                Real norm_x = (x - xmin) / (xmax - xmin);     // [0,1]
                Real norm_y = (y - ymin) / (ymax - ymin);     // [0,1]
                Real river_y = 0.5 + 0.15 * std::sin(norm_x * 3.14159 * 3.0);
                Real dist_river = std::abs(norm_y - river_y);
                Real river_valley = std::exp(-dist_river * dist_river * 80.0);
                // Floodplain: wider flat area near river
                Real floodplain = std::exp(-dist_river * dist_river * 15.0);
                // Mountains on edges
                Real edge_y = std::min(norm_y, 1.0 - norm_y);
                Real mountains = std::exp(-edge_y * edge_y * 20.0) * 80.0;
                h = mountains + 30.0 * (1.0 - floodplain) - 5.0 * river_valley;
                h = std::max(0.0, h);

            } else if (type == "basins") {
                // 多盆地：3-4个低洼盆地被山脊分隔
                // 模拟地中海周边/中国地理（关中、中原、巴蜀、江南）
                Real norm_x = (x - xmin) / (xmax - xmin);
                Real norm_y = (y - ymin) / (ymax - ymin);

                struct Basin { double cx, cy, sx, sy; };
                constexpr Basin basins[] = {
                    {0.25, 0.35, 0.12, 0.10},  // 西北盆地（关中）
                    {0.55, 0.55, 0.15, 0.12},  // 中原
                    {0.25, 0.70, 0.10, 0.08},  // 西南盆地（巴蜀）
                    {0.75, 0.35, 0.12, 0.10},  // 东北平原
                };

                Real base = 60.0;
                for (const auto& b : basins) {
                    Real bx = (norm_x - b.cx) / b.sx;
                    Real by = (norm_y - b.cy) / b.sy;
                    base -= 55.0 * std::exp(-(bx * bx + by * by));
                }
                // Edge mountains
                Real ex = std::min(norm_x, 1.0 - norm_x);
                Real ey = std::min(norm_y, 1.0 - norm_y);
                Real edge = std::min(ex, ey);
                base += 40.0 * std::exp(-edge * edge * 30.0);

                h = std::max(0.0, base);

            } else if (type == "continent") {
                // 大陆：中央大陆被海洋（高势垒）环绕
                // 内部有河谷网络和山脉
                Real norm_x = (x - xmin) / (xmax - xmin);
                Real norm_y = (y - ymin) / (ymax - ymin);

                // Ocean: high potential at edges
                Real ex = std::min(norm_x, 1.0 - norm_x);
                Real ey = std::min(norm_y, 1.0 - norm_y);
                Real coast = std::min(ex, ey);
                Real ocean = 200.0 * std::exp(-coast * coast * 50.0);

                // Mountain chain running NE-SW
                Real mt_dist = std::abs(norm_y - (1.2 - norm_x));
                Real mountains = 60.0 * std::exp(-mt_dist * mt_dist * 100.0);

                // Fertile plains: two lowland areas on either side of mountains
                Real plain1_dx = norm_x - 0.35;
                Real plain1_dy = norm_y - 0.4;
                Real plain1 = 30.0 * std::exp(-(plain1_dx*plain1_dx + plain1_dy*plain1_dy) * 8.0);

                Real plain2_dx = norm_x - 0.65;
                Real plain2_dy = norm_y - 0.6;
                Real plain2 = 30.0 * std::exp(-(plain2_dx*plain2_dx + plain2_dy*plain2_dy) * 8.0);

                h = ocean + mountains + 20.0 - plain1 - plain2;
                h = std::max(0.0, h);

            } else if (type == "china") {
                // 中国式地形：一个大型连通平原 + 几条河流汇聚 + 西部高原边缘
                // 核心特征：空间约束少，平原开阔，利于统一
                Real norm_x = (x - xmin) / (xmax - xmin);
                Real norm_y = (y - ymin) / (ymax - ymin);

                // Western highland (青藏高原边缘): steep wall on left
                Real west_wall = 100.0 * std::exp(-(norm_x * norm_x) * 40.0);

                // Northern mountains (燕山): gentle ridge along top
                Real north_mt = 50.0 * std::exp(-((1.0 - norm_y) * (1.0 - norm_y)) * 30.0);

                // Southern hills (南岭): low ridge at ~30% from bottom
                Real south_ridge_dist = std::abs(norm_y - 0.25);
                Real south_hills = 25.0 * std::exp(-south_ridge_dist * south_ridge_dist * 80.0);

                // Great Central Plain (华北平原 + 长江中下游): large connected lowland
                Real plain_cx = 0.55, plain_cy = 0.55;
                Real pdx = (norm_x - plain_cx), pdy = (norm_y - plain_cy);
                // Elongated east-west
                Real plain = 70.0 * std::exp(-(pdx * pdx * 3.0 + pdy * pdy * 4.0));

                // Yellow River (黄河): west to east through northern plain
                Real yr_y = 0.65 + 0.08 * std::sin(norm_x * 3.14159 * 2.0);
                Real yr_dist = std::abs(norm_y - yr_y);
                Real yellow_river = 15.0 * std::exp(-yr_dist * yr_dist * 200.0);

                // Yangtze River (长江): west to east through central plain
                Real yz_y = 0.45 + 0.06 * std::sin(norm_x * 3.14159 * 2.5 + 1.0);
                Real yz_dist = std::abs(norm_y - yz_y);
                Real yangtze = 15.0 * std::exp(-yz_dist * yz_dist * 200.0);

                // Edge ocean
                Real edge_x = std::min(norm_x, 1.0 - norm_x);
                Real edge_y = std::min(norm_y, 1.0 - norm_y);
                Real edge = std::min(edge_x, edge_y);
                Real edge_mt = 30.0 * std::exp(-edge * edge * 40.0);

                h = west_wall + north_mt + south_hills + edge_mt
                    + 40.0 - plain - yellow_river - yangtze;
                h = std::max(0.0, h);

            } else if (type == "europe") {
                // 欧洲式地形：多条高山脉分割空间为独立盆地
                // 核心特征：山脉屏障密集，平原被隔离，利于碎裂
                Real norm_x = (x - xmin) / (xmax - xmin);
                Real norm_y = (y - ymin) / (ymax - ymin);

                // Alps (阿尔卑斯): major E-W chain through center
                Real alps_y = 0.55 + 0.08 * std::sin(norm_x * 3.14159 * 2.0);
                Real alps_dist = std::abs(norm_y - alps_y);
                Real alps = 90.0 * std::exp(-alps_dist * alps_dist * 120.0);

                // Pyrenees (比利牛斯): SW barrier
                Real pyr_y = 0.30;
                Real pyr_x_center = 0.25;
                Real pyr_dx = norm_x - pyr_x_center;
                Real pyr_dy = norm_y - pyr_y;
                Real pyr = 70.0 * std::exp(-(pyr_dx * pyr_dx * 60.0 + pyr_dy * pyr_dy * 120.0));

                // Carpathians (喀尔巴阡): curved chain in east
                Real carp_angle = std::atan2(norm_y - 0.6, norm_x - 0.75);
                Real carp_r = std::sqrt((norm_x - 0.75) * (norm_x - 0.75)
                                      + (norm_y - 0.6) * (norm_y - 0.6));
                Real carp_target_r = 0.18;
                Real carp_dist = std::abs(carp_r - carp_target_r);
                Real carp = 60.0 * std::exp(-carp_dist * carp_dist * 300.0);
                if (carp_angle < -0.5 || carp_angle > 2.5) carp = 0.0;

                // Scandinavian ridge (斯堪的纳维亚): north
                Real scand_dist = std::abs(norm_y - 0.85);
                Real scand = 50.0 * std::exp(-scand_dist * scand_dist * 100.0)
                           * std::exp(-(norm_x - 0.4) * (norm_x - 0.4) * 8.0);

                // Isolated basins (盆地): France, Po Valley, Hungary, Iberia, NW Europe
                struct Basin { double cx, cy, sx, sy, depth; };
                constexpr Basin basins[] = {
                    {0.25, 0.50, 0.10, 0.08, 60.0},  // France
                    {0.50, 0.45, 0.06, 0.05, 50.0},  // Po Valley
                    {0.70, 0.55, 0.08, 0.07, 55.0},  // Hungarian Plain
                    {0.20, 0.20, 0.08, 0.07, 45.0},  // Iberia
                    {0.45, 0.70, 0.10, 0.08, 55.0},  // NW Europe
                    {0.80, 0.40, 0.07, 0.06, 40.0},  // Balkans
                };

                Real basin_sum = 0.0;
                for (const auto& b : basins) {
                    Real bdx = (norm_x - b.cx) / b.sx;
                    Real bdy = (norm_y - b.cy) / b.sy;
                    basin_sum += b.depth * std::exp(-(bdx * bdx + bdy * bdy));
                }

                // Ocean edges
                Real ex = std::min(norm_x, 1.0 - norm_x);
                Real ey = std::min(norm_y, 1.0 - norm_y);
                Real edge = std::min(ex, ey);
                Real ocean = 60.0 * std::exp(-edge * edge * 40.0);

                h = ocean + alps + pyr + carp + scand + 40.0 - basin_sum;
                h = std::max(0.0, h);

            } else {
                h = 0.0;
            }
            data_[static_cast<std::size_t>(r) * ncols + c] = h;
        }
    }

    compute_minmax();
}

// ─── 双线性插值 ───────────────────────────────────────────

Real TerrainGrid::elevation(Real x, Real y) const noexcept {
    if (data_.empty()) return 0.0;

    Real fx = (x - xmin_) / cellsize_;
    Real fy = (y - ymin_) / cellsize_;

    fx = std::clamp(fx, 0.0, static_cast<Real>(ncols_ - 1));
    fy = std::clamp(fy, 0.0, static_cast<Real>(nrows_ - 1));

    int c0 = static_cast<int>(fx);
    int r0 = static_cast<int>(fy);
    int c1 = std::min(c0 + 1, ncols_ - 1);
    int r1 = std::min(r0 + 1, nrows_ - 1);

    Real tx = fx - c0;
    Real ty = fy - r0;

    Real h00 = at(r0, c0);
    Real h10 = at(r0, c1);
    Real h01 = at(r1, c0);
    Real h11 = at(r1, c1);

    return (1 - tx) * (1 - ty) * h00 +
           tx       * (1 - ty) * h10 +
           (1 - tx) * ty       * h01 +
           tx       * ty       * h11;
}

// ─── 梯度（中心差分）────────────────────────────────────────

Vec2 TerrainGrid::gradient(Real x, Real y) const noexcept {
    if (data_.empty()) return {0.0, 0.0};

    const Real eps = cellsize_ * 0.5;
    Real dhdx = (elevation(x + eps, y) - elevation(x - eps, y)) / (2.0 * eps);
    Real dhdy = (elevation(x, y + eps) - elevation(x, y - eps)) / (2.0 * eps);
    return {dhdx, dhdy};
}

// ─── 势能与力 ─────────────────────────────────────────────

Real TerrainGrid::potential(Real x, Real y, Real scale) const noexcept {
    return scale * (elevation(x, y) - h_min_);
}

Vec2 TerrainGrid::force(Real x, Real y, Real scale) const noexcept {
    auto grad = gradient(x, y);
    return {-scale * grad[0], -scale * grad[1]};
}

// ─── 批量力计算 ───────────────────────────────────────────

Real compute_grid_terrain_forces(
    const Real* __restrict__ x_data,
    Real* __restrict__ force_buf,
    Index count,
    const TerrainGrid& grid,
    Real scale
) {
    if (!grid.loaded()) return 0.0;

    Real total_pe = 0.0;

    #pragma omp parallel for schedule(static) reduction(+:total_pe) if(count > 256)
    for (Index i = 0; i < count; ++i) {
        const Real xi = x_data[2 * i];
        const Real yi = x_data[2 * i + 1];

        auto f = grid.force(xi, yi, scale);
        force_buf[2 * i]     += f[0];
        force_buf[2 * i + 1] += f[1];

        total_pe += grid.potential(xi, yi, scale);
    }

    return total_pe;
}

Real grid_terrain_potential(
    Real x, Real y,
    const TerrainGrid& grid,
    Real scale
) {
    if (!grid.loaded()) return 0.0;
    // 河谷（低高程）返回负值（肥沃），高地返回接近 0
    return -scale * (grid.h_max() - grid.elevation(x, y));
}

} // namespace politeia
