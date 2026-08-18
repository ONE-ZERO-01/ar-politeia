#pragma once

/// @file perf_monitor.hpp
/// @brief 性能监控：分段计时 + MPI 负载均衡分析
///
/// 将每个时间步的计算分解为多个阶段（力计算、交互、通信等），
/// 统计每个阶段的耗时，通过 MPI 全局汇总得到 max/min/avg，
/// 计算并行效率 efficiency = avg/max（理想值 100%）。
///
/// 当 efficiency 低于阈值时自动触发 SFC 重平衡。

#include "core/types.hpp"

#include <chrono>
#include <string>
#include <vector>
#include <array>

#ifdef POLITEIA_USE_MPI
#include <mpi.h>
#endif

namespace politeia {

class PerfMonitor {
public:
    /// 计时阶段定义
    enum Phase : int {
        Dynamics = 0,    // Langevin 积分
        Exchange,        // 资源交换
        Culture,         // 文化演化
        Technology,      // 技术演化
        Resources,       // 资源产出/消耗
        Population,      // 年龄/死亡/繁殖
        Migration,       // MPI 粒子迁移
        Analysis,        // 序参量计算
        IO,              // 输出
        NUM_PHASES
    };

    static constexpr const char* phase_names[] = {
        "dynamics", "exchange", "culture", "technology",
        "resources", "population", "migration", "analysis", "io"
    };

    /// 开始计时一个阶段
    void start(Phase p) {
        starts_[p] = clock::now();
    }

    /// 结束计时一个阶段，累加到该阶段的总时间
    void stop(Phase p) {
        auto elapsed = std::chrono::duration<double>(clock::now() - starts_[p]).count();
        accum_[p] += elapsed;
        step_time_[p] = elapsed;
    }

    /// 重置所有累加器
    void reset() {
        accum_.fill(0.0);
        step_time_.fill(0.0);
        total_steps_ = 0;
    }

    /// 记录一步完成
    void step_done() { total_steps_++; }

    /// 本步各阶段耗时
    [[nodiscard]] double step_time(Phase p) const { return step_time_[p]; }

    /// 本步总耗时
    [[nodiscard]] double step_total() const {
        double t = 0;
        for (int i = 0; i < NUM_PHASES; ++i) t += step_time_[i];
        return t;
    }

    /// 本步计算耗时（排除 IO，IO 仅在 rank 0 执行，不参与负载均衡评估）
    [[nodiscard]] double step_compute() const {
        double t = 0;
        for (int i = 0; i < NUM_PHASES; ++i) {
            if (i != IO) t += step_time_[i];
        }
        return t;
    }

    /// 累计各阶段耗时
    [[nodiscard]] double accumulated(Phase p) const { return accum_[p]; }

    /// 累计总耗时
    [[nodiscard]] double accumulated_total() const {
        double t = 0;
        for (int i = 0; i < NUM_PHASES; ++i) t += accum_[i];
        return t;
    }

    /// MPI 负载均衡报告
    struct LoadReport {
        double local_total = 0;
        double global_max = 0;
        double global_min = 0;
        double global_avg = 0;
        double efficiency = 1.0;          // avg/max
        Index local_particles = 0;
        Index global_max_particles = 0;
        Index global_min_particles = 0;
        bool needs_rebalance = false;     // efficiency < threshold
    };

    /// 计算当前步的负载报告（MPI 集合操作，所有 rank 必须调用）
    [[nodiscard]] LoadReport compute_load_report(
        Index local_particle_count,
        double rebalance_threshold = 0.5   // efficiency < 50% 触发重平衡
    ) const;

    /// 格式化报告为字符串（仅 rank 0 使用）
    [[nodiscard]] std::string format_report(const LoadReport& report) const;

    /// 格式化各阶段耗时分解（仅 rank 0 使用）
    [[nodiscard]] std::string format_breakdown() const;

private:
    using clock = std::chrono::steady_clock;
    using time_point = clock::time_point;

    std::array<time_point, NUM_PHASES> starts_;
    std::array<double, NUM_PHASES> accum_ = {};
    std::array<double, NUM_PHASES> step_time_ = {};
    Index total_steps_ = 0;
};

} // namespace politeia
