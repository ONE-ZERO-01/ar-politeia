#pragma once

#include "types.hpp"
#include <vector>
#include <cassert>
#include <cstdint>
#include <unordered_map>

namespace politeia {

/// SoA (Structure of Arrays) container for particle data.
/// Each attribute is stored as a contiguous array for cache-friendly access
/// in hot-path force calculations and integration loops.
///
/// Global ID system: every particle receives a unique global_id at creation
/// that persists across MPI migration and compaction. The superior field stores
/// a global ID (not local index), enabling cross-rank hierarchy tracking.
class ParticleData {
public:
    explicit ParticleData(Index capacity, int culture_dim = 2, int immune_dim = 0);

    /// Set the rank-based ID seed: rank * 2^40 to avoid collisions.
    /// Must be called once before adding any particles.
    void set_id_seed(int rank);

    /// Add a new particle with auto-assigned global ID. Returns local index.
    [[nodiscard]] Index add_particle(
        Vec2 pos, Vec2 mom, Real wealth, Real epsilon, Real age
    );

    /// Add a particle with an explicit global ID (used by MPI unpack).
    [[nodiscard]] Index add_particle_with_gid(
        Vec2 pos, Vec2 mom, Real wealth, Real epsilon, Real age, Id gid
    );

    /// Mark a particle as dead. Does not immediately remove it.
    void mark_dead(Index i);

    /// Remove all dead particles, compacting arrays. Returns number removed.
    Index compact();

    /// Compact and produce an old→new index map (for repairing pointers like superior_i).
    /// old_to_new[old_index] = new_index, or Index(-1) if removed.
    Index compact_with_map(std::vector<Index>& old_to_new);

    /// Reserve additional capacity.
    void reserve(Index new_capacity);

    // --- Accessors (non-const for hot path direct access) ---

    Real* x_data() noexcept { return x_.data(); }
    Real* p_data() noexcept { return p_.data(); }
    Real* w_data() noexcept { return w_.data(); }
    Real* eps_data() noexcept { return eps_.data(); }
    Real* age_data() noexcept { return age_.data(); }
    Real* cv_data() noexcept { return cv_.data(); }

    const Real* x_data() const noexcept { return x_.data(); }
    const Real* p_data() const noexcept { return p_.data(); }
    const Real* w_data() const noexcept { return w_.data(); }
    const Real* eps_data() const noexcept { return eps_.data(); }
    const Real* age_data() const noexcept { return age_.data(); }
    const Real* cv_data() const noexcept { return cv_.data(); }

    // --- Per-particle element access ---

    Vec2 position(Index i) const noexcept {
        assert(i < count_);
        return {x_[2 * i], x_[2 * i + 1]};
    }

    void set_position(Index i, Vec2 pos) noexcept {
        assert(i < count_);
        x_[2 * i] = pos[0];
        x_[2 * i + 1] = pos[1];
    }

    Vec2 momentum(Index i) const noexcept {
        assert(i < count_);
        return {p_[2 * i], p_[2 * i + 1]};
    }

    void set_momentum(Index i, Vec2 mom) noexcept {
        assert(i < count_);
        p_[2 * i] = mom[0];
        p_[2 * i + 1] = mom[1];
    }

    Real wealth(Index i) const noexcept { assert(i < count_); return w_[i]; }
    Real& wealth(Index i) noexcept { assert(i < count_); return w_[i]; }

    Real epsilon(Index i) const noexcept { assert(i < count_); return eps_[i]; }
    Real& epsilon(Index i) noexcept { assert(i < count_); return eps_[i]; }

    Real age(Index i) const noexcept { assert(i < count_); return age_[i]; }
    Real& age(Index i) noexcept { assert(i < count_); return age_[i]; }

    Real last_birth_time(Index i) const noexcept { assert(i < count_); return last_birth_time_[i]; }
    Real& last_birth_time(Index i) noexcept { assert(i < count_); return last_birth_time_[i]; }

    ParticleStatus status(Index i) const noexcept {
        assert(i < count_);
        return status_[i];
    }

    void set_status(Index i, ParticleStatus s) noexcept {
        assert(i < count_);
        status_[i] = s;
    }

