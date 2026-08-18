/// @file mortality.cpp
/// @brief 四重死亡机制和生产力曲线
///
/// 物理背景（研究方案 §2.3）：
///   P_death = P_age + P_starve + P_accident + P_plague
///
/// 四重死亡机制：
///   1. 衰老（Gompertz 法则）：P = α·exp(β·age)·dt —— 年龄越大死亡率指数增长
///   2. 饥饿：w < threshold 时死亡概率急剧增加（sigmoid 函数）
///   3. 意外：P = λ_accident·dt —— 纯随机，与年龄和财富无关（雷击、毒蛇等）
///   4. 瘟疫：预留接口（当前未实现 SIR 传播动力学）
///
/// 生产力曲线 productivity_factor(age)：
///   钟形曲线：0岁=0，15岁开始增加，30岁峰值，之后衰退。
///   社会含义：壮年劳动力最强，儿童和老人产出低。

#include "population/mortality.hpp"

#include <cmath>
#include <cstdint>
#include <vector>

#ifdef POLITEIA_USE_OPENMP
#include <omp.h>
#endif

namespace politeia {

Real effective_max_age(Real base_max_age, Real wealth, Real epsilon,
                       const MortalityParams& params) {
    Real a_max = base_max_age;
    if (params.lifespan_wealth_enabled) {
        Real w_ratio = std::min(wealth / std::max(params.lifespan_wealth_ref, 1e-10), 1.0);
        a_max += params.lifespan_wealth_k * w_ratio;
    }
    if (params.lifespan_tech_enabled) {
        a_max += params.lifespan_tech_k * std::log(1.0 + epsilon / std::max(params.lifespan_tech_ref, 1e-10));
    }
    return a_max;
}

Real effective_gompertz_beta(Real base_beta, Real wealth, Real epsilon,
                              const MortalityParams& params) {
    Real denom = 1.0;
    if (params.lifespan_wealth_enabled) {
        denom += params.lifespan_wealth_beta_alpha * wealth / std::max(params.lifespan_wealth_ref, 1e-10);
    }
    if (params.lifespan_tech_enabled) {
        denom += params.lifespan_tech_beta_alpha * epsilon / std::max(params.lifespan_tech_ref, 1e-10);
    }
    return base_beta / denom;
}

Real productivity_factor(Real age) {
    // 高斯钟形曲线，模拟人一生的劳动能力变化：
    //   0-15岁：线性增长（儿童逐渐成长）
    //   30岁：峰值（壮年最强）
    //   50+岁：逐渐衰退（衰老）
    if (age < 0.0) return 0.0;
    constexpr Real peak = 30.0;    // 峰值年龄
    constexpr Real width = 20.0;   // 衰退宽度
    Real t = (age - peak) / width;
    Real factor = std::exp(-0.5 * t * t);  // 高斯包络
    if (age < 15.0) factor *= age / 15.0;  // 儿童线性增长
    return factor;
}

void advance_age(ParticleData& particles, Real dt) {
    const Index n = particles.count();
    #pragma omp parallel for schedule(static) if(n > 256)
    for (Index i = 0; i < n; ++i) {
        if (particles.status(i) == ParticleStatus::Alive ||
            particles.status(i) == ParticleStatus::Pregnant ||
            particles.status(i) == ParticleStatus::Nursing) {
            particles.age(i) += dt;
        }
    }
}

Index apply_mortality(
    ParticleData& particles,
    const MortalityParams& params,
    Real dt,
    std::mt19937_64& rng
) {
    const Index n = particles.count();
    Index deaths = 0;

#ifdef POLITEIA_USE_OPENMP
    {
        const int nthreads = omp_get_max_threads();
        std::vector<std::uint64_t> seeds(nthreads);
        for (int t = 0; t < nthreads; ++t) seeds[t] = rng();

    #pragma omp parallel reduction(+:deaths)
    {
        std::mt19937_64 thread_rng(seeds[omp_get_thread_num()]);
        std::uniform_real_distribution<Real> uniform(0.0, 1.0);

        #pragma omp for schedule(static)
        for (Index i = 0; i < n; ++i) {
            if (particles.status(i) == ParticleStatus::Dead) continue;

            bool dies = false;
            const Real age = particles.age(i);
            const Real wealth = particles.wealth(i);
            const Real eps = particles.epsilon(i);

            Real eff_max = effective_max_age(params.max_age, wealth, eps, params);
            if (age > eff_max) {
                dies = true;
            }
            if (!dies) {
                Real eff_beta = effective_gompertz_beta(params.gompertz_beta, wealth, eps, params);
                Real p_age = params.gompertz_alpha * std::exp(eff_beta * age) * dt;
                if (uniform(thread_rng) < p_age) dies = true;
            }
            if (!dies && wealth < params.survival_threshold) {
                Real p_starve = 1.0 / (1.0 + std::exp(params.starvation_sigmoid_k * (wealth - params.survival_threshold * 0.5)));
                if (uniform(thread_rng) < p_starve * dt) dies = true;
            }
            if (!dies) {
                if (uniform(thread_rng) < params.accident_rate * dt) dies = true;
            }

            if (dies) {
                particles.mark_dead(i);
                ++deaths;
            }
        }
    }
    }
#else
    std::uniform_real_distribution<Real> uniform(0.0, 1.0);

    for (Index i = 0; i < n; ++i) {
        if (particles.status(i) == ParticleStatus::Dead) continue;

        bool dies = false;
        const Real age = particles.age(i);
        const Real wealth = particles.wealth(i);
        const Real eps = particles.epsilon(i);

        Real eff_max = effective_max_age(params.max_age, wealth, eps, params);
        if (age > eff_max) {
            dies = true;
        }
        if (!dies) {
            Real eff_beta = effective_gompertz_beta(params.gompertz_beta, wealth, eps, params);
            Real p_age = params.gompertz_alpha * std::exp(eff_beta * age) * dt;
            if (uniform(rng) < p_age) dies = true;
        }
        if (!dies && wealth < params.survival_threshold) {
            Real p_starve = 1.0 / (1.0 + std::exp(params.starvation_sigmoid_k * (wealth - params.survival_threshold * 0.5)));
            if (uniform(rng) < p_starve * dt) dies = true;
        }
        if (!dies) {
            if (uniform(rng) < params.accident_rate * dt) dies = true;
        }

        if (dies) {
            particles.mark_dead(i);
            ++deaths;
        }
    }
#endif

    return deaths;
}

} // namespace politeia
