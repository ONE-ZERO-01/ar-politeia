#include "river/river_field.hpp"

#include <algorithm>
#include <cmath>
#include <fstream>
#include <sstream>
#include <stdexcept>
#include <utility>
#include <vector>

namespace politeia {

namespace {

struct Polyline {
    std::vector<std::pair<Real, Real>> points;
    Real amplitude = 1.0;
};

Real clamp01(Real v) noexcept {
    return std::max(0.0, std::min(1.0, v));
}

Real segment_distance_sq(Real x, Real y,
                         Real x1, Real y1,
                         Real x2, Real y2) noexcept {
    const Real dx = x2 - x1;
    const Real dy = y2 - y1;
    const Real len_sq = dx * dx + dy * dy;
    if (len_sq < 1e-15) {
        const Real px = x - x1;
        const Real py = y - y1;
        return px * px + py * py;
    }
    const Real t = std::max(0.0, std::min(1.0, ((x - x1) * dx + (y - y1) * dy) / len_sq));
    const Real proj_x = x1 + t * dx;
    const Real proj_y = y1 + t * dy;
    const Real px = x - proj_x;
    const Real py = y - proj_y;
    return px * px + py * py;
}

Real polyline_distance_sq(Real x, Real y, const Polyline& line) noexcept {
    if (line.points.empty()) return 1e12;
    if (line.points.size() == 1) {
        const Real dx = x - line.points.front().first;
        const Real dy = y - line.points.front().second;
        return dx * dx + dy * dy;
    }

    Real best = 1e12;
    for (std::size_t i = 1; i < line.points.size(); ++i) {
        best = std::min(best, segment_distance_sq(
            x, y,
            line.points[i - 1].first, line.points[i - 1].second,
            line.points[i].first, line.points[i].second
        ));
    }
    return best;
}

Polyline make_line(std::initializer_list<std::pair<Real, Real>> pts, Real amplitude = 1.0) {
    Polyline line;
    line.points = pts;
    line.amplitude = amplitude;
    return line;
}

} // namespace

Real RiverField::interp(const std::vector<Real>& field, Real x, Real y, Real fallback) const noexcept {
    if (field.empty() || nrows_ < 1 || ncols_ < 1) return fallback;
    if (nrows_ == 1 || ncols_ == 1) return field.front();

    Real fx = (x - xmin_) / cellsize_;
    Real fy = (y - ymin_) / cellsize_;
    fx = std::max(0.0, std::min(fx, static_cast<Real>(ncols_ - 1)));
    fy = std::max(0.0, std::min(fy, static_cast<Real>(nrows_ - 1)));

    int ix = static_cast<int>(fx);
    int iy = static_cast<int>(fy);
    ix = std::min(ix, ncols_ - 2);
    iy = std::min(iy, nrows_ - 2);
    const Real tx = fx - ix;
    const Real ty = fy - iy;

    const Real v00 = field[iy * ncols_ + ix];
    const Real v10 = field[iy * ncols_ + ix + 1];
    const Real v01 = field[(iy + 1) * ncols_ + ix];
    const Real v11 = field[(iy + 1) * ncols_ + ix + 1];

    return (1.0 - tx) * (1.0 - ty) * v00
         + tx * (1.0 - ty) * v10
         + (1.0 - tx) * ty * v01
         + tx * ty * v11;
}

Real RiverField::proximity(Real x, Real y) const noexcept {
    return clamp01(interp(proximity_data_, x, y, 0.0));
}

Real RiverField::discharge(Real x, Real y) const noexcept {
    if (discharge_data_.empty()) return 0.0;
    return std::max(0.0, interp(discharge_data_, x, y, 0.0));
}

RiverCell RiverField::cell_at(Real x, Real y) const noexcept {
    return RiverCell{proximity(x, y), discharge(x, y)};
}

Vec2 RiverField::gradient(Real x, Real y) const noexcept {
    if (!loaded()) return {0.0, 0.0};
    const Real h = std::max(cellsize_, 1e-6);
    const Real px1 = proximity(x + h, y);
    const Real px0 = proximity(x - h, y);
    const Real py1 = proximity(x, y + h);
    const Real py0 = proximity(x, y - h);
    return {(px1 - px0) / (2.0 * h), (py1 - py0) / (2.0 * h)};
}

Vec2 RiverField::force(Real x, Real y, Real scale) const noexcept {
    const Vec2 g = gradient(x, y);
    return {scale * g[0], scale * g[1]};
}

Real RiverField::corridor_bonus(Real x, Real y,
                                Real proximity_scale,
                                Real discharge_scale) const noexcept {
    const RiverCell cell = cell_at(x, y);
    return 1.0 + proximity_scale * cell.proximity + discharge_scale * cell.discharge;
}

void RiverField::load_ascii(const std::string& filepath) {
    std::ifstream file(filepath);
    if (!file.is_open()) {
        throw std::runtime_error("Cannot open river field file: " + filepath);
    }

    auto read_header = [&](int& nr, int& nc, Real& xll, Real& yll, Real& cs) {
        std::string line;
        std::string key;
        Real nodata = -9999.0;
        for (int i = 0; i < 6; ++i) {
            if (!std::getline(file, line)) {
                throw std::runtime_error("Unexpected EOF in river field header: " + filepath);
            }
            std::istringstream iss(line);
            iss >> key;
            if (key == "ncols") iss >> nc;
            else if (key == "nrows") iss >> nr;
            else if (key == "xllcorner") iss >> xll;
            else if (key == "yllcorner") iss >> yll;
            else if (key == "cellsize") iss >> cs;
            else if (key == "NODATA_value") iss >> nodata;
        }
    };

    int nr = 0, nc = 0;
    Real xll = 0.0, yll = 0.0, cs = 1.0;
    read_header(nr, nc, xll, yll, cs);
    nrows_ = nr;
    ncols_ = nc;
    xmin_ = xll;
    ymin_ = yll;
    cellsize_ = cs;

    proximity_data_.assign(nrows_ * ncols_, 0.0);
    for (int r = nrows_ - 1; r >= 0; --r) {
        for (int c = 0; c < ncols_; ++c) {
            file >> proximity_data_[r * ncols_ + c];
        }
    }

    const std::streampos pos = file.tellg();
    std::string maybe_key;
    if (!(file >> maybe_key)) {
        discharge_data_.clear();
        return;
    }
    if (maybe_key != "ncols") {
        discharge_data_.clear();
        return;
    }
    file.seekg(pos);

    int nr2 = 0, nc2 = 0;
    Real xll2 = 0.0, yll2 = 0.0, cs2 = 1.0;
    read_header(nr2, nc2, xll2, yll2, cs2);
    if (nr2 != nrows_ || nc2 != ncols_) {
        throw std::runtime_error("River field second band shape mismatch: " + filepath);
    }
    discharge_data_.assign(nrows_ * ncols_, 0.0);
    for (int r = nrows_ - 1; r >= 0; --r) {
        for (int c = 0; c < ncols_; ++c) {
            file >> discharge_data_[r * ncols_ + c];
        }
    }
}

void RiverField::load_binary(const std::string& filepath,
                             int nrows, int ncols,
                             Real xmin, Real ymin, Real cellsize) {
    std::ifstream file(filepath, std::ios::binary);
    if (!file.is_open()) {
        throw std::runtime_error("Cannot open river field binary: " + filepath);
    }

    nrows_ = nrows;
    ncols_ = ncols;
    xmin_ = xmin;
    ymin_ = ymin;
    cellsize_ = cellsize;

    proximity_data_.assign(static_cast<std::size_t>(nrows_) * static_cast<std::size_t>(ncols_), 0.0);
    file.read(reinterpret_cast<char*>(proximity_data_.data()),
              static_cast<std::streamsize>(sizeof(Real) * proximity_data_.size()));
    if (!file) {
        throw std::runtime_error("Incomplete read of river field binary: " + filepath);
    }
    discharge_data_.clear();
}

void RiverField::generate_synthetic(int nrows, int ncols,
                                    Real xmin, Real ymin,
                                    Real xmax, Real ymax,
                                    const std::string& type) {
    nrows_ = nrows;
    ncols_ = ncols;
    xmin_ = xmin;
    ymin_ = ymin;
    cellsize_ = (xmax - xmin) / std::max(ncols - 1, 1);
    proximity_data_.assign(static_cast<std::size_t>(nrows_) * static_cast<std::size_t>(ncols_), 0.0);
    discharge_data_.assign(static_cast<std::size_t>(nrows_) * static_cast<std::size_t>(ncols_), 0.0);

    std::vector<Polyline> lines;
    if (type == "nile") {
        lines.push_back(make_line({{0.55, 0.10}, {0.53, 0.28}, {0.52, 0.45}, {0.54, 0.70}, {0.56, 0.92}}, 1.4));
    } else if (type == "mesopotamia") {
        lines.push_back(make_line({{0.43, 0.88}, {0.46, 0.70}, {0.49, 0.50}, {0.50, 0.25}}, 1.1));
        lines.push_back(make_line({{0.54, 0.88}, {0.56, 0.68}, {0.55, 0.48}, {0.51, 0.24}}, 1.1));
    } else if (type == "china") {
        lines.push_back(make_line({{0.18, 0.63}, {0.32, 0.60}, {0.48, 0.58}, {0.66, 0.60}, {0.84, 0.56}}, 1.2));
        lines.push_back(make_line({{0.20, 0.46}, {0.38, 0.43}, {0.55, 0.41}, {0.75, 0.39}, {0.90, 0.37}}, 1.0));
    } else {
        lines.push_back(make_line({{0.10, 0.52}, {0.25, 0.56}, {0.42, 0.50}, {0.60, 0.54}, {0.85, 0.48}}, 1.1));
        lines.push_back(make_line({{0.50, 0.08}, {0.48, 0.24}, {0.46, 0.42}, {0.47, 0.62}, {0.50, 0.92}}, 1.3));
        lines.push_back(make_line({{0.15, 0.35}, {0.30, 0.33}, {0.46, 0.30}, {0.68, 0.28}, {0.88, 0.25}}, 0.9));
        lines.push_back(make_line({{0.22, 0.72}, {0.36, 0.70}, {0.55, 0.67}, {0.76, 0.64}, {0.92, 0.61}}, 0.8));
    }

    const Real sigma = 0.035;
    for (int r = 0; r < nrows_; ++r) {
        const Real ny = (nrows_ > 1) ? static_cast<Real>(r) / static_cast<Real>(nrows_ - 1) : 0.0;
        for (int c = 0; c < ncols_; ++c) {
            const Real nx = (ncols_ > 1) ? static_cast<Real>(c) / static_cast<Real>(ncols_ - 1) : 0.0;

            Real prox = 0.0;
            Real flow = 0.0;
            for (const auto& line : lines) {
                const Real d2 = polyline_distance_sq(nx, ny, line);
                const Real g = line.amplitude * std::exp(-d2 / (2.0 * sigma * sigma));
                prox = std::max(prox, g);
                flow = std::max(flow, 0.75 * g * line.amplitude);
            }

            proximity_data_[r * ncols_ + c] = clamp01(prox);
            discharge_data_[r * ncols_ + c] = std::max(0.0, flow);
        }
    }
}

} // namespace politeia
