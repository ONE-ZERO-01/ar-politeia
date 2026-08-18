#pragma once

#include "core/types.hpp"
#include "core/particle_data.hpp"
#include "analysis/polity.hpp"
#include "analysis/phase_transition.hpp"

#include <string>
#include <fstream>
#include <vector>

namespace politeia {

/// CSV output for simulation data.
/// Writes five types of files:
///   1. Particle snapshots (full state per particle per output step)
///   2. Energy time series
///   3. Order parameter time series (Gini, Q, H, C, F, Ψ, ⟨L⟩, etc.)
///   4. Polity summary time series (counts by type, HHI, largest)
///   5. Polity events log (formation, merger, split, collapse)
class CSVWriter {
public:
    explicit CSVWriter(const std::string& output_dir);

    void write_snapshot(const ParticleData& particles, Index step,
                        const std::vector<Real>* power = nullptr);

    void write_snapshot_binary(const ParticleData& particles, Index step,
                               const std::vector<Real>* power = nullptr);

    void write_energy(Index step, Real time, Real ke, Real pe_social,
                      Real pe_terrain, Real total);

    struct OrderParams {
        Index step = 0;
        Real time = 0;
        Index N = 0;
        Real gini = 0;
        Real Q = 0;
        Real mean_eps = 0;
        Index H = 0;
        Index C = 0;
        Real F = 0;
        Real psi = 0;
        Real mean_loyalty = 0;
        Index n_attached = 0;
        Real gini_power = 0;
    };

    void write_order_params(const OrderParams& op);

    struct DemographicRecord {
        Index step = 0;
        Real time = 0;
        Index N = 0;
        Index births = 0;
        Index deaths = 0;
        Real mean_age = 0;
        Real median_age = 0;
        Real frac_fertile = 0;   // fraction of population in fertile age range
        Real frac_children = 0;  // fraction < 15
        Real frac_elderly = 0;   // fraction > 60
        Real growth_rate = 0;    // (births - deaths) / N
    };

    void write_demographics(const DemographicRecord& dr);

    /// Write polity summary row (one per analysis window).
    void write_polity_summary(const PolitySummary& ps);

    /// Write a polity lifecycle event.
    void write_polity_event(const PolityEvent& ev);

    /// Write per-polity snapshot (top polities at this step).
    void write_polity_snapshot(const std::vector<PolityInfo>& polities,
                               Index step);

    /// Write a phase transition event.
    void write_transition_event(const TransitionEvent& ev);

    void close();

    void write_positions(const ParticleData& particles, Index step) {
        write_snapshot(particles, step);
    }

private:
    std::string output_dir_;
    std::ofstream energy_file_;
    std::ofstream order_file_;
    std::ofstream demographics_file_;
    std::ofstream polity_file_;
    std::ofstream polity_event_file_;
    std::ofstream transition_file_;
};

} // namespace politeia
