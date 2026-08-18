#pragma once

#include "core/types.hpp"
#include "core/particle_data.hpp"

#include <vector>
#include <string>
#include <unordered_map>

namespace politeia {

/// Classification of polity type based on population and hierarchy depth.
enum class PolityType : int {
    Band       = 0,  // N < 50,  H ≤ 1
    Tribe      = 1,  // N < 300, H ≤ 2
    Chiefdom   = 2,  // N < 1000, H ≤ 4
    State      = 3,  // N < 5000
    Empire     = 4   // N ≥ 5000
};

const char* polity_type_name(PolityType t) noexcept;

/// Aggregate statistics for a single detected polity.
struct PolityInfo {
    Index root_local;       // local index of the root particle
    Id    root_gid;         // global ID of the root
    Index population;       // number of particles in this polity
    Index depth;            // max hierarchy depth
    Real  total_wealth;     // sum of member wealth
    Real  total_power;      // effective power of the root
    Real  mean_loyalty;     // average loyalty of subordinates
    Real  territory_area;   // convex hull area approximation (bounding box)
    Vec2  centroid;         // population-weighted center of mass
    PolityType type;        // classification
};

/// Event types for polity lifecycle tracking.
enum class PolityEventType : int {
    Formation = 0,  // new polity appears (was isolated individuals)
    Merger    = 1,  // two polities merge into one
    Split     = 2,  // one polity splits into multiple
    Collapse  = 3   // polity dissolves (leader dies, all subordinates rebel)
};

struct PolityEvent {
    Real time;
    PolityEventType type;
    Id   polity_gid;        // root gid of the polity involved
    Id   other_gid;         // for merger: the absorbed polity's old root gid
    Index pop_before;
    Index pop_after;
};

/// Detect polities from the hierarchy tree.
/// A polity = a connected component in the superior tree (all particles
/// reachable from a common root). Isolated individuals (no superior,
/// no subordinates) are classified as Band (size=1).
///
/// Returns a vector of PolityInfo sorted by population (descending).
[[nodiscard]] std::vector<PolityInfo> detect_polities(
    const ParticleData& particles
);

/// Classify a polity based on population and hierarchy depth.
[[nodiscard]] PolityType classify_polity(Index population, Index depth);

/// Compare current polities with previous step to detect events.
/// Uses root gid as polity identity. Detects formation, merger,
/// split, and collapse by tracking which root gids persist, appear,
/// or disappear between steps.
[[nodiscard]] std::vector<PolityEvent> detect_polity_events(
    const std::vector<PolityInfo>& prev_polities,
    const std::vector<PolityInfo>& curr_polities,
    Real time
);

/// Summary statistics across all polities at one time step.
struct PolitySummary {
    Real time;
    Index n_polities;       // number of polities (including singletons)
    Index n_multi;          // polities with pop > 1
    Index largest_pop;      // population of the largest polity
    Real  hhi;              // Herfindahl-Hirschman Index (concentration)
    Real  mean_pop;         // mean polity population
    Index n_bands;
    Index n_tribes;
    Index n_chiefdoms;
    Index n_states;
    Index n_empires;
};

/// Compute summary statistics from detected polities.
[[nodiscard]] PolitySummary summarize_polities(
    const std::vector<PolityInfo>& polities,
    Real time
);

} // namespace politeia
