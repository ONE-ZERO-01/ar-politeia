#pragma once

#include "core/types.hpp"

#include <deque>
#include <string>
#include <vector>

namespace politeia {

/// Detects phase transitions by monitoring order parameter time series.
/// Uses a sliding window to compute rate of change and variance;
/// when either exceeds a threshold, flags a "transition event".
struct TransitionEvent {
    Real time;
    std::string param_name;    // which order parameter triggered
    Real rate;                 // |dX/dt| at trigger
    Real variance;             // Var(X) at trigger
    Real value_before;         // mean X in the first half of window
    Real value_after;          // mean X in the second half
};

/// Per-parameter sliding window tracker.
class OrderParamTracker {
public:
    OrderParamTracker(std::string name, Index window_size,
                      Real rate_threshold, Real variance_threshold);

    /// Push a new (time, value) sample. Returns true if a transition
    /// is detected at this step.
    bool push(Real time, Real value);

    /// Get the last detected event (valid only if push() returned true).
    [[nodiscard]] const TransitionEvent& last_event() const { return last_event_; }

    [[nodiscard]] const std::string& name() const { return name_; }

private:
    std::string name_;
    Index window_size_;
    Real rate_threshold_;
    Real variance_threshold_;

    struct Sample { Real time; Real value; };
    std::deque<Sample> buffer_;

    TransitionEvent last_event_{};
    Real prev_mean_ = 0.0;
    bool primed_ = false;  // true once buffer is full
};

/// Aggregate tracker for multiple order parameters.
class PhaseTransitionDetector {
public:
    /// Initialize with default trackers for standard order parameters.
    /// window_size: number of samples in the sliding window.
    explicit PhaseTransitionDetector(Index window_size = 20);

    /// Push a full set of order parameters at one time step.
    /// Returns detected transition events (may be empty).
    struct Snapshot {
        Real time;
        Real gini;
        Real Q;
        Real H;
        Real F;
        Real psi;
        Real hhi;
        Real mean_loyalty;
    };

    [[nodiscard]] std::vector<TransitionEvent> push(const Snapshot& snap);

private:
    std::vector<OrderParamTracker> trackers_;
};

} // namespace politeia
