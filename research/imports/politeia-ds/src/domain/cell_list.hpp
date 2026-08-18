#pragma once

#include "core/types.hpp"
#include <vector>
#include <cassert>

namespace politeia {

/// 2D cell list for O(N) neighbor searching with cutoff radius.
/// Divides the domain into uniform cells of size >= cutoff.
/// Each cell stores indices of particles within it.
class CellList {
public:
    CellList() = default;

    /// Initialize cell list for given domain and cutoff.
    void init(Real xmin, Real xmax, Real ymin, Real ymax, Real cutoff);

    /// Rebuild cell list from particle positions.
    /// x_data: interleaved [x0,y0,x1,y1,...], count: number of particles.
    void build(const Real* __restrict__ x_data, Index count);

    /// Iterate over all neighbor pairs within cutoff.
    /// Callback signature: void(Index i, Index j, Real dx, Real dy, Real r2)
    /// Only calls with i < j to avoid double counting.
    template <typename Func>
    void for_each_pair(const Real* __restrict__ x_data, Index count, Real cutoff_sq, Func&& func) const;

    /// Iterate over all neighbors of particle i within cutoff.
    /// Callback: void(Index j, Real dx, Real dy, Real r2)
    /// Each particle independently finds its neighbors — no i<j constraint.
    /// Suitable for OpenMP: each thread handles disjoint particles.
    template <typename Func>
    void for_neighbors_of(Index i, const Real* __restrict__ x_data,
                          Index count, Real cutoff_sq, Func&& func) const;

    [[nodiscard]] int nx() const noexcept { return nx_; }
    [[nodiscard]] int ny() const noexcept { return ny_; }
    [[nodiscard]] int total_cells() const noexcept { return nx_ * ny_; }

private:
    Real xmin_ = 0, xmax_ = 1, ymin_ = 0, ymax_ = 1;
    Real cell_size_ = 1;
    int nx_ = 1, ny_ = 1;

    // cell_start_[c] = index into particle_indices_ where cell c begins
    // cell_start_ has total_cells+1 entries (sentinel at end)
    std::vector<Index> cell_start_;
    std::vector<Index> particle_indices_;

    [[nodiscard]] int cell_index(Real x, Real y) const noexcept {
        int cx = static_cast<int>((x - xmin_) / cell_size_);
        int cy = static_cast<int>((y - ymin_) / cell_size_);
        if (cx < 0) cx = 0;
        if (cx >= nx_) cx = nx_ - 1;
        if (cy < 0) cy = 0;
        if (cy >= ny_) cy = ny_ - 1;
        return cy * nx_ + cx;
    }
};

// --- Template implementation (must be in header for inlining) ---

template <typename Func>
void CellList::for_each_pair(
    const Real* __restrict__ x_data, Index count, Real cutoff_sq, Func&& func
) const {
    for (int cy = 0; cy < ny_; ++cy) {
        for (int cx = 0; cx < nx_; ++cx) {
            const int c = cy * nx_ + cx;
            const Index c_begin = cell_start_[c];
            const Index c_end = cell_start_[c + 1];

            // Pairs within the same cell
            for (Index ii = c_begin; ii < c_end; ++ii) {
                for (Index jj = ii + 1; jj < c_end; ++jj) {
                    const Index i = particle_indices_[ii];
                    const Index j = particle_indices_[jj];
                    const Real dx = x_data[2 * j]     - x_data[2 * i];
                    const Real dy = x_data[2 * j + 1] - x_data[2 * i + 1];
                    const Real r2 = dx * dx + dy * dy;
                    if (r2 < cutoff_sq && r2 > 0.0) {
                        func(i, j, dx, dy, r2);
                    }
                }
            }

            // Pairs with neighboring cells (only forward neighbors to avoid double counting)
            // Neighbor offsets: (1,0), (0,1), (1,1), (-1,1)
            constexpr int neighbor_dx[] = {1, 0, 1, -1};
            constexpr int neighbor_dy[] = {0, 1, 1,  1};

            for (int n = 0; n < 4; ++n) {
                const int ncx = cx + neighbor_dx[n];
                const int ncy = cy + neighbor_dy[n];
                if (ncx < 0 || ncx >= nx_ || ncy < 0 || ncy >= ny_) continue;

                const int nc = ncy * nx_ + ncx;
                const Index nc_begin = cell_start_[nc];
                const Index nc_end = cell_start_[nc + 1];

                for (Index ii = c_begin; ii < c_end; ++ii) {
                    for (Index jj = nc_begin; jj < nc_end; ++jj) {
                        const Index i = particle_indices_[ii];
                        const Index j = particle_indices_[jj];
                        const Real dx = x_data[2 * j]     - x_data[2 * i];
                        const Real dy = x_data[2 * j + 1] - x_data[2 * i + 1];
                        const Real r2 = dx * dx + dy * dy;
                        if (r2 < cutoff_sq && r2 > 0.0) {
                            if (i < j) {
                                func(i, j, dx, dy, r2);
                            } else {
                                func(j, i, -dx, -dy, r2);
                            }
                        }
                    }
                }
            }
        }
    }
}

template <typename Func>
void CellList::for_neighbors_of(
    Index i, const Real* __restrict__ x_data,
    Index count, Real cutoff_sq, Func&& func
) const {
    const Real xi = x_data[2 * i];
    const Real yi = x_data[2 * i + 1];

    const int home_cx = static_cast<int>((xi - xmin_) / cell_size_);
    const int home_cy = static_cast<int>((yi - ymin_) / cell_size_);

    for (int dy = -1; dy <= 1; ++dy) {
        for (int dx = -1; dx <= 1; ++dx) {
            const int ncx = home_cx + dx;
            const int ncy = home_cy + dy;
            if (ncx < 0 || ncx >= nx_ || ncy < 0 || ncy >= ny_) continue;

            const int nc = ncy * nx_ + ncx;
            const Index nc_begin = cell_start_[nc];
            const Index nc_end = cell_start_[nc + 1];

            for (Index jj = nc_begin; jj < nc_end; ++jj) {
                const Index j = particle_indices_[jj];
                if (j == i) continue;
                const Real ddx = x_data[2 * j]     - xi;
                const Real ddy = x_data[2 * j + 1] - yi;
                const Real r2 = ddx * ddx + ddy * ddy;
                if (r2 < cutoff_sq && r2 > 0.0) {
                    func(j, ddx, ddy, r2);
                }
            }
        }
    }
}

} // namespace politeia