    /// Access culture vector component j of particle i
    Real culture(Index i, int j) const noexcept {
        assert(i < count_ && j < culture_dim_);
        return cv_[i * culture_dim_ + j];
    }

    Real& culture(Index i, int j) noexcept {
        assert(i < count_ && j < culture_dim_);
        return cv_[i * culture_dim_ + j];
    }

    /// Sex: 0=female, 1=male. Only meaningful when gender_enabled=true.
    uint8_t sex(Index i) const noexcept { assert(i < count_); return sex_[i]; }
    uint8_t& sex(Index i) noexcept { assert(i < count_); return sex_[i]; }

    /// 全局唯一 ID，跨 MPI rank 和 compact 保持稳定
    Id global_id(Index i) const noexcept { assert(i < count_); return gid_[i]; }

    /// 依附指针：存储上级的 **global_id**，-1 = 无上级（独立根节点）
    Id superior(Index i) const noexcept { assert(i < count_); return superior_[i]; }
    Id& superior(Index i) noexcept { assert(i < count_); return superior_[i]; }

    /// 忠诚度 L_ij ∈ [0,1]：i 对 superior(i) 的忠诚度
    Real loyalty(Index i) const noexcept { assert(i < count_); return loyalty_[i]; }
    Real& loyalty(Index i) noexcept { assert(i < count_); return loyalty_[i]; }

    /// 通过全局 ID 查找本地索引。返回 -1 表示不在本 rank。
    [[nodiscard]] Index gid_to_local(Id gid) const noexcept {
        auto it = gid_map_.find(gid);
        return (it != gid_map_.end()) ? it->second : static_cast<Index>(-1);
    }

    /// 重建 global_id → local_index 查找表（在迁移/compact后调用）
    void rebuild_gid_map();

    /// 免疫向量第 k 种病原体的免疫力，d^k_i ∈ [0,1]
    Real immunity(Index i, int k) const noexcept {
        assert(i < count_ && k < immune_dim_);
        return imm_[i * immune_dim_ + k];
    }

    Real& immunity(Index i, int k) noexcept {
        assert(i < count_ && k < immune_dim_);
        return imm_[i * immune_dim_ + k];
    }

    // --- Metadata ---

    [[nodiscard]] Index count() const noexcept { return count_; }
    [[nodiscard]] Index capacity() const noexcept { return capacity_; }
    [[nodiscard]] int culture_dim() const noexcept { return culture_dim_; }
    [[nodiscard]] int immune_dim() const noexcept { return immune_dim_; }

    // --- Force buffer (managed externally or here) ---

    std::vector<Real>& force_buffer() noexcept { return force_; }
    const std::vector<Real>& force_buffer() const noexcept { return force_; }

private:
    // Spatial DOFs (interleaved: x0,y0,x1,y1,...)
    std::vector<Real> x_;
    std::vector<Real> p_;

    // Internal DOFs
    std::vector<Real> w_;
    std::vector<Real> cv_;
    std::vector<Real> eps_;

    // Parameters
    std::vector<Real> age_;
    std::vector<Real> imm_;

    // Status
    std::vector<ParticleStatus> status_;

    // Sex: 0=female, 1=male
    std::vector<uint8_t> sex_;

    // Reproduction cooldown: time of last birth event
    std::vector<Real> last_birth_time_;

    // Global ID: unique across all ranks and all time
    std::vector<Id> gid_;
    Id next_gid_ = 0;  // monotonically increasing ID counter

    // Hierarchy (Phase 13): attachment pointer stores global_id of superior
    std::vector<Id> superior_;     // -1 = root (no superior)
    std::vector<Real> loyalty_;    // L_ij ∈ [0,1]

    // global_id → local index lookup (rebuilt after compact/migration)
    std::unordered_map<Id, Index> gid_map_;

    // Force accumulator (interleaved like x_)
    std::vector<Real> force_;

    Index count_ = 0;
    Index capacity_ = 0;
    int culture_dim_ = 2;
    int immune_dim_ = 0;

    void grow_to(Index new_cap);
};

} // namespace politeia
