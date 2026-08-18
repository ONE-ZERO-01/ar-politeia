#include "analysis/phase_transition.hpp"

#include <cmath>
#include <numeric>

namespace politeia {

OrderParamTracker::OrderParamTracker(
    std::string name, Index window_size,
    Real rate_threshold, Real variance_threshold
) : name_(std::move(name)),
    window_size_(window_size),
    rate_threshold_(rate_threshold),
    variance_threshold_(variance_threshold)
{}

bool OrderParamTracker::push(Real time, Real value) {
    buffer_.push_back({time, value});

    if (buffer_.size() > window_size_) {
        buffer_.pop_front();
    }

    if (buffer_.size() < window_size_) {
        return false;
    }

    if (!primed_) {
        primed_ = true;
        prev_mean_ = 0.0;
        for (auto& s : buffer_) prev_mean_ += s.value;
        prev_mean_ /= static_cast<Real>(buffer_.size());
        return false;
    }

    // Compute mean and variance
    Real mean = 0.0;
    for (auto& s : buffer_) mean += s.value;
    mean /= static_cast<Real>(buffer_.size());

    Real var = 0.0;
    for (auto& s : buffer_) {
        Real d = s.value - mean;
        var += d * d;
    }
    var /= static_cast<Real>(buffer_.size());

    // Rate of change (mean in second half minus first half)
    Index half = window_size_ / 2;
    Real mean_first = 0.0, mean_second = 0.0;
    Index idx = 0;
    for (auto& s : buffer_) {
        if (idx < half) mean_first += s.value;
        else            mean_second += s.value;
        ++idx;
    }
    mean_first /= static_cast<Real>(half);
    mean_second /= static_cast<Real>(window_size_ - half);

    Real dt = buffer_.back().time - buffer_.front().time;
    Real rate = (dt > 0) ? std::abs(mean_second - mean_first) / dt : 0.0;

    bool triggered = (rate > rate_threshold_) || (var > variance_threshold_);

    if (triggered) {
        last_event_.time = time;
        last_event_.param_name = name_;
        last_event_.rate = rate;
        last_event_.variance = var;
        last_event_.value_before = mean_first;
        last_event_.value_after = mean_second;
    }

    prev_mean_ = mean;
    return triggered;
}

PhaseTransitionDetector::PhaseTransitionDetector(Index window_size) {
    // Thresholds tuned for typical Politeia order parameter ranges
    trackers_.emplace_back("Gini",   window_size, 0.05, 0.01);
    trackers_.emplace_back("Q",      window_size, 0.05, 0.01);
    trackers_.emplace_back("H",      window_size, 0.5,  0.5);
    trackers_.emplace_back("F",      window_size, 0.03, 0.005);
    trackers_.emplace_back("Psi",    window_size, 0.03, 0.005);
    trackers_.emplace_back("HHI",    window_size, 0.02, 0.003);
    trackers_.emplace_back("<L>",    window_size, 0.03, 0.005);
}

std::vector<TransitionEvent> PhaseTransitionDetector::push(const Snapshot& snap) {
    std::vector<TransitionEvent> events;

    Real values[] = {snap.gini, snap.Q, snap.H, snap.F,
                     snap.psi, snap.hhi, snap.mean_loyalty};

    for (size_t i = 0; i < trackers_.size(); ++i) {
        if (trackers_[i].push(snap.time, values[i])) {
            events.push_back(trackers_[i].last_event());
        }
    }

    return events;
}

} // namespace politeia
