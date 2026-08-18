#pragma once

#include "core/types.hpp"
#include "core/particle_data.hpp"
#include "analysis/network_analysis.hpp"
#include "analysis/order_params.hpp"
#include "analysis/polity.hpp"
#include "analysis/phase_transition.hpp"
#include "interaction/culture_dynamics.hpp"
#include "interaction/tech_spread.hpp"
#include "io/csv_writer.hpp"

#include <algorithm>
#include <future>
#include <string>
#include <vector>
#include <iostream>
#include <sstream>

namespace politeia {

struct AsyncAnalysisInput {
    ParticleData snap;            // deep-copied snapshot
    Index step;
    Real time;
    Real gini;                    // pre-computed by main thread
};

class AsyncAnalyzer {
public:
    explicit AsyncAnalyzer(CSVWriter* writer, bool binary_snapshot = false)
        : writer_(writer), binary_snapshot_(binary_snapshot) {}

    ~AsyncAnalyzer() { wait(); }

    void wait() {
        if (future_.valid()) {
            future_.get();
            if (!deferred_console_.empty()) {
                std::cout << deferred_console_;
                deferred_console_.clear();
            }
        }
    }

    bool is_ready() const {
        return !future_.valid() ||
               future_.wait_for(std::chrono::seconds(0)) == std::future_status::ready;
    }

    void launch(AsyncAnalysisInput input, Index total_steps) {
        wait();

        future_ = std::async(std::launch::async,
            [this, in = std::move(input), total_steps]() {
                run_analysis(in, total_steps);
            });
    }

private:
    CSVWriter* writer_;
    bool binary_snapshot_;
    std::future<void> future_;
    std::string deferred_console_;

    std::vector<PolityInfo> prev_polities_;
    PhaseTransitionDetector phase_detector_;

    void run_analysis(const AsyncAnalysisInput& in, Index total_steps) {
        std::ostringstream console;

        Real Q = compute_culture_order_param(in.snap);
        Real mean_eps = compute_mean_epsilon(in.snap);

        auto dominator = build_dominator_from_superior(in.snap);
        auto hm = compute_hierarchy_metrics(dominator, in.snap);

        Real mean_loyalty = 0;
        Index n_attached = 0;
        for (Index i = 0; i < in.snap.count(); ++i) {
            if (in.snap.superior(i) >= 0) {
                mean_loyalty += in.snap.loyalty(i);
                ++n_attached;
            }
        }
        if (n_attached > 0) mean_loyalty /= n_attached;

        auto power = compute_effective_power(dominator, in.snap);
        Real gini_power = 0;
        {
            std::vector<Real> pw(power.begin(), power.end());
            std::sort(pw.begin(), pw.end());
            Real sum = 0, weighted = 0;
            for (size_t idx = 0; idx < pw.size(); ++idx) {
                sum += pw[idx];
                weighted += (2.0 * idx - pw.size() + 1.0) * pw[idx];
            }
            gini_power = (sum > 0) ? weighted / (sum * pw.size()) : 0;
        }

        if (binary_snapshot_) {
            writer_->write_snapshot_binary(in.snap, in.step, &power);
        } else {
            writer_->write_snapshot(in.snap, in.step, &power);
        }

        CSVWriter::OrderParams op;
        op.step = in.step;
        op.time = in.time;
        op.N = in.snap.count();
        op.gini = in.gini;
        op.Q = Q;
        op.mean_eps = mean_eps;
        op.H = hm.max_depth;
        op.C = hm.n_components;
        op.F = hm.largest_fraction;
        op.psi = hm.psi;
        op.mean_loyalty = mean_loyalty;
        op.n_attached = n_attached;
        op.gini_power = gini_power;
        writer_->write_order_params(op);

        auto polities = detect_polities(in.snap);
        auto polity_summary = summarize_polities(polities, in.time);

        auto polity_events = detect_polity_events(
            prev_polities_, polities, in.time);
        prev_polities_ = polities;

        writer_->write_polity_summary(polity_summary);
        for (auto& ev : polity_events) {
            writer_->write_polity_event(ev);
        }
        if (!polities.empty()) {
            writer_->write_polity_snapshot(polities, in.step);
        }

        PhaseTransitionDetector::Snapshot pt_snap;
        pt_snap.time = in.time;
        pt_snap.gini = in.gini;
        pt_snap.Q = Q;
        pt_snap.H = static_cast<Real>(hm.max_depth);
        pt_snap.F = hm.largest_fraction;
        pt_snap.psi = hm.psi;
        pt_snap.hhi = polity_summary.hhi;
        pt_snap.mean_loyalty = mean_loyalty;

        auto transitions = phase_detector_.push(pt_snap);
        for (auto& tr : transitions) {
            writer_->write_transition_event(tr);
        }

        Index alive_n = 0;
        for (Index i = 0; i < in.snap.count(); ++i) {
            if (in.snap.status(i) == ParticleStatus::Alive) ++alive_n;
        }

        console << "Step " << in.step << "/" << total_steps
                << "  N=" << alive_n
                << "  Gini=" << in.gini
                << "  Q=" << Q
                << "  H=" << hm.max_depth
                << "  polities=" << polity_summary.n_multi
                << "(" << polity_summary.n_bands << "b"
                << polity_summary.n_tribes << "t"
                << polity_summary.n_chiefdoms << "c"
                << polity_summary.n_states << "s"
                << polity_summary.n_empires << "e)"
                << "  largest=" << polity_summary.largest_pop
                << "  HHI=" << polity_summary.hhi
                << "\n";

        for (auto& tr : transitions) {
            console << "  *** TRANSITION: " << tr.param_name
                    << " rate=" << tr.rate
                    << " var=" << tr.variance
                    << " [" << tr.value_before
                    << " -> " << tr.value_after << "]\n";
        }

        deferred_console_ = console.str();
    }
};

} // namespace politeia
