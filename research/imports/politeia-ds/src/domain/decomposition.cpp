#include "domain/decomposition.hpp"

#include <algorithm>
#include <cmath>
#include <cassert>

namespace politeia {

void DomainDecomposition::init(
    Real global_xmin, Real global_xmax,
    Real global_ymin, Real global_ymax,
    int px, int py,
    int rank, int nprocs
) {
    global_xmin_ = global_xmin;
    global_xmax_ = global_xmax;
    global_ymin_ = global_ymin;
    global_ymax_ = global_ymax;
    px_ = px;
    py_ = py;
    rank_ = rank;
    nprocs_ = nprocs;

    rank_ix_ = rank % px;
    rank_iy_ = rank / px;

    Real dx = (global_xmax - global_xmin) / px;
    Real dy = (global_ymax - global_ymin) / py;

    local_xmin_ = global_xmin + rank_ix_ * dx;
    local_xmax_ = global_xmin + (rank_ix_ + 1) * dx;
    local_ymin_ = global_ymin + rank_iy_ * dy;
    local_ymax_ = global_ymin + (rank_iy_ + 1) * dy;
}

bool DomainDecomposition::owns(Real x, Real y) const noexcept {
    return x >= local_xmin_ && x < local_xmax_ &&
           y >= local_ymin_ && y < local_ymax_;
}

int DomainDecomposition::neighbor(int dx, int dy) const noexcept {
    int nx = rank_ix_ + dx;
    int ny = rank_iy_ + dy;
    if (nx < 0 || nx >= px_ || ny < 0 || ny >= py_) return -1;
    return ny * px_ + nx;
}

int DomainDecomposition::pack_size(int culture_dim) const noexcept {
    // x(2) + p(2) + w(1) + eps(1) + age(1) + sex(1) + last_birth_time(1) + status(1)
    // + gid(1) + superior(1) + loyalty(1) + culture(cd)
    return 13 + culture_dim;
}

void DomainDecomposition::pack_particle(
    const ParticleData& pd, Index i, std::vector<Real>& buf
) const {
    auto pos = pd.position(i);
    auto mom = pd.momentum(i);
    buf.push_back(pos[0]);            // 0
    buf.push_back(pos[1]);            // 1
    buf.push_back(mom[0]);            // 2
    buf.push_back(mom[1]);            // 3
    buf.push_back(pd.wealth(i));      // 4
    buf.push_back(pd.epsilon(i));     // 5
    buf.push_back(pd.age(i));         // 6
    buf.push_back(static_cast<Real>(pd.sex(i))); // 7
    buf.push_back(pd.last_birth_time(i)); // 8
    buf.push_back(static_cast<Real>(static_cast<int>(pd.status(i)))); // 9
    buf.push_back(static_cast<Real>(pd.global_id(i))); // 10
    buf.push_back(static_cast<Real>(pd.superior(i)));   // 11
    buf.push_back(pd.loyalty(i));     // 12
    for (int d = 0; d < pd.culture_dim(); ++d) {
        buf.push_back(pd.culture(i, d));
    }
}

void DomainDecomposition::unpack_particle(
    ParticleData& pd, const Real* buf, int culture_dim
) const {
    Vec2 pos = {buf[0], buf[1]};
    Vec2 mom = {buf[2], buf[3]};
    Real w = buf[4];
    Real eps = buf[5];
    Real age = buf[6];
    Id gid = static_cast<Id>(buf[10]);

    Index idx = pd.add_particle_with_gid(pos, mom, w, eps, age, gid);
    pd.sex(idx) = static_cast<uint8_t>(buf[7]);
    pd.last_birth_time(idx) = buf[8];
    pd.set_status(idx, static_cast<ParticleStatus>(static_cast<int>(buf[9])));
    pd.superior(idx) = static_cast<Id>(buf[11]);
    pd.loyalty(idx) = buf[12];
    for (int d = 0; d < culture_dim; ++d) {
        pd.culture(idx, d) = buf[13 + d];
    }
}

void DomainDecomposition::migrate_particles(ParticleData& particles) {
    if (is_serial()) return;

#ifdef POLITEIA_USE_MPI
    const int cd = particles.culture_dim();
    const int ps = pack_size(cd);

    // Classify particles that have left this subdomain
    // Direction encoding: 9 cells (3x3), center=4 is "stays"
    std::array<std::vector<Real>, 9> send_bufs;

    std::vector<Index> to_remove;

    for (Index i = 0; i < particles.count(); ++i) {
        if (particles.status(i) == ParticleStatus::Dead) continue;

        auto pos = particles.position(i);
        int dx = 0, dy = 0;
        if (pos[0] < local_xmin_) dx = -1;
        if (pos[0] >= local_xmax_) dx = 1;
        if (pos[1] < local_ymin_) dy = -1;
        if (pos[1] >= local_ymax_) dy = 1;

        if (dx == 0 && dy == 0) continue;

        int dir = (dy + 1) * 3 + (dx + 1);
        pack_particle(particles, i, send_bufs[dir]);
        to_remove.push_back(i);
    }

    for (auto it = to_remove.rbegin(); it != to_remove.rend(); ++it) {
        particles.mark_dead(*it);
    }

    // Exchange with all 8 neighbors
    constexpr int dir_dx[] = {-1, 0, 1, -1, 0, 1, -1, 0, 1};
    constexpr int dir_dy[] = {-1, -1, -1, 0, 0, 0, 1, 1, 1};

    for (int dir = 0; dir < 9; ++dir) {
        if (dir == 4) continue;  // self

        int nb = neighbor(dir_dx[dir], dir_dy[dir]);
        int opp_dir = 8 - dir;
        int opp_nb = neighbor(-dir_dx[dir], -dir_dy[dir]);

        int send_count = static_cast<int>(send_bufs[dir].size());
        int recv_count = 0;

        if (nb >= 0 && opp_nb >= 0) {
            MPI_Sendrecv(
                &send_count, 1, MPI_INT, nb, 100 + dir,
                &recv_count, 1, MPI_INT, opp_nb, 100 + opp_dir,
                comm_, MPI_STATUS_IGNORE
            );
        } else if (nb >= 0) {
            MPI_Send(&send_count, 1, MPI_INT, nb, 100 + dir, comm_);
        } else if (opp_nb >= 0) {
            MPI_Recv(&recv_count, 1, MPI_INT, opp_nb, 100 + opp_dir, comm_, MPI_STATUS_IGNORE);
        }

        if (recv_count > 0) {
            std::vector<Real> recv_buf(recv_count);
            if (nb >= 0) {
                MPI_Sendrecv(
                    send_bufs[dir].data(), send_count, MPI_DOUBLE, nb, 200 + dir,
                    recv_buf.data(), recv_count, MPI_DOUBLE, opp_nb, 200 + opp_dir,
                    comm_, MPI_STATUS_IGNORE
                );
            } else {
                MPI_Recv(recv_buf.data(), recv_count, MPI_DOUBLE, opp_nb, 200 + opp_dir, comm_, MPI_STATUS_IGNORE);
            }

            int n_particles = recv_count / ps;
            for (int p = 0; p < n_particles; ++p) {
                unpack_particle(particles, &recv_buf[p * ps], cd);
            }
        } else if (send_count > 0 && nb >= 0) {
            MPI_Send(send_bufs[dir].data(), send_count, MPI_DOUBLE, nb, 200 + dir, comm_);
        }
    }
#endif
}

void DomainDecomposition::exchange_halos(
    const ParticleData& particles,
    Real cutoff,
    ParticleData& ghost_particles
) {
    if (is_serial()) return;

#ifdef POLITEIA_USE_MPI
    const int cd = particles.culture_dim();
    const int ps = pack_size(cd);

    // Pack particles near each boundary
    constexpr int dir_dx[] = {-1, 0, 1, -1, 1, -1, 0, 1};
    constexpr int dir_dy[] = {-1, -1, -1, 0, 0, 1, 1, 1};

    for (int d = 0; d < 8; ++d) {
        int nb = neighbor(dir_dx[d], dir_dy[d]);
        if (nb < 0) continue;

        std::vector<Real> send_buf;

        for (Index i = 0; i < particles.count(); ++i) {
            if (particles.status(i) == ParticleStatus::Dead) continue;
            auto pos = particles.position(i);

            bool near_boundary = false;
            if (dir_dx[d] == -1 && pos[0] - local_xmin_ < cutoff) near_boundary = true;
            if (dir_dx[d] ==  1 && local_xmax_ - pos[0] < cutoff) near_boundary = true;
            if (dir_dy[d] == -1 && pos[1] - local_ymin_ < cutoff) near_boundary = true;
            if (dir_dy[d] ==  1 && local_ymax_ - pos[1] < cutoff) near_boundary = true;

            if (dir_dx[d] == 0) {
                // For pure vertical neighbors, don't filter on x
            }
            if (dir_dy[d] == 0) {
                // For pure horizontal neighbors, don't filter on y
            }

            if (near_boundary) {
                pack_particle(particles, i, send_buf);
            }
        }

        int opp_d = 7 - d;
        int opp_nb = neighbor(-dir_dx[d], -dir_dy[d]);

        int send_count = static_cast<int>(send_buf.size());
        int recv_count = 0;

        MPI_Sendrecv(
            &send_count, 1, MPI_INT, nb, 300 + d,
            &recv_count, 1, MPI_INT, (opp_nb >= 0 ? opp_nb : MPI_PROC_NULL), 300 + opp_d,
            comm_, MPI_STATUS_IGNORE
        );

        if (recv_count > 0) {
            std::vector<Real> recv_buf(recv_count);
            MPI_Sendrecv(
                send_buf.data(), send_count, MPI_DOUBLE, nb, 400 + d,
                recv_buf.data(), recv_count, MPI_DOUBLE, (opp_nb >= 0 ? opp_nb : MPI_PROC_NULL), 400 + opp_d,
                comm_, MPI_STATUS_IGNORE
            );

            int n_ghosts = recv_count / ps;
            for (int p = 0; p < n_ghosts; ++p) {
                unpack_particle(ghost_particles, &recv_buf[p * ps], cd);
            }
        }
    }
#endif
}

Real DomainDecomposition::global_sum(Real local_val) const {
#ifdef POLITEIA_USE_MPI
    if (!is_serial()) {
        Real global_val = 0.0;
        MPI_Allreduce(&local_val, &global_val, 1, MPI_DOUBLE, MPI_SUM, comm_);
        return global_val;
    }
#endif
    return local_val;
}

Index DomainDecomposition::global_sum_index(Index local_val) const {
#ifdef POLITEIA_USE_MPI
    if (!is_serial()) {
        unsigned long long local_ull = local_val;
        unsigned long long global_ull = 0;
        MPI_Allreduce(&local_ull, &global_ull, 1, MPI_UNSIGNED_LONG_LONG, MPI_SUM, comm_);
        return static_cast<Index>(global_ull);
    }
#endif
    return local_val;
}

} // namespace politeia
