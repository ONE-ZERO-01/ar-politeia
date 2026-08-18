#include "analysis/perf_monitor.hpp"

#include <sstream>
#include <iomanip>
#include <algorithm>
#include <cmath>

namespace politeia {

PerfMonitor::LoadReport PerfMonitor::compute_load_report(
    Index local_particle_count,
    double rebalance_threshold
) const {
    LoadReport report;
    report.local_total = step_compute();
    report.local_particles = local_particle_count;

#ifdef POLITEIA_USE_MPI
    int mpi_ready = 0;
    MPI_Initialized(&mpi_ready);
    if (mpi_ready) {
        MPI_Allreduce(&report.local_total, &report.global_max, 1,
                      MPI_DOUBLE, MPI_MAX, MPI_COMM_WORLD);
        MPI_Allreduce(&report.local_total, &report.global_min, 1,
                      MPI_DOUBLE, MPI_MIN, MPI_COMM_WORLD);
        MPI_Allreduce(&report.local_total, &report.global_avg, 1,
                      MPI_DOUBLE, MPI_SUM, MPI_COMM_WORLD);

        int nprocs = 1;
        MPI_Comm_size(MPI_COMM_WORLD, &nprocs);
        report.global_avg /= nprocs;

        Index local_n = local_particle_count;
        MPI_Allreduce(&local_n, &report.global_max_particles, 1,
                      MPI_UNSIGNED_LONG_LONG, MPI_MAX, MPI_COMM_WORLD);
        MPI_Allreduce(&local_n, &report.global_min_particles, 1,
                      MPI_UNSIGNED_LONG_LONG, MPI_MIN, MPI_COMM_WORLD);
    } else {
        report.global_max = report.local_total;
        report.global_min = report.local_total;
        report.global_avg = report.local_total;
        report.global_max_particles = local_particle_count;
        report.global_min_particles = local_particle_count;
    }
#else
    report.global_max = report.local_total;
    report.global_min = report.local_total;
    report.global_avg = report.local_total;
    report.global_max_particles = local_particle_count;
    report.global_min_particles = local_particle_count;
#endif

    report.efficiency = (report.global_max > 1e-15)
                        ? report.global_avg / report.global_max
                        : 1.0;
    report.needs_rebalance = (report.efficiency < rebalance_threshold);

    return report;
}

std::string PerfMonitor::format_report(const LoadReport& report) const {
    std::ostringstream os;
    os << std::fixed << std::setprecision(3);
    os << "  Load: time(max=" << report.global_max * 1e3
       << "ms min=" << report.global_min * 1e3
       << "ms avg=" << report.global_avg * 1e3 << "ms) "
       << "eff=" << std::setprecision(1) << report.efficiency * 100 << "% "
       << "particles(max=" << report.global_max_particles
       << " min=" << report.global_min_particles << ")";
    if (report.needs_rebalance) {
        os << " [REBALANCE TRIGGERED]";
    }
    return os.str();
}

std::string PerfMonitor::format_breakdown() const {
    double total = step_total();
    if (total < 1e-15) return "";

    std::ostringstream os;
    os << std::fixed << std::setprecision(2);
    os << "  Phases: ";
    for (int i = 0; i < NUM_PHASES; ++i) {
        double pct = step_time_[i] / total * 100.0;
        if (pct >= 0.1) {
            os << phase_names[i] << "=" << pct << "% ";
        }
    }
    return os.str();
}

} // namespace politeia
