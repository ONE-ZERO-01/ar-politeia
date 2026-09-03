#include "population/reproduction.hpp"
#include "population/plague.hpp"
#include "population/carrying_capacity.hpp"
#include "interaction/loyalty.hpp"

#include <cmath>
#include <algorithm>

namespace politeia {

Real fertility(Real age, const ReproductionParams& params) {
    if (age < params.puberty_age || age > params.menopause_age) return 0.0;

    // Beta-like bell curve: peaks at peak_fertility_age
    const Real span = params.menopause_age - params.puberty_age;
    if (span <= 1e-15) return 0.0;
    const Real t = (age - params.puberty_age) / span;  // normalized to [0, 1]
    const Real peak_t = (params.peak_fertility_age - params.puberty_age) / span;
    if (peak_t <= 0.0 || peak_t >= 1.0) return 0.0;

    // Shape: t^a * (1-t)^b where peak is at a/(a+b) = peak_t
    const Real alpha = params.fertility_alpha;
    const Real beta_param = alpha * (1.0 - peak_t) / peak_t;

    Real f = std::pow(t, alpha) * std::pow(1.0 - t, beta_param);

    // Normalize so peak = max_fertility
    Real peak_val = std::pow(peak_t, alpha) * std::pow(1.0 - peak_t, beta_param);
    if (peak_val > 1e-15) {
        f = params.max_fertility * f / peak_val;
    }

    return f;
}

namespace {

struct BirthRecord {
    Vec2 pos;
    Vec2 mom;
    Real wealth;
    Real epsilon;
    Index mother;   // female parent (or parent_a when gender disabled)
    Index father;   // male parent (or parent_b when gender disabled)
};

/// Determine culture inheritance weight for the "dominant" parent.
/// In "contribution" mode: the parent with higher w×ε contribution gets
/// culture_dominant_weight of the culture vector.
Real dominant_weight(const ParticleData& particles, Index mother, Index father,
                     const ReproductionParams& params) {
    if (params.inheritance_model == "matrilineal") return params.culture_dominant_weight;
    if (params.inheritance_model == "patrilineal") return 1.0 - params.culture_dominant_weight;
    if (params.inheritance_model == "equal") return 0.5;

    if (params.inheritance_model == "epsilon_switch") {
        Real mean_eps = 0.5 * (particles.epsilon(mother) + particles.epsilon(father));
        return (mean_eps > params.epsilon_patrilineal_threshold)
            ? (1.0 - params.culture_dominant_weight) : params.culture_dominant_weight;
    }

    // "contribution" mode (default): weight by w×ε contribution ratio
    Real contrib_m = std::max(1e-10, particles.wealth(mother) * particles.epsilon(mother));
    Real contrib_f = std::max(1e-10, particles.wealth(father) * particles.epsilon(father));
    return contrib_m / (contrib_m + contrib_f);
}

} // namespace

Index attempt_reproduction(
    ParticleData& particles,
    const CellList& cells,
    const ReproductionParams& params,
    Real current_time,
    std::mt19937_64& rng,
    const Real* local_density,
    const Real* local_K,
    const LoyaltyParams* loyalty_params
) {
    const Real cutoff_sq = params.mate_range * params.mate_range;
    const Real* __restrict__ x = particles.x_data();
    const Index n = particles.count();

    std::uniform_real_distribution<Real> uniform(0.0, 1.0);
    std::normal_distribution<Real> mutation(0.0, params.mutation_strength);

    std::vector<BirthRecord> births;
    Index born = 0;

    cells.for_each_pair(x, n, cutoff_sq,
        [&](Index i, Index j, Real dx, Real dy, Real r2) {
            if (particles.status(i) != ParticleStatus::Alive) return;
            if (particles.status(j) != ParticleStatus::Alive) return;

            // Gender complementarity check
            Index mother = i, father = j;
            if (params.gender_enabled) {
                if (particles.sex(i) == particles.sex(j)) return;
                mother = (particles.sex(i) == 0) ? i : j;
                father = (particles.sex(i) == 0) ? j : i;
            }

            if (particles.wealth(i) < params.min_wealth_to_breed) return;
            if (particles.wealth(j) < params.min_wealth_to_breed) return;

            // Gender-asymmetric cooldown
            if (params.gender_enabled) {
                Real female_cooldown = params.gestation_time + params.nursing_time;
                if (current_time - particles.last_birth_time(mother) < female_cooldown) return;
                if (current_time - particles.last_birth_time(father) < params.male_cooldown) return;
            } else {
                Real cooldown = params.gestation_time + params.nursing_time;
                if (current_time - particles.last_birth_time(i) < cooldown) return;
                if (current_time - particles.last_birth_time(j) < cooldown) return;
            }

            Real cdist = culture_distance(particles, i, j);
            if (cdist > params.culture_mate_threshold) return;

            // Fertility: female fertility window [puberty, menopause]; male [puberty, ∞)
            Real fi, fj;
            if (params.gender_enabled) {
                fi = fertility(particles.age(mother), params);
                fj = (particles.age(father) >= params.puberty_age) ? params.max_fertility : 0.0;
            } else {
                fi = fertility(particles.age(i), params);
                fj = fertility(particles.age(j), params);
            }
            Real prob = std::min(fi, fj);

            if (local_density && local_K) {
                Real si = density_suppression(local_density[i], local_K[i]);
                Real sj = density_suppression(local_density[j], local_K[j]);
                prob *= std::min(si, sj);
            }

            if (prob < 1e-15) return;
            if (uniform(rng) > prob) return;

            Real child_wealth = params.wealth_birth_cost *
                                std::min(particles.wealth(i), particles.wealth(j));

            Vec2 parent_pos_i = particles.position(i);
            Vec2 parent_pos_j = particles.position(j);
            Vec2 child_pos = {
                0.5 * (parent_pos_i[0] + parent_pos_j[0]) + mutation(rng),
                0.5 * (parent_pos_i[1] + parent_pos_j[1]) + mutation(rng)
            };

            Real child_eps = std::max(particles.epsilon(i), particles.epsilon(j))
                             + std::abs(mutation(rng)) * params.epsilon_mutation_scale;

            births.push_back({
                child_pos, {0.0, 0.0}, child_wealth, child_eps, mother, father
            });
        }
    );

    for (const auto& b : births) {
        Real cost = b.wealth * 0.5;
        if (particles.wealth(b.mother) > cost && particles.wealth(b.father) > cost) {
            particles.wealth(b.mother) -= cost;
            particles.wealth(b.father) -= cost;
            particles.last_birth_time(b.mother) = current_time;
            particles.last_birth_time(b.father) = current_time;

            Index child_idx = particles.add_particle(b.pos, b.mom, b.wealth, b.epsilon, 0.0);

            // Assign child sex
            if (params.gender_enabled) {
                particles.sex(child_idx) = (uniform(rng) < params.sex_ratio) ? 1 : 0;
            }

            // Culture inheritance with configurable direction
            int cd = particles.culture_dim();
            Real wm = dominant_weight(particles, b.mother, b.father, params);
            for (int k = 0; k < cd; ++k) {
                Real cm = particles.culture(b.mother, k);
                Real cf = particles.culture(b.father, k);
                particles.culture(child_idx, k) = wm * cm + (1.0 - wm) * cf + mutation(rng) * params.culture_mutation_scale;
            }

            inherit_immunity(particles, child_idx, b.mother, b.father, 0.5);
            if (loyalty_params) {
                inherit_hierarchy(
                    particles, child_idx, b.mother, b.father, *loyalty_params);
            } else {
                inherit_hierarchy(particles, child_idx, b.mother, b.father);
            }
            ++born;
        }
    }

    return born;
}

} // namespace politeia
