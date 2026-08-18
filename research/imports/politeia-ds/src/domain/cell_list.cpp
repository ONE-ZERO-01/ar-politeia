#include "domain/cell_list.hpp"

#include <algorithm>
#include <cmath>

namespace politeia {

void CellList::init(Real xmin, Real xmax, Real ymin, Real ymax, Real cutoff) {
    xmin_ = xmin;
    xmax_ = xmax;
    ymin_ = ymin;
    ymax_ = ymax;
    cell_size_ = cutoff;

    nx_ = std::max(1, static_cast<int>(std::floor((xmax - xmin) / cutoff)));
    ny_ = std::max(1, static_cast<int>(std::floor((ymax - ymin) / cutoff)));

    // Adjust cell_size to exactly cover domain
    cell_size_ = std::max((xmax - xmin) / nx_, (ymax - ymin) / ny_);
    nx_ = std::max(1, static_cast<int>(std::ceil((xmax - xmin) / cell_size_)));
    ny_ = std::max(1, static_cast<int>(std::ceil((ymax - ymin) / cell_size_)));

    cell_start_.resize(nx_ * ny_ + 1, 0);
}

void CellList::build(const Real* __restrict__ x_data, Index count) {
    const int total = nx_ * ny_;

    // Count particles per cell
    std::fill(cell_start_.begin(), cell_start_.end(), 0);

    for (Index i = 0; i < count; ++i) {
        int c = cell_index(x_data[2 * i], x_data[2 * i + 1]);
        cell_start_[c + 1]++;
    }

    // Prefix sum → cell_start_[c] = start index for cell c
    for (int c = 0; c < total; ++c) {
        cell_start_[c + 1] += cell_start_[c];
    }

    // Fill particle indices using a counting sort
    particle_indices_.resize(count);
    // Use a temporary copy of starts as write cursors
    std::vector<Index> cursor(cell_start_.begin(), cell_start_.begin() + total);

    for (Index i = 0; i < count; ++i) {
        int c = cell_index(x_data[2 * i], x_data[2 * i + 1]);
        particle_indices_[cursor[c]] = i;
        cursor[c]++;
    }
}

} // namespace politeia
