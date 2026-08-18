#pragma once

#include "core/types.hpp"
#include "core/particle_data.hpp"

#include <vector>
#include <array>

#ifdef POLITEIA_USE_MPI
#include <mpi.h>
#endif

namespace politeia {

/// 2D Cartesian domain decomposition for MPI parallelization.
/// Divides the global domain into px × py sub-domains.
/// Each rank owns particles within its sub-domain.
class DomainDecomposition {
public:
    DomainDecomposition() = default;

    /// Initialize decomposition. Must be called after MPI_Init.
    void init(
        Real global_xmin, Real global_xmax,
        Real global_ymin, Real global_ymax,
        int px, int py,
        int rank, int nprocs
    );

    /// Check if a position falls within this rank's sub-domain.
    [[nodiscard]] bool owns(Real x, Real y) const noexcept;

    /// Migrate particles that have left this rank's sub-domain to the correct rank.
    /// Removes migrated particles from local data, receives incoming particles.
    void migrate_particles(ParticleData& particles);

    /// Exchange ghost particles (halo) with neighboring ranks for force computation.
    /// Populates ghost_particles with copies from neighbors within cutoff.
    void exchange_halos(
        const ParticleData& particles,
        Real cutoff,
        ParticleData& ghost_particles
    );

    /// Perform MPI_Allreduce to get global sum of a scalar.
    [[nodiscard]] Real global_sum(Real local_val) const;

    /// Perform MPI_Allreduce to get global sum of an integer.
    [[nodiscard]] Index global_sum_index(Index local_val) const;

    // --- Accessors ---
    [[nodiscard]] Real local_xmin() const noexcept { return local_xmin_; }
    [[nodiscard]] Real local_xmax() const noexcept { return local_xmax_; }
    [[nodiscard]] Real local_ymin() const noexcept { return local_ymin_; }
    [[nodiscard]] Real local_ymax() const noexcept { return local_ymax_; }
    [[nodiscard]] int rank() const noexcept { return rank_; }
    [[nodiscard]] int nprocs() const noexcept { return nprocs_; }
    [[nodiscard]] int px() const noexcept { return px_; }
    [[nodiscard]] int py() const noexcept { return py_; }
    [[nodiscard]] bool is_serial() const noexcept { return nprocs_ <= 1; }

    /// Get rank index (ix, iy) in the 2D grid.
    [[nodiscard]] std::array<int, 2> rank_coords() const noexcept { return {rank_ix_, rank_iy_}; }

    /// Get neighbor rank for direction. Returns -1 if boundary.
    [[nodiscard]] int neighbor(int dx, int dy) const noexcept;

private:
    Real global_xmin_ = 0, global_xmax_ = 100;
    Real global_ymin_ = 0, global_ymax_ = 100;
    Real local_xmin_ = 0, local_xmax_ = 100;
    Real local_ymin_ = 0, local_ymax_ = 100;
    int px_ = 1, py_ = 1;
    int rank_ = 0, nprocs_ = 1;
    int rank_ix_ = 0, rank_iy_ = 0;

#ifdef POLITEIA_USE_MPI
    MPI_Comm comm_ = MPI_COMM_WORLD;
#endif

    /// Pack a particle into a buffer for MPI send.
    void pack_particle(const ParticleData& pd, Index i, std::vector<Real>& buf) const;

    /// Unpack a particle from a buffer after MPI recv.
    void unpack_particle(ParticleData& pd, const Real* buf, int culture_dim) const;

    /// Number of doubles per particle in the send buffer.
    [[nodiscard]] int pack_size(int culture_dim) const noexcept;
};

} // namespace politeia
