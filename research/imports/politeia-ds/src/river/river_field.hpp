#pragma once

#include "core/types.hpp"

#include <string>
#include <vector>

namespace politeia {

struct RiverCell {
    Real proximity = 0.0;  // [0,1], larger means closer to a major river
    Real discharge = 0.0;  // optional flow strength proxy
};

class RiverField {
public:
    RiverField() = default;

    void load_ascii(const std::string& filepath);
    void load_binary(const std::string& filepath,
                     int nrows, int ncols,
                     Real xmin, Real ymin, Real cellsize);
    void generate_synthetic(int nrows, int ncols,
                            Real xmin, Real ymin,
                            Real xmax, Real ymax,
                            const std::string& type = "major_rivers");

    [[nodiscard]] bool loaded() const noexcept { return !proximity_data_.empty(); }
    [[nodiscard]] int nrows() const noexcept { return nrows_; }
    [[nodiscard]] int ncols() const noexcept { return ncols_; }
    [[nodiscard]] Real xmin() const noexcept { return xmin_; }
    [[nodiscard]] Real ymin() const noexcept { return ymin_; }
    [[nodiscard]] Real cellsize() const noexcept { return cellsize_; }

    [[nodiscard]] Real proximity(Real x, Real y) const noexcept;
    [[nodiscard]] Real discharge(Real x, Real y) const noexcept;
    [[nodiscard]] RiverCell cell_at(Real x, Real y) const noexcept;
    [[nodiscard]] Vec2 gradient(Real x, Real y) const noexcept;
    [[nodiscard]] Vec2 force(Real x, Real y, Real scale) const noexcept;
    [[nodiscard]] Real corridor_bonus(Real x, Real y,
                                      Real proximity_scale,
                                      Real discharge_scale = 0.0) const noexcept;

private:
    std::vector<Real> proximity_data_;
    std::vector<Real> discharge_data_;
    int nrows_ = 0;
    int ncols_ = 0;
    Real xmin_ = 0.0;
    Real ymin_ = 0.0;
    Real cellsize_ = 1.0;

    [[nodiscard]] Real interp(const std::vector<Real>& field, Real x, Real y, Real fallback) const noexcept;
};

} // namespace politeia
