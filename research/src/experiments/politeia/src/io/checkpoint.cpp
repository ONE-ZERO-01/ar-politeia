#include "io/checkpoint.hpp"

#include <fstream>
#include <stdexcept>
#include <iostream>
#include <cstring>
#include <numeric>

#ifdef POLITEIA_USE_MPI
#include <mpi.h>
#endif

namespace politeia {

// ─── Pack / Unpack one particle ────────────────────────────────────────────

int checkpoint_pack_particle(const ParticleData& pd, Index i,
                             double* buf, int culture_dim, int immune_dim) {
    int k = 0;
    auto pos = pd.position(i);
    auto mom = pd.momentum(i);
    buf[k++] = pos[0];
    buf[k++] = pos[1];
    buf[k++] = mom[0];
    buf[k++] = mom[1];
    buf[k++] = pd.wealth(i);
    buf[k++] = pd.epsilon(i);
    buf[k++] = pd.age(i);
    buf[k++] = static_cast<double>(pd.sex(i));
    buf[k++] = pd.last_birth_time(i);
    buf[k++] = static_cast<double>(pd.global_id(i));
    buf[k++] = static_cast<double>(pd.superior(i));
    buf[k++] = pd.loyalty(i);
    for (int d = 0; d < culture_dim; ++d) {
        buf[k++] = pd.culture(i, d);
    }
    for (int d = 0; d < immune_dim; ++d) {
        buf[k++] = pd.immunity(i, d);
    }
    return k;
}

void checkpoint_unpack_particle(ParticleData& pd, const double* buf,
                                int culture_dim, int immune_dim) {
    Vec2 pos = {buf[0], buf[1]};
    Vec2 mom = {buf[2], buf[3]};
    Id gid   = static_cast<Id>(buf[9]);
    Index idx = pd.add_particle_with_gid(pos, mom, buf[4], buf[5], buf[6], gid);
    pd.sex(idx) = static_cast<uint8_t>(buf[7]);
    pd.last_birth_time(idx) = buf[8];
    pd.superior(idx) = static_cast<Id>(buf[10]);
    pd.loyalty(idx)  = buf[11];
    for (int d = 0; d < culture_dim; ++d) {
        pd.culture(idx, d) = buf[12 + d];
    }
    for (int d = 0; d < immune_dim; ++d) {
        pd.immunity(idx, d) = buf[12 + culture_dim + d];
    }
}

// ─── Config text helpers ───────────────────────────────────────────────────

static std::string read_file_text(const std::string& path) {
    std::ifstream f(path);
    if (!f.is_open()) return "";
    return std::string((std::istreambuf_iterator<char>(f)),
                        std::istreambuf_iterator<char>());
}

static size_t align8(size_t n) {
    return (n + 7) & ~size_t(7);
}

// ─── Gather all particles to rank 0 ───────────────────────────────────────

ParticleData gather_all_particles(const ParticleData& local,
                                  int rank, int nprocs) {
    const int cdim = local.culture_dim();
    const int idim = local.immune_dim();
    const int doubles_per = 12 + cdim + idim;

#ifdef POLITEIA_USE_MPI
    // Count alive particles
    int local_alive = 0;
    for (Index i = 0; i < local.count(); ++i) {
        if (local.status(i) == ParticleStatus::Alive) ++local_alive;
    }

    // Gather counts
    std::vector<int> counts(nprocs);
    MPI_Gather(&local_alive, 1, MPI_INT,
               counts.data(), 1, MPI_INT, 0, MPI_COMM_WORLD);

    // Pack local alive particles
    std::vector<double> send_buf(static_cast<size_t>(local_alive) * doubles_per);
    int pos = 0;
    for (Index i = 0; i < local.count(); ++i) {
        if (local.status(i) != ParticleStatus::Alive) continue;
        checkpoint_pack_particle(local, i, &send_buf[pos], cdim, idim);
        pos += doubles_per;
    }

    // Compute displacements (in doubles)
    std::vector<int> send_counts(nprocs), displs(nprocs);
    if (rank == 0) {
        for (int r = 0; r < nprocs; ++r) {
            send_counts[r] = counts[r] * doubles_per;
        }
        displs[0] = 0;
        for (int r = 1; r < nprocs; ++r) {
            displs[r] = displs[r - 1] + send_counts[r - 1];
        }
    }

    int total_particles = 0;
    if (rank == 0) {
        for (int r = 0; r < nprocs; ++r) total_particles += counts[r];
    }

    std::vector<double> recv_buf;
    if (rank == 0) {
        recv_buf.resize(static_cast<size_t>(total_particles) * doubles_per);
    }

    MPI_Gatherv(send_buf.data(), local_alive * doubles_per, MPI_DOUBLE,
                recv_buf.data(), send_counts.data(), displs.data(), MPI_DOUBLE,
                0, MPI_COMM_WORLD);

    ParticleData result(rank == 0 ? static_cast<Index>(total_particles) : 0, cdim, idim);
    if (rank == 0) {
        for (int p = 0; p < total_particles; ++p) {
            checkpoint_unpack_particle(result, &recv_buf[static_cast<size_t>(p) * doubles_per],
                                       cdim, idim);
        }
    }
    return result;
#else
    // Serial: just copy alive particles
    int alive = 0;
    for (Index i = 0; i < local.count(); ++i) {
        if (local.status(i) == ParticleStatus::Alive) ++alive;
    }
    ParticleData result(static_cast<Index>(alive), cdim, idim);
    std::vector<double> buf(doubles_per);
    for (Index i = 0; i < local.count(); ++i) {
        if (local.status(i) != ParticleStatus::Alive) continue;
        checkpoint_pack_particle(local, i, buf.data(), cdim, idim);
        checkpoint_unpack_particle(result, buf.data(), cdim, idim);
    }
    return result;
#endif
}

// ─── Write checkpoint (Gather-to-Root strategy) ────────────────────────────

static void write_checkpoint_gather(const std::string& filepath,
                                    const ParticleData& particles,
                                    const CheckpointHeader& hdr,
                                    const std::string& cfg_text,
                                    int rank, int nprocs) {
    const int cdim = static_cast<int>(hdr.culture_dim);
    const int idim = static_cast<int>(hdr.immune_dim);

    ParticleData global = gather_all_particles(particles, rank, nprocs);

    if (rank == 0) {
        std::ofstream out(filepath, std::ios::binary);
        if (!out.is_open()) {
            throw std::runtime_error("Cannot open checkpoint file for writing: " + filepath);
        }

        // Write header
        CheckpointHeader whdr = hdr;
        whdr.particle_count = static_cast<uint64_t>(global.count());
        out.write(reinterpret_cast<const char*>(&whdr), sizeof(whdr));

        // Write config block
        uint64_t cfg_size = cfg_text.size();
        out.write(reinterpret_cast<const char*>(&cfg_size), sizeof(cfg_size));
        out.write(cfg_text.data(), static_cast<std::streamsize>(cfg_size));
        // Padding to 8-byte boundary
        size_t pad_bytes = align8(cfg_size) - cfg_size;
        if (pad_bytes > 0) {
            char zeros[8] = {};
            out.write(zeros, static_cast<std::streamsize>(pad_bytes));
        }

        // Write particle records
        const int doubles_per = 12 + cdim + idim;
        std::vector<double> rec(doubles_per);
        for (Index i = 0; i < global.count(); ++i) {
            checkpoint_pack_particle(global, i, rec.data(), cdim, idim);
            out.write(reinterpret_cast<const char*>(rec.data()),
                      static_cast<std::streamsize>(doubles_per * sizeof(double)));
        }

        out.close();
        std::cout << "[Checkpoint] Wrote " << global.count()
                  << " particles to " << filepath
                  << " (" << (sizeof(whdr) + 8 + align8(cfg_size) +
                              static_cast<size_t>(global.count()) * doubles_per * sizeof(double))
                  << " bytes)\n";
    }
}

// ─── Write checkpoint (MPI-IO strategy) ────────────────────────────────────

static void write_checkpoint_mpiio(const std::string& filepath,
                                   const ParticleData& particles,
                                   const CheckpointHeader& hdr,
                                   const std::string& cfg_text,
                                   int rank, int nprocs) {
#ifdef POLITEIA_USE_MPI
    const int cdim = static_cast<int>(hdr.culture_dim);
    const int idim = static_cast<int>(hdr.immune_dim);
    const int doubles_per = 12 + cdim + idim;

    // Count alive particles per rank
    int local_alive = 0;
    for (Index i = 0; i < particles.count(); ++i) {
        if (particles.status(i) == ParticleStatus::Alive) ++local_alive;
    }

    // Compute global total and prefix sum for file offsets
    long long ll_local = local_alive;
    long long ll_total = 0;
    long long ll_prefix = 0;
    MPI_Allreduce(&ll_local, &ll_total, 1, MPI_LONG_LONG, MPI_SUM, MPI_COMM_WORLD);
    MPI_Exscan(&ll_local, &ll_prefix, 1, MPI_LONG_LONG, MPI_SUM, MPI_COMM_WORLD);
    if (rank == 0) ll_prefix = 0;

    // Rank 0 writes header + config using POSIX first
    size_t data_offset = 0;
    if (rank == 0) {
        std::ofstream out(filepath, std::ios::binary);
        if (!out.is_open()) {
            throw std::runtime_error("Cannot open checkpoint for writing: " + filepath);
        }
        CheckpointHeader whdr = hdr;
        whdr.particle_count = static_cast<uint64_t>(ll_total);
        out.write(reinterpret_cast<const char*>(&whdr), sizeof(whdr));

        uint64_t cfg_size = cfg_text.size();
        out.write(reinterpret_cast<const char*>(&cfg_size), sizeof(cfg_size));
        out.write(cfg_text.data(), static_cast<std::streamsize>(cfg_size));
        size_t pad_bytes = align8(cfg_size) - cfg_size;
        if (pad_bytes > 0) {
            char zeros[8] = {};
            out.write(zeros, static_cast<std::streamsize>(pad_bytes));
        }
        data_offset = CHECKPOINT_HEADER_BYTES + 8 + align8(cfg_size);
        out.close();
    }

    // Broadcast data_offset to all ranks
    MPI_Bcast(&data_offset, sizeof(data_offset), MPI_BYTE, 0, MPI_COMM_WORLD);

    MPI_Barrier(MPI_COMM_WORLD);

    // Each rank writes its particles via MPI-IO
    MPI_File fh;
    int rc = MPI_File_open(MPI_COMM_WORLD, filepath.c_str(),
                           MPI_MODE_WRONLY, MPI_INFO_NULL, &fh);
    if (rc != MPI_SUCCESS) {
        throw std::runtime_error("MPI_File_open failed for: " + filepath);
    }

    // Pack local particles
    std::vector<double> buf(static_cast<size_t>(local_alive) * doubles_per);
    int pos = 0;
    for (Index i = 0; i < particles.count(); ++i) {
        if (particles.status(i) != ParticleStatus::Alive) continue;
        checkpoint_pack_particle(particles, i, &buf[pos], cdim, idim);
        pos += doubles_per;
    }

    MPI_Offset offset = static_cast<MPI_Offset>(data_offset)
                      + static_cast<MPI_Offset>(ll_prefix) * doubles_per * sizeof(double);
    MPI_Status status;
    MPI_File_write_at_all(fh, offset, buf.data(),
                          local_alive * doubles_per, MPI_DOUBLE, &status);
    MPI_File_close(&fh);

    if (rank == 0) {
        std::cout << "[Checkpoint] MPI-IO wrote " << ll_total
                  << " particles to " << filepath << "\n";
    }
#else
    write_checkpoint_gather(filepath, particles, hdr, cfg_text, rank, nprocs);
#endif
}

// ─── Public write_checkpoint ───────────────────────────────────────────────

void write_checkpoint(const std::string& filepath,
                      const ParticleData& particles,
                      const SimConfig& cfg,
                      const std::string& cfg_path,
                      uint64_t step,
                      int rank, int nprocs) {
    const int cdim = particles.culture_dim();
    const int idim = particles.immune_dim();

    CheckpointHeader hdr;
    hdr.step        = step;
    hdr.time        = static_cast<double>(step) * cfg.dt;
    hdr.culture_dim = static_cast<uint32_t>(cdim);
    hdr.immune_dim  = static_cast<uint32_t>(idim);
    hdr.record_size = checkpoint_record_size(cdim, idim);

    std::string cfg_text = read_file_text(cfg_path);

    // Determine global particle count for strategy selection
    uint64_t local_alive = 0;
    for (Index i = 0; i < particles.count(); ++i) {
        if (particles.status(i) == ParticleStatus::Alive) ++local_alive;
    }
    uint64_t global_count = local_alive;

#ifdef POLITEIA_USE_MPI
    MPI_Allreduce(&local_alive, &global_count, 1, MPI_UNSIGNED_LONG_LONG,
                  MPI_SUM, MPI_COMM_WORLD);
#endif

    constexpr uint64_t GATHER_THRESHOLD = 10'000'000ULL;

    if (global_count <= GATHER_THRESHOLD) {
        write_checkpoint_gather(filepath, particles, hdr, cfg_text, rank, nprocs);
    } else {
        write_checkpoint_mpiio(filepath, particles, hdr, cfg_text, rank, nprocs);
    }
}

// ─── Read checkpoint header ────────────────────────────────────────────────

CheckpointHeader read_checkpoint_header(const std::string& filepath) {
    std::ifstream in(filepath, std::ios::binary);
    if (!in.is_open()) {
        throw std::runtime_error("Cannot open checkpoint: " + filepath);
    }
    CheckpointHeader hdr;
    in.read(reinterpret_cast<char*>(&hdr), sizeof(hdr));
    if (hdr.magic != CHECKPOINT_MAGIC) {
        throw std::runtime_error("Invalid checkpoint magic in: " + filepath);
    }
    if (hdr.version != CHECKPOINT_VERSION) {
        throw std::runtime_error("Unsupported checkpoint version in: " + filepath);
    }
    return hdr;
}

// ─── Read checkpoint ───────────────────────────────────────────────────────

void read_checkpoint(const std::string& filepath,
                     ParticleData& particles,
                     uint64_t& step_out,
                     double& time_out,
                     int rank, int nprocs) {
    // Every rank reads the header independently
    std::ifstream in(filepath, std::ios::binary);
    if (!in.is_open()) {
        throw std::runtime_error("Cannot open checkpoint: " + filepath);
    }

    CheckpointHeader hdr;
    in.read(reinterpret_cast<char*>(&hdr), sizeof(hdr));
    if (hdr.magic != CHECKPOINT_MAGIC) {
        throw std::runtime_error("Invalid checkpoint magic");
    }

    step_out = hdr.step;
    time_out = hdr.time;

    const int cdim = static_cast<int>(hdr.culture_dim);
    const int idim = static_cast<int>(hdr.immune_dim);
    const int doubles_per = 12 + cdim + idim;
    const uint64_t N = hdr.particle_count;

    // Skip config block
    uint64_t cfg_size = 0;
    in.read(reinterpret_cast<char*>(&cfg_size), sizeof(cfg_size));
    size_t skip = align8(cfg_size);
    in.seekg(static_cast<std::streamoff>(skip), std::ios::cur);

    // Compute this rank's share: [begin, end)
    uint64_t begin = N * static_cast<uint64_t>(rank) / static_cast<uint64_t>(nprocs);
    uint64_t end   = N * static_cast<uint64_t>(rank + 1) / static_cast<uint64_t>(nprocs);
    uint64_t my_count = end - begin;

    // Seek to begin particle
    auto data_start = in.tellg();
    in.seekg(data_start + static_cast<std::streamoff>(begin * doubles_per * sizeof(double)));

    // Read and unpack
    particles.reserve(static_cast<Index>(my_count * 2));
    std::vector<double> rec(doubles_per);
    for (uint64_t p = 0; p < my_count; ++p) {
        in.read(reinterpret_cast<char*>(rec.data()),
                static_cast<std::streamsize>(doubles_per * sizeof(double)));
        checkpoint_unpack_particle(particles, rec.data(), cdim, idim);
    }

    if (rank == 0) {
        std::cout << "[Checkpoint] Read " << N << " total particles from " << filepath
                  << " (step=" << step_out << " time=" << time_out << ")\n"
                  << "  This rank loaded " << my_count << "/" << N << " particles\n";
    }
}

} // namespace politeia
