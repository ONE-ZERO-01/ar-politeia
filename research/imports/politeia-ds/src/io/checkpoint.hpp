#pragma once
/// @file checkpoint.hpp
/// @brief Process-count-independent checkpoint/restart for elastic scaling.
///
/// Binary format (single file, no process topology encoded):
///   Header (128 bytes, fixed)  ->  Config block  ->  Particle records
///
/// Any number of MPI ranks can read a checkpoint written by any other number.
/// After reading, SFC rebalance + redistribute restores spatial locality.

#include "core/types.hpp"
#include "core/particle_data.hpp"
#include "core/config.hpp"

#include <string>
#include <cstdint>
#include <vector>

namespace politeia {

constexpr uint64_t CHECKPOINT_MAGIC   = 0x4356534D43484B50ULL; // "CVSMCHKP"
constexpr uint32_t CHECKPOINT_VERSION = 1;
constexpr size_t   CHECKPOINT_HEADER_BYTES = 128;

struct CheckpointHeader {
    uint64_t magic        = CHECKPOINT_MAGIC;
    uint32_t version      = CHECKPOINT_VERSION;
    uint32_t _pad0        = 0;
    uint64_t particle_count = 0;
    uint64_t step         = 0;
    double   time         = 0.0;
    uint32_t culture_dim  = 2;
    uint32_t immune_dim   = 0;
    uint32_t record_size  = 0;   // bytes per particle record
    uint32_t _pad1        = 0;
    // remaining bytes to fill 128-byte header
    uint64_t _reserved[9] = {};
};
static_assert(sizeof(CheckpointHeader) == CHECKPOINT_HEADER_BYTES,
              "CheckpointHeader must be exactly 128 bytes");

/// Compute the byte size of one serialised particle record.
inline uint32_t checkpoint_record_size(int culture_dim, int immune_dim) {
    // x,y + px,py + w + eps + age + sex + last_birth + gid + superior + loyalty
    //   = 12 doubles, plus culture_dim + immune_dim doubles
    return static_cast<uint32_t>((12 + culture_dim + immune_dim) * sizeof(double));
}

/// Serialize one particle into a contiguous double buffer (returns doubles written).
int checkpoint_pack_particle(const ParticleData& pd, Index i,
                             double* buf, int culture_dim, int immune_dim);

/// Deserialize one particle from a double buffer into ParticleData.
void checkpoint_unpack_particle(ParticleData& pd, const double* buf,
                                int culture_dim, int immune_dim);

// ─── Write ─────────────────────────────────────────────────────────────────

/// Write a checkpoint file.  All ranks participate (collective).
/// Automatically selects Gather-to-Root (<=10M particles) or MPI-IO.
/// @param filepath   Output file path (same on all ranks).
/// @param particles  Local particles on this rank.
/// @param cfg        Simulation config (serialised into file for restart).
/// @param cfg_path   Path to original .cfg file (contents embedded in checkpoint).
/// @param step       Current simulation step.
/// @param rank       MPI rank.
/// @param nprocs     Total MPI ranks.
void write_checkpoint(const std::string& filepath,
                      const ParticleData& particles,
                      const SimConfig& cfg,
                      const std::string& cfg_path,
                      uint64_t step,
                      int rank, int nprocs);

// ─── Read ──────────────────────────────────────────────────────────────────

/// Read checkpoint header (any single rank can call this).
CheckpointHeader read_checkpoint_header(const std::string& filepath);

/// Read a checkpoint file.  All ranks participate (collective).
/// Each rank reads its share of particles: [N*rank/P, N*(rank+1)/P).
/// Caller must SFC rebalance + redistribute afterwards.
/// @param filepath    Checkpoint file path.
/// @param particles   Output: local particles for this rank.
/// @param step_out    Output: simulation step stored in checkpoint.
/// @param time_out    Output: simulation time stored in checkpoint.
/// @param rank        MPI rank.
/// @param nprocs      Total MPI ranks.
void read_checkpoint(const std::string& filepath,
                     ParticleData& particles,
                     uint64_t& step_out,
                     double& time_out,
                     int rank, int nprocs);

// ─── Gather utility ────────────────────────────────────────────────────────

/// Gather all particles from all ranks to rank 0.
/// Returns a ParticleData containing all particles (only valid on rank 0;
/// other ranks get an empty container).
ParticleData gather_all_particles(const ParticleData& local,
                                  int rank, int nprocs);

} // namespace politeia
