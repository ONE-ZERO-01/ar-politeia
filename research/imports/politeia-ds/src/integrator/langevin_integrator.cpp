#include "integrator/langevin_integrator.hpp"

#include <cmath>
#include <cstring>
#include <vector>

#ifdef POLITEIA_USE_OPENMP
#include <omp.h>
#endif

namespace politeia {

LangevinIntegrator::LangevinIntegrator(
    Real dt, Real mass, Real friction, Real temperature,
    SocialForceParams social, TerrainParams terrain,
    Real domain_xmin, Real domain_xmax,
    Real domain_ymin, Real domain_ymax,
    std::uint64_t seed,
    const TerrainGrid* terrain_grid,
    Real terrain_scale
)
    : dt_(dt), mass_(mass), inv_mass_(1.0 / mass),
      friction_(friction), temperature_(temperature),
      social_(std::move(social)), terrain_(std::move(terrain)),
      terrain_grid_(terrain_grid), terrain_scale_(terrain_scale),
      domain_xmin_(domain_xmin), domain_xmax_(domain_xmax),
      domain_ymin_(domain_ymin), domain_ymax_(domain_ymax),
      rng_(seed)
{
    update_noise_amplitude();
}

void LangevinIntegrator::update_noise_amplitude() {
    // Langevin equation: dp = F·dt − γ·p·dt + σ·dW
    // where σ = sqrt(2·γ·m·k_B·T), k_B = 1 in our units.
    // Per half-step, noise = σ·sqrt(dt/2)·N(0,1) = sqrt(γ·m·T·dt)·N(0,1).
    if (friction_ > 0.0 && temperature_ > 0.0) {
        noise_amp_ = std::sqrt(2.0 * friction_ * mass_ * temperature_);
    } else {
        noise_amp_ = 0.0;
    }
}

std::pair<Real, Real> LangevinIntegrator::compute_forces(
    ParticleData& particles, CellList& cells
) {
    auto& f = particles.force_buffer();
    std::memset(f.data(), 0, sizeof(Real) * particles.count() * SPATIAL_DIM);

    cells.build(particles.x_data(), particles.count());

    Real social_pe = compute_social_forces(
        particles.x_data(), f.data(), particles.count(), cells, social_
    );

    Real terrain_pe = 0.0;
    if (terrain_grid_ && terrain_grid_->loaded()) {
        terrain_pe = compute_grid_terrain_forces(
            particles.x_data(), f.data(), particles.count(),
            *terrain_grid_, terrain_scale_
        );
    } else {
        terrain_pe = compute_terrain_forces(
            particles.x_data(), f.data(), particles.count(), terrain_
        );
    }

    return {social_pe, terrain_pe};
}

Real LangevinIntegrator::compute_kinetic(const ParticleData& particles) const {
    Real ke = 0.0;
    const Real* __restrict__ p = particles.p_data();
    const Index n = particles.count();
    #pragma omp parallel for schedule(static) reduction(+:ke) if(n > 256)
    for (Index i = 0; i < n; ++i) {
        ke += p[2 * i] * p[2 * i] + p[2 * i + 1] * p[2 * i + 1];
    }
    return 0.5 * inv_mass_ * ke;
}

void LangevinIntegrator::apply_boundary(ParticleData& particles) const {
    Real* __restrict__ x = particles.x_data();
    Real* __restrict__ p = particles.p_data();
    const Index n = particles.count();

    #pragma omp parallel for schedule(static) if(n > 256)
    for (Index i = 0; i < n; ++i) {
        if (x[2*i] < domain_xmin_)     { x[2*i] = 2.0*domain_xmin_ - x[2*i]; p[2*i] = -p[2*i]; }
        if (x[2*i] > domain_xmax_)     { x[2*i] = 2.0*domain_xmax_ - x[2*i]; p[2*i] = -p[2*i]; }
        if (x[2*i+1] < domain_ymin_)   { x[2*i+1] = 2.0*domain_ymin_ - x[2*i+1]; p[2*i+1] = -p[2*i+1]; }
        if (x[2*i+1] > domain_ymax_)   { x[2*i+1] = 2.0*domain_ymax_ - x[2*i+1]; p[2*i+1] = -p[2*i+1]; }
    }
}

IntegratorState LangevinIntegrator::step(ParticleData& particles, CellList& cells) {
    // BBK integrator (Brünger-Brooks-Karplus):
    //
    // p_{n+1/2} = p_n + (dt/2) * [F_n - γ*p_n/m] + (σ*sqrt(dt)/2) * R_n
    // x_{n+1}   = x_n + (dt/m) * p_{n+1/2}
    // F_{n+1}   = Force(x_{n+1})
    // p_{n+1}   = p_{n+1/2} + (dt/2) * [F_{n+1} - γ*p_{n+1/2}/m] + (σ*sqrt(dt)/2) * R_{n+1}
    //
    // When γ=0, σ=0: reduces to standard Velocity-Verlet.

    const Index n = particles.count();
    Real* __restrict__ x = particles.x_data();
    Real* __restrict__ p = particles.p_data();
    Real* __restrict__ f = particles.force_buffer().data();

    const Real half_dt = 0.5 * dt_;
    const Real half_dt_gamma = half_dt * friction_;
    const Real noise_half = noise_amp_ * std::sqrt(half_dt);

    // --- Step 1: Half-step momentum update ---
    // dp = (dt/2)*F − (dt/2)*γ*p + σ*sqrt(dt/2)*N(0,1)
#ifdef POLITEIA_USE_OPENMP
    if (noise_amp_ > 0.0) {
        const int nthreads = omp_get_max_threads();
        std::vector<std::uint64_t> seeds(nthreads);
        for (int t = 0; t < nthreads; ++t) seeds[t] = rng_();

        #pragma omp parallel
        {
            std::mt19937_64 thread_rng(seeds[omp_get_thread_num()]);
            std::normal_distribution<Real> thread_normal(0.0, 1.0);
            #pragma omp for schedule(static)
            for (Index i = 0; i < n * SPATIAL_DIM; ++i) {
                p[i] += half_dt * f[i] - half_dt_gamma * p[i]
                      + noise_half * thread_normal(thread_rng);
            }
        }
    } else {
        #pragma omp parallel for schedule(static)
        for (Index i = 0; i < n * SPATIAL_DIM; ++i) {
            p[i] += half_dt * f[i];
        }
    }
#else
    for (Index i = 0; i < n * SPATIAL_DIM; ++i) {
        Real random_kick = 0.0;
        if (noise_amp_ > 0.0) {
            random_kick = noise_half * normal_(rng_);
        }
        p[i] += half_dt * f[i] - half_dt_gamma * p[i] + random_kick;
    }
#endif

    // --- Step 2: Full-step position update ---
    #pragma omp parallel for schedule(static) if(n > 256)
    for (Index i = 0; i < n * SPATIAL_DIM; ++i) {
        x[i] += dt_ * inv_mass_ * p[i];
    }

    // --- Step 3: Boundary conditions ---
    apply_boundary(particles);

    // --- Step 4: Recompute forces at new positions ---
    auto [social_pe, terrain_pe] = compute_forces(particles, cells);

    // --- Step 5: Second half-step momentum update ---
#ifdef POLITEIA_USE_OPENMP
    if (noise_amp_ > 0.0) {
        const int nthreads = omp_get_max_threads();
        std::vector<std::uint64_t> seeds(nthreads);
        for (int t = 0; t < nthreads; ++t) seeds[t] = rng_();

        #pragma omp parallel
        {
            std::mt19937_64 thread_rng(seeds[omp_get_thread_num()]);
            std::normal_distribution<Real> thread_normal(0.0, 1.0);
            #pragma omp for schedule(static)
            for (Index i = 0; i < n * SPATIAL_DIM; ++i) {
                p[i] += half_dt * f[i] - half_dt_gamma * p[i]
                      + noise_half * thread_normal(thread_rng);
            }
        }
    } else {
        #pragma omp parallel for schedule(static)
        for (Index i = 0; i < n * SPATIAL_DIM; ++i) {
            p[i] += half_dt * f[i];
        }
    }
#else
    for (Index i = 0; i < n * SPATIAL_DIM; ++i) {
        Real random_kick = 0.0;
        if (noise_amp_ > 0.0) {
            random_kick = noise_half * normal_(rng_);
        }
        p[i] += half_dt * f[i] - half_dt_gamma * p[i] + random_kick;
    }
#endif

    // --- Step 6: Kinetic energy ---
    Real ke = compute_kinetic(particles);

    return IntegratorState{ke, social_pe, terrain_pe};
}

} // namespace politeia
