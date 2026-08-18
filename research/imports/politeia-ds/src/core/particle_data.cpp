#include "core/particle_data.hpp"

#include <algorithm>
#include <stdexcept>

namespace politeia {

ParticleData::ParticleData(Index capacity, int culture_dim, int immune_dim)
    : culture_dim_(culture_dim), immune_dim_(immune_dim) {
    if (capacity > 0) {
        reserve(capacity);
    }
}

void ParticleData::reserve(Index new_capacity) {
    if (new_capacity <= capacity_) return;
    grow_to(new_capacity);
}

void ParticleData::set_id_seed(int rank) {
    // Each rank gets a non-overlapping 40-bit window: rank * 2^40
    next_gid_ = static_cast<Id>(rank) * (Id(1) << 40);
}

void ParticleData::grow_to(Index new_cap) {
    x_.resize(new_cap * SPATIAL_DIM, 0.0);
    p_.resize(new_cap * SPATIAL_DIM, 0.0);
    w_.resize(new_cap, 0.0);
    eps_.resize(new_cap, 0.0);
    age_.resize(new_cap, 0.0);
    cv_.resize(new_cap * culture_dim_, 0.0);
    if (immune_dim_ > 0) {
        imm_.resize(new_cap * immune_dim_, 0.0);
    }
    sex_.resize(new_cap, 0);
    last_birth_time_.resize(new_cap, -1000.0);
    gid_.resize(new_cap, -1);
    superior_.resize(new_cap, -1);
    loyalty_.resize(new_cap, 0.0);
    status_.resize(new_cap, ParticleStatus::Dead);
    force_.resize(new_cap * SPATIAL_DIM, 0.0);
    capacity_ = new_cap;
}

void ParticleData::rebuild_gid_map() {
    gid_map_.clear();
    gid_map_.reserve(count_);
    for (Index i = 0; i < count_; ++i) {
        if (status_[i] == ParticleStatus::Alive) {
            gid_map_[gid_[i]] = i;
        }
    }
}

Index ParticleData::add_particle(
    Vec2 pos, Vec2 mom, Real wealth, Real epsilon, Real age
) {
    if (count_ >= capacity_) {
        Index new_cap = (capacity_ == 0) ? 64 : capacity_ * 2;
        grow_to(new_cap);
    }

    Index i = count_;
    x_[2 * i]     = pos[0];
    x_[2 * i + 1] = pos[1];
    p_[2 * i]     = mom[0];
    p_[2 * i + 1] = mom[1];
    w_[i]    = wealth;
    eps_[i]  = epsilon;
    age_[i]  = age;
    sex_[i]  = 0;
    last_birth_time_[i] = -1000.0;
    gid_[i] = next_gid_++;
    superior_[i] = -1;
    loyalty_[i] = 0.0;
    status_[i] = ParticleStatus::Alive;

    for (int d = 0; d < culture_dim_; ++d) {
        cv_[i * culture_dim_ + d] = 0.0;
    }

    gid_map_[gid_[i]] = i;
    ++count_;
    return i;
}

Index ParticleData::add_particle_with_gid(
    Vec2 pos, Vec2 mom, Real wealth, Real epsilon, Real age, Id gid
) {
    if (count_ >= capacity_) {
        Index new_cap = (capacity_ == 0) ? 64 : capacity_ * 2;
        grow_to(new_cap);
    }

    Index i = count_;
    x_[2 * i]     = pos[0];
    x_[2 * i + 1] = pos[1];
    p_[2 * i]     = mom[0];
    p_[2 * i + 1] = mom[1];
    w_[i]    = wealth;
    eps_[i]  = epsilon;
    age_[i]  = age;
    sex_[i]  = 0;
    last_birth_time_[i] = -1000.0;
    gid_[i] = gid;
    superior_[i] = -1;
    loyalty_[i] = 0.0;
    status_[i] = ParticleStatus::Alive;

    for (int d = 0; d < culture_dim_; ++d) {
        cv_[i * culture_dim_ + d] = 0.0;
    }

    gid_map_[gid] = i;
    ++count_;
    return i;
}

void ParticleData::mark_dead(Index i) {
    assert(i < count_);
    status_[i] = ParticleStatus::Dead;
}

Index ParticleData::compact() {
    Index write = 0;
    for (Index read = 0; read < count_; ++read) {
        if (status_[read] != ParticleStatus::Dead) {
            if (write != read) {
                x_[2 * write]     = x_[2 * read];
                x_[2 * write + 1] = x_[2 * read + 1];
                p_[2 * write]     = p_[2 * read];
                p_[2 * write + 1] = p_[2 * read + 1];
                w_[write]    = w_[read];
                eps_[write]  = eps_[read];
                age_[write]  = age_[read];
                sex_[write]  = sex_[read];
                last_birth_time_[write] = last_birth_time_[read];
                gid_[write] = gid_[read];
                superior_[write] = superior_[read];
                loyalty_[write] = loyalty_[read];
                status_[write] = status_[read];

                for (int d = 0; d < culture_dim_; ++d) {
                    cv_[write * culture_dim_ + d] = cv_[read * culture_dim_ + d];
                }
                if (immune_dim_ > 0) {
                    for (int d = 0; d < immune_dim_; ++d) {
                        imm_[write * immune_dim_ + d] = imm_[read * immune_dim_ + d];
                    }
                }
            }
            ++write;
        }
    }
    Index removed = count_ - write;
    count_ = write;
    rebuild_gid_map();
    return removed;
}

Index ParticleData::compact_with_map(std::vector<Index>& old_to_new) {
    old_to_new.assign(count_, static_cast<Index>(-1));
    Index write = 0;
    for (Index read = 0; read < count_; ++read) {
        if (status_[read] != ParticleStatus::Dead) {
            old_to_new[read] = write;
            if (write != read) {
                x_[2 * write]     = x_[2 * read];
                x_[2 * write + 1] = x_[2 * read + 1];
                p_[2 * write]     = p_[2 * read];
                p_[2 * write + 1] = p_[2 * read + 1];
                w_[write]    = w_[read];
                eps_[write]  = eps_[read];
                age_[write]  = age_[read];
                sex_[write]  = sex_[read];
                last_birth_time_[write] = last_birth_time_[read];
                gid_[write] = gid_[read];
                superior_[write] = superior_[read];
                loyalty_[write] = loyalty_[read];
                status_[write] = status_[read];

                for (int d = 0; d < culture_dim_; ++d) {
                    cv_[write * culture_dim_ + d] = cv_[read * culture_dim_ + d];
                }
                if (immune_dim_ > 0) {
                    for (int d = 0; d < immune_dim_; ++d) {
                        imm_[write * immune_dim_ + d] = imm_[read * immune_dim_ + d];
                    }
                }
            }
            ++write;
        }
    }
    Index removed = count_ - write;
    count_ = write;
    rebuild_gid_map();
    return removed;
}

} // namespace politeia
