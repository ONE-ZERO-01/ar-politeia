/// @file sfc_decomposition.cpp
/// @brief Morton Z-curve 域分解实现
///
/// 核心算法流程：
///   1. 每个粒子计算 Morton key（O(1) 位操作）
///   2. 全局直方图统计每个 key 范围的粒子数（MPI_Allreduce）
///   3. 前缀和确定分割点（每个 rank 管理 N/P 个粒子）
///   4. 按分割点迁移粒子（MPI_Alltoallv）
///   5. 邻居发现：bounding box 扩展法

#include "domain/sfc_decomposition.hpp"
#include "core/constants.hpp"

#include <algorithm>
#include <numeric>
#include <cmath>
#include <cassert>
#include <cstring>

namespace politeia {

void SFCDecomposition::init(
    Real global_xmin, Real global_xmax,
    Real global_ymin, Real global_ymax,
    int level, int rank, int nprocs
) {
    global_xmin_ = global_xmin;
    global_xmax_ = global_xmax;
    global_ymin_ = global_ymin;
    global_ymax_ = global_ymax;
    level_ = level;
    rank_ = rank;
    nprocs_ = nprocs;

    // 初始均匀分割：key 空间 [0, 2^(2*level)) 均匀切割
    const MortonKey total_cells = MortonKey(1) << (2 * level);
    splits_.resize(nprocs + 1);
    for (int r = 0; r <= nprocs; ++r) {
        splits_[r] = (total_cells * r) / nprocs;
    }

    bbox_ = {global_xmin, global_xmax, global_ymin, global_ymax};
}

MortonKey SFCDecomposition::compute_key(Real x, Real y) const noexcept {
    return point_to_morton(x, y, global_xmin_, global_xmax_,
                           global_ymin_, global_ymax_, level_);
}

std::vector<MortonKey> SFCDecomposition::compute_keys(const ParticleData& particles) const {
    const Index n = particles.count();
    std::vector<MortonKey> keys(n);
    const Real* x = particles.x_data();
    for (Index i = 0; i < n; ++i) {
        if (particles.status(i) == ParticleStatus::Dead) {
            keys[i] = 0;
            continue;
        }
        keys[i] = compute_key(x[2 * i], x[2 * i + 1]);
    }
    return keys;
}

int SFCDecomposition::key_to_rank(MortonKey key) const {
    // 二分搜索找到 key 所属的 rank
    auto it = std::upper_bound(splits_.begin(), splits_.end(), key);
    int r = static_cast<int>(std::distance(splits_.begin(), it)) - 1;
    if (r < 0) r = 0;
    if (r >= nprocs_) r = nprocs_ - 1;
    return r;
}

void SFCDecomposition::rebalance(const std::vector<MortonKey>& local_keys) {
    if (is_serial()) return;

#ifdef POLITEIA_USE_MPI
    // 用采样法确定全局分割点：
    // 1. 每个 rank 从本地 keys 中均匀采样 S 个
    // 2. MPI_Allgather 所有采样
    // 3. 全局排序采样，取等间距分割点

    const int S = std::min(static_cast<int>(local_keys.size()), 1000);
    std::vector<MortonKey> local_samples(S);

    if (!local_keys.empty()) {
        // 均匀采样
        for (int i = 0; i < S; ++i) {
            Index idx = (local_keys.size() * i) / S;
            local_samples[i] = local_keys[idx];
        }
        std::sort(local_samples.begin(), local_samples.end());
    }

    // 收集所有 rank 的采样
    std::vector<int> recv_counts(nprocs_);
    int send_count = S;
    MPI_Allgather(&send_count, 1, MPI_INT, recv_counts.data(), 1, MPI_INT, comm_);

    std::vector<int> displs(nprocs_);
    displs[0] = 0;
    for (int r = 1; r < nprocs_; ++r) {
        displs[r] = displs[r - 1] + recv_counts[r - 1];
    }
    int total_samples = displs[nprocs_ - 1] + recv_counts[nprocs_ - 1];

    std::vector<MortonKey> all_samples(total_samples);
    MPI_Allgatherv(
        local_samples.data(), S, MPI_UNSIGNED_LONG_LONG,
        all_samples.data(), recv_counts.data(), displs.data(), MPI_UNSIGNED_LONG_LONG,
        comm_
    );

    // 全局排序
    std::sort(all_samples.begin(), all_samples.end());

    // 取等间距分割点
    splits_[0] = 0;
    for (int r = 1; r < nprocs_; ++r) {
        Index idx = (static_cast<Index>(total_samples) * r) / nprocs_;
        if (idx >= static_cast<Index>(total_samples)) idx = total_samples - 1;
        splits_[r] = all_samples[idx];
    }
    const MortonKey total_cells = MortonKey(1) << (2 * level_);
    splits_[nprocs_] = total_cells;
#endif
}

int SFCDecomposition::pack_size() const noexcept {
    // x(2) + p(2) + w(1) + eps(1) + age(1) + sex(1) + last_birth(1) + status(1)
    // + gid(1) + superior(1) + loyalty(1) + culture(D)
    return 13 + constants::DEFAULT_CULTURE_DIM;
}

void SFCDecomposition::pack_particle(
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

void SFCDecomposition::unpack_particle(ParticleData& pd, const Real* buf) const {
    Vec2 pos = {buf[0], buf[1]};
    Vec2 mom = {buf[2], buf[3]};
    Id gid = static_cast<Id>(buf[10]);
    Index idx = pd.add_particle_with_gid(pos, mom, buf[4], buf[5], buf[6], gid);
    pd.sex(idx) = static_cast<uint8_t>(buf[7]);
    pd.last_birth_time(idx) = buf[8];
    pd.set_status(idx, static_cast<ParticleStatus>(static_cast<int>(buf[9])));
    pd.superior(idx) = static_cast<Id>(buf[11]);
    pd.loyalty(idx) = buf[12];
    for (int d = 0; d < pd.culture_dim(); ++d) {
        pd.culture(idx, d) = buf[13 + d];
    }
}

void SFCDecomposition::redistribute(ParticleData& particles) {
    if (is_serial()) return;

#ifdef POLITEIA_USE_MPI
    const int ps = pack_size();
    const Index n = particles.count();

    // 对每个粒子确定目标 rank
    auto keys = compute_keys(particles);
    std::vector<std::vector<Real>> send_bufs(nprocs_);

    for (Index i = 0; i < n; ++i) {
        if (particles.status(i) == ParticleStatus::Dead) continue;
        int target = key_to_rank(keys[i]);
        if (target != rank_) {
            pack_particle(particles, i, send_bufs[target]);
            particles.mark_dead(i);
        }
    }

    // 交换发送/接收计数
    std::vector<int> send_counts(nprocs_), recv_counts(nprocs_);
    for (int r = 0; r < nprocs_; ++r) {
        send_counts[r] = static_cast<int>(send_bufs[r].size());
    }
    MPI_Alltoall(send_counts.data(), 1, MPI_INT,
                 recv_counts.data(), 1, MPI_INT, comm_);

    // 准备 Alltoallv 缓冲区
    std::vector<int> send_displs(nprocs_), recv_displs(nprocs_);
    send_displs[0] = recv_displs[0] = 0;
    for (int r = 1; r < nprocs_; ++r) {
        send_displs[r] = send_displs[r - 1] + send_counts[r - 1];
        recv_displs[r] = recv_displs[r - 1] + recv_counts[r - 1];
    }

    int total_send = send_displs[nprocs_ - 1] + send_counts[nprocs_ - 1];
    int total_recv = recv_displs[nprocs_ - 1] + recv_counts[nprocs_ - 1];

    // 合并发送缓冲
    std::vector<Real> send_flat(total_send);
    for (int r = 0; r < nprocs_; ++r) {
        std::memcpy(&send_flat[send_displs[r]], send_bufs[r].data(),
                     send_counts[r] * sizeof(Real));
    }

    std::vector<Real> recv_flat(total_recv);
    MPI_Alltoallv(
        send_flat.data(), send_counts.data(), send_displs.data(), MPI_DOUBLE,
        recv_flat.data(), recv_counts.data(), recv_displs.data(), MPI_DOUBLE,
        comm_
    );

    // 解包接收到的粒子
    int offset = 0;
    while (offset + ps <= total_recv) {
        unpack_particle(particles, &recv_flat[offset]);
        offset += ps;
    }

    // 压缩掉已标记为 Dead 的粒子
    particles.compact();

    // 更新 bounding box
    update_bbox(particles);
#endif
}

void SFCDecomposition::migrate_particles(ParticleData& particles) {
    // 与 redistribute 逻辑相同，但只迁移越界的粒子
    if (is_serial()) return;

#ifdef POLITEIA_USE_MPI
    const int ps = pack_size();
    const Index n = particles.count();
    auto keys = compute_keys(particles);

    std::vector<std::vector<Real>> send_bufs(nprocs_);
    bool any_migrated = false;

    for (Index i = 0; i < n; ++i) {
        if (particles.status(i) == ParticleStatus::Dead) continue;
        int target = key_to_rank(keys[i]);
        if (target != rank_) {
            pack_particle(particles, i, send_bufs[target]);
            particles.mark_dead(i);
            any_migrated = true;
        }
    }

    // 快速检查：如果没有粒子需要迁移，跳过 Alltoall
    int local_flag = any_migrated ? 1 : 0;
    int global_flag = 0;
    MPI_Allreduce(&local_flag, &global_flag, 1, MPI_INT, MPI_MAX, comm_);
    if (!global_flag) return;

    std::vector<int> send_counts(nprocs_), recv_counts(nprocs_);
    for (int r = 0; r < nprocs_; ++r) {
        send_counts[r] = static_cast<int>(send_bufs[r].size());
    }
    MPI_Alltoall(send_counts.data(), 1, MPI_INT,
                 recv_counts.data(), 1, MPI_INT, comm_);

    std::vector<int> send_displs(nprocs_), recv_displs(nprocs_);
    send_displs[0] = recv_displs[0] = 0;
    for (int r = 1; r < nprocs_; ++r) {
        send_displs[r] = send_displs[r - 1] + send_counts[r - 1];
        recv_displs[r] = recv_displs[r - 1] + recv_counts[r - 1];
    }

    int total_send = send_displs[nprocs_ - 1] + send_counts[nprocs_ - 1];
    int total_recv = recv_displs[nprocs_ - 1] + recv_counts[nprocs_ - 1];

    std::vector<Real> send_flat(total_send);
    for (int r = 0; r < nprocs_; ++r) {
        if (send_counts[r] > 0) {
            std::memcpy(&send_flat[send_displs[r]], send_bufs[r].data(),
                         send_counts[r] * sizeof(Real));
        }
    }

    std::vector<Real> recv_flat(total_recv);
    MPI_Alltoallv(
        send_flat.data(), send_counts.data(), send_displs.data(), MPI_DOUBLE,
        recv_flat.data(), recv_counts.data(), recv_displs.data(), MPI_DOUBLE,
        comm_
    );

    int offset = 0;
    while (offset + ps <= total_recv) {
        unpack_particle(particles, &recv_flat[offset]);
        offset += ps;
    }

    particles.compact();
    update_bbox(particles);
#endif
}

void SFCDecomposition::update_bbox(const ParticleData& particles) {
    Real xmin = global_xmax_, xmax = global_xmin_;
    Real ymin = global_ymax_, ymax = global_ymin_;
    const Real* x = particles.x_data();
    for (Index i = 0; i < particles.count(); ++i) {
        if (particles.status(i) == ParticleStatus::Dead) continue;
        xmin = std::min(xmin, x[2 * i]);
        xmax = std::max(xmax, x[2 * i]);
        ymin = std::min(ymin, x[2 * i + 1]);
        ymax = std::max(ymax, x[2 * i + 1]);
    }
    if (particles.count() == 0) {
        xmin = xmax = 0.5 * (global_xmin_ + global_xmax_);
        ymin = ymax = 0.5 * (global_ymin_ + global_ymax_);
    }
    bbox_ = {xmin, xmax, ymin, ymax};
}

void SFCDecomposition::discover_neighbors(const ParticleData& particles, Real cutoff) {
    if (is_serial()) { neighbors_.clear(); return; }

#ifdef POLITEIA_USE_MPI
    update_bbox(particles);

    // 收集所有 rank 的 bounding box
    std::vector<Real> all_bbox(nprocs_ * 4);
    MPI_Allgather(bbox_.data(), 4, MPI_DOUBLE,
                  all_bbox.data(), 4, MPI_DOUBLE, comm_);

    // 本 rank 的扩展 bbox（扩展 cutoff）
    Real ext_xmin = bbox_[0] - cutoff;
    Real ext_xmax = bbox_[1] + cutoff;
    Real ext_ymin = bbox_[2] - cutoff;
    Real ext_ymax = bbox_[3] + cutoff;

    neighbors_.clear();
    for (int r = 0; r < nprocs_; ++r) {
        if (r == rank_) continue;

        Real r_xmin = all_bbox[4 * r];
        Real r_xmax = all_bbox[4 * r + 1];
        Real r_ymin = all_bbox[4 * r + 2];
        Real r_ymax = all_bbox[4 * r + 3];

        // 两个 bbox 是否重叠？
        if (ext_xmax >= r_xmin && ext_xmin <= r_xmax &&
            ext_ymax >= r_ymin && ext_ymin <= r_ymax) {
            neighbors_.push_back(r);
        }
    }
#endif
}

void SFCDecomposition::exchange_halos(
    const ParticleData& particles,
    Real cutoff,
    ParticleData& ghost_particles
) {
    if (is_serial()) return;

#ifdef POLITEIA_USE_MPI
    const int ps = pack_size();

    for (int nb : neighbors_) {
        // 收集 cutoff 范围内靠近 nb 的粒子
        std::vector<Real> send_buf;

        // 获取 nb 的 bounding box（需要从 discover_neighbors 中缓存）
        // 简化：发送所有在本 rank bbox 边界 cutoff 内的粒子
        const Real* x = particles.x_data();
        for (Index i = 0; i < particles.count(); ++i) {
            if (particles.status(i) == ParticleStatus::Dead) continue;
            Real px = x[2 * i], py = x[2 * i + 1];

            bool near_edge = false;
            if (px - bbox_[0] < cutoff || bbox_[1] - px < cutoff ||
                py - bbox_[2] < cutoff || bbox_[3] - py < cutoff) {
                near_edge = true;
            }

            if (near_edge) {
                pack_particle(particles, i, send_buf);
            }
        }

        int send_count = static_cast<int>(send_buf.size());
        int recv_count = 0;

        MPI_Sendrecv(&send_count, 1, MPI_INT, nb, 500,
                     &recv_count, 1, MPI_INT, nb, 500,
                     comm_, MPI_STATUS_IGNORE);

        if (recv_count > 0) {
            std::vector<Real> recv_buf(recv_count);
            MPI_Sendrecv(
                send_buf.data(), send_count, MPI_DOUBLE, nb, 501,
                recv_buf.data(), recv_count, MPI_DOUBLE, nb, 501,
                comm_, MPI_STATUS_IGNORE
            );

            int offset = 0;
            while (offset + ps <= recv_count) {
                unpack_particle(ghost_particles, &recv_buf[offset]);
                offset += ps;
            }
        } else if (send_count > 0) {
            MPI_Send(send_buf.data(), send_count, MPI_DOUBLE, nb, 501, comm_);
        }
    }
#endif
}

Real SFCDecomposition::global_sum(Real local_val) const {
#ifdef POLITEIA_USE_MPI
    if (!is_serial()) {
        Real global_val = 0.0;
        MPI_Allreduce(&local_val, &global_val, 1, MPI_DOUBLE, MPI_SUM, comm_);
        return global_val;
    }
#endif
    return local_val;
}

Index SFCDecomposition::global_sum_index(Index local_val) const {
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

SFCDecomposition::LoadStats SFCDecomposition::compute_load_stats(Index local_count) const {
    LoadStats stats;
    stats.local_count = local_count;

#ifdef POLITEIA_USE_MPI
    if (!is_serial()) {
        unsigned long long lc = local_count;
        unsigned long long gc_min = 0, gc_max = 0, gc_sum = 0;
        MPI_Allreduce(&lc, &gc_min, 1, MPI_UNSIGNED_LONG_LONG, MPI_MIN, comm_);
        MPI_Allreduce(&lc, &gc_max, 1, MPI_UNSIGNED_LONG_LONG, MPI_MAX, comm_);
        MPI_Allreduce(&lc, &gc_sum, 1, MPI_UNSIGNED_LONG_LONG, MPI_SUM, comm_);
        stats.global_min = gc_min;
        stats.global_max = gc_max;
        stats.global_total = gc_sum;
        stats.efficiency = (gc_max > 0) ? (static_cast<Real>(gc_sum) / nprocs_) / gc_max : 1.0;
    } else
#endif
    {
        stats.global_min = stats.global_max = stats.global_total = local_count;
        stats.efficiency = 1.0;
    }
    return stats;
}

} // namespace politeia
