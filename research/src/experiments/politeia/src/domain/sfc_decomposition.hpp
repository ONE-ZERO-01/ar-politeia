#pragma once

/// @file sfc_decomposition.hpp
/// @brief 空间填充曲线 (Morton Z-curve) 域分解
///
/// 面向 80 亿粒子全球模拟的并行框架。将 2D 空间通过 Morton 曲线
/// 映射为 1D 有序序列，按粒子数均匀切割到各 MPI rank，实现：
///   - 任意粒子分布下的负载均衡（海洋 0 人、城市 10⁶/km²）
///   - O(N) 动态重平衡
///   - 空间局域性保持（相邻粒子大概率在同一 rank）
///
/// 替代原来的 2D Cartesian DomainDecomposition。

#include "core/types.hpp"
#include "core/particle_data.hpp"
#include "domain/morton.hpp"

#include <vector>
#include <array>

#ifdef POLITEIA_USE_MPI
#include <mpi.h>
#endif

namespace politeia {

/// SFC 域分解器
class SFCDecomposition {
public:
    SFCDecomposition() = default;

    /// 初始化：定义全局域和 Morton 网格分辨率
    /// @param level  Morton 网格层数（2^level × 2^level 个 cell）
    ///               level=20 → ~100万 cell（全球 ~100m 分辨率）
    void init(
        Real global_xmin, Real global_xmax,
        Real global_ymin, Real global_ymax,
        int level,
        int rank, int nprocs
    );

    /// 计算粒子的 Morton key
    [[nodiscard]] MortonKey compute_key(Real x, Real y) const noexcept;

    /// 计算所有本地粒子的 Morton key
    [[nodiscard]] std::vector<MortonKey> compute_keys(const ParticleData& particles) const;

    /// 负载均衡：根据全局粒子分布重新计算分割点。
    /// 分割点 splits[r] = rank r 管理的 key 范围起点。
    /// splits.size() = nprocs + 1，最后一个元素 = max_key + 1。
    void rebalance(const std::vector<MortonKey>& local_keys);

    /// 根据当前分割点，将粒子重分配到正确的 rank。
    void redistribute(ParticleData& particles);

    /// 发现需要 halo 通信的邻居 rank 列表。
    /// 基于 bounding box 扩展法：本 rank 的 bounding box 扩展 cutoff 后
    /// 与哪些其他 rank 的 bounding box 重叠。
    void discover_neighbors(const ParticleData& particles, Real cutoff);

    /// 与邻居 rank 交换 halo（ghost 粒子）。
    void exchange_halos(
        const ParticleData& particles,
        Real cutoff,
        ParticleData& ghost_particles
    );

    /// 将越界粒子迁移到正确的 rank。
    void migrate_particles(ParticleData& particles);

    /// 全局标量求和
    [[nodiscard]] Real global_sum(Real local_val) const;
    [[nodiscard]] Index global_sum_index(Index local_val) const;

    // --- 访问器 ---
    [[nodiscard]] int rank() const noexcept { return rank_; }
    [[nodiscard]] int nprocs() const noexcept { return nprocs_; }
    [[nodiscard]] bool is_serial() const noexcept { return nprocs_ <= 1; }
    [[nodiscard]] int level() const noexcept { return level_; }

    /// 本 rank 管理的 key 范围 [key_min, key_max)
    [[nodiscard]] MortonKey local_key_min() const noexcept { return splits_[rank_]; }
    [[nodiscard]] MortonKey local_key_max() const noexcept { return splits_[rank_ + 1]; }

    /// 本 rank 的 bounding box（由实际粒子位置决定）
    [[nodiscard]] Real local_xmin() const noexcept { return bbox_[0]; }
    [[nodiscard]] Real local_xmax() const noexcept { return bbox_[1]; }
    [[nodiscard]] Real local_ymin() const noexcept { return bbox_[2]; }
    [[nodiscard]] Real local_ymax() const noexcept { return bbox_[3]; }

    /// 邻居 rank 列表
    [[nodiscard]] const std::vector<int>& neighbors() const noexcept { return neighbors_; }

    /// 负载均衡指标
    struct LoadStats {
        Index local_count = 0;
        Index global_min = 0;
        Index global_max = 0;
        Index global_total = 0;
        Real efficiency = 0.0;  // avg/max
    };
    [[nodiscard]] LoadStats compute_load_stats(Index local_count) const;

private:
    Real global_xmin_ = 0, global_xmax_ = 1;
    Real global_ymin_ = 0, global_ymax_ = 1;
    int level_ = 10;
    int rank_ = 0, nprocs_ = 1;

    /// 分割点：rank r 管理 [splits_[r], splits_[r+1])
    std::vector<MortonKey> splits_;

    /// 本 rank 的 bounding box [xmin, xmax, ymin, ymax]
    std::array<Real, 4> bbox_ = {0, 1, 0, 1};

    /// 邻居 rank 列表（动态发现）
    std::vector<int> neighbors_;

#ifdef POLITEIA_USE_MPI
    MPI_Comm comm_ = MPI_COMM_WORLD;
#endif

    /// 确定一个 key 属于哪个 rank
    [[nodiscard]] int key_to_rank(MortonKey key) const;

    /// 打包/解包粒子
    void pack_particle(const ParticleData& pd, Index i, std::vector<Real>& buf) const;
    void unpack_particle(ParticleData& pd, const Real* buf) const;
    [[nodiscard]] int pack_size() const noexcept;

    /// 更新 bounding box
    void update_bbox(const ParticleData& particles);
};

} // namespace politeia
