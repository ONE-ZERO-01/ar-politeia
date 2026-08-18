#pragma once

/// @file plague.hpp
/// @brief 瘟疫差异化打击模型
///
/// 物理背景（研究方案 §2.3）：
///   不同群体对同一种瘟疫的免疫力不同。当两个被地形势垒长期隔离的
///   群体接触时，携带者一方的地方性病原体可能对另一方造成毁灭性打击。
///
///   历史验证：
///   - 哥伦布交换 (1492+)：天花杀死 90% 美洲原住民
///   - 黑死病 (1347-1351)：杀死 30-60% 欧洲人口 → 农奴制崩溃
///   - 安东尼瘟疫 (165-180)：加速罗马帝国衰落
///
/// 机制：
///   1. 内生触发：高密度区以 Poisson 过程随机生成新病原体
///   2. SIR 传播：S(易感)→I(感染)→R(康复)/D(死亡)
///   3. 差异化打击：死亡率 = P₀ × (1 − d^k_i)，有免疫力者存活
///   4. 免疫获取：康复者获得永久免疫 d^k_i = 1
///   5. 代际遗传：后代部分继承父母免疫力

#include "core/types.hpp"
#include "core/particle_data.hpp"
#include "domain/cell_list.hpp"

#include <random>
#include <vector>

namespace politeia {

struct PlagueParams {
    Real trigger_density = 50.0;    // 触发瘟疫所需的局部人口密度
    Real trigger_rate = 1e-5;       // 每步触发概率（在高密度区）
    Real infection_radius = 3.0;    // 感染传播半径
    Real infection_rate = 0.3;      // 感染概率/步（接触到感染者时）
    Real base_mortality = 0.5;      // 无免疫力时的死亡率
    Real recovery_time = 5.0;       // 平均恢复时间（步数）
    Real immunity_inheritance = 0.5; // 后代继承的免疫力比例
};

/// SIR 状态标记
enum class InfectionState : std::uint8_t {
    Susceptible = 0,  // 易感
    Infected = 1,     // 感染中
    Recovered = 2,    // 已康复（免疫）
};

/// 瘟疫事件管理器
class PlagueManager {
public:
    PlagueManager() = default;

    /// 初始化：为每个粒子分配 SIR 状态
    void init(Index n_particles, int n_pathogens);

    /// 每步调用：检测是否触发新瘟疫 + 传播已有瘟疫
    /// 返回本步死亡人数
    [[nodiscard]] Index update(
        ParticleData& particles,
        const CellList& cells,
        const PlagueParams& params,
        Real local_density_estimate,
        Real dt,
        std::mt19937_64& rng
    );

    /// 当前是否有活跃的瘟疫
    [[nodiscard]] bool has_active_plague() const noexcept { return active_pathogen_ >= 0; }

    /// 当前活跃瘟疫的病原体编号
    [[nodiscard]] int active_pathogen() const noexcept { return active_pathogen_; }

    /// 感染人数
    [[nodiscard]] Index infected_count() const noexcept { return infected_count_; }

    /// 调整粒子数量（compact 后调用）
    void resize(Index new_count);

private:
    std::vector<InfectionState> sir_state_;
    std::vector<Real> infection_timer_;  // 感染后经过的时间
    int active_pathogen_ = -1;           // -1 = 无活跃瘟疫
    Index infected_count_ = 0;
    int n_pathogens_ = 0;
};

/// 为新生儿设置免疫继承
void inherit_immunity(
    ParticleData& particles,
    Index child_idx,
    Index parent_a,
    Index parent_b,
    Real inheritance_factor
);

} // namespace politeia
