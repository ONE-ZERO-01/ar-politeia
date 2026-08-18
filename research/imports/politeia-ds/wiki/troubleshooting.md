# Politeia 问题排查与解决方案总结

> 按严重等级和模块分类，记录项目开发过程中遇到的所有重要问题、根因分析和解决方案。
> 每个条目包含：**现象 → 根因 → 修复 → 验证 → 教训**。
> 另见 `wiki/log.md` 中的按时间线详细记录。

---

## 一、物理模型层（严重级别：Critical）

### 1.1 人口爆炸 — Carrying Capacity 地形势能未归一化

| 项目 | 内容 |
|------|------|
| **发现日期** | 2026-05-10 |
| **严重级别** | Critical |
| **现象** | 100K 粒子 × 3000 步后人口爆炸至 454K（4.5 倍），完全脱离物理预期 |

**根因链**：

```
terrain_potential V = -scale × (h_max - h)
  → V ∈ [-138, 0] (海平面最肥沃)
  → K = carrying_capacity_base × max(0, -V)
  → K = 50 × 138 = 6923 (应该是 50!)
  → density_suppression = max(0, 1 - 1.65/6923) = 0.9998
  → 密度抑制完全失效
  → 每步 ~11,550 次出生 vs ~1 次死亡
  → 指数爆炸
```

**修复**：`src/population/carrying_capacity.cpp`

```cpp
// 归一化：先找 max(-V)，然后 quality = -V[i] / max_neg_V ∈ [0,1]
Real max_neg_V = 0.0;
for (Index i = 0; i < n; ++i) {
    if (terrain_potential[i] < 0)
        max_neg_V = std::max(max_neg_V, -terrain_potential[i]);
}
if (max_neg_V < 1e-15) max_neg_V = 1.0;
K[i] = base * std::max(0.0, -V[i]) / max_neg_V;
```

**验证**：校准测试 10K 粒子 500 步后人口仅增长 +23（0.23%），符合前工业社会增长率。

**教训**：任何将物理量（势能、高度等）用作比例因子时，必须先归一化到 [0,1]。否则物理单位的量纲会破坏上层逻辑。

---

### 1.2 社会势能数值爆炸 (1e30 ~ 1e36)

| 项目 | 内容 |
|------|------|
| **发现日期** | 2026-05-09 |
| **严重级别** | Critical |
| **现象** | `energy.csv` 中 `potential_social` 高达 1e30-1e36 |

**根因**：Lennard-Jones 势 V(r) ∝ (σ/r)¹² 在 r→0 时发散。虽然力已有 F_MAX 封顶，但势能计算未做对应保护。初始化时粒子位置可能非常接近，导致 sr12 → ∞。

**修复**：`src/force/social_force.cpp` 引入 soft-core 最小距离

```cpp
const Real r_min_sq = 0.25 * sigma2;  // r_min = 0.5σ
const Real r2_eff = std::max(r2, r_min_sq);
// 后续所有 sr2, sr6, sr12 均基于 r2_eff 计算
```

**迭代**：第一版 r_min = 0.1σ → 能量仍达 1e17；调至 0.5σ → 每对势能上界 ~48ε。

**验证**：新增 `OverlappingParticlesFiniteEnergy` + `ExactOverlapSkipped` 两个单元测试，6/6 通过。

**教训**：势能和力必须共享同一个正则化方案。只封顶力而不保护势能会导致能量诊断失去意义。

---

### 1.3 生育率参数标定 — pair-wise 模型的隐性放大

| 项目 | 内容 |
|------|------|
| **发现日期** | 2026-05-10 |
| **严重级别** | High |
| **现象** | 即使 carrying capacity 归一化修复后，使用默认 `max_fertility=0.005` 人口仍快速增长 |

**根因**：生育概率 `max_fertility` 是 **per-pair-per-step** 的。每个粒子有 ~46 个邻居，有效 per-individual 生育率 ≈ 1-(1-0.005)^46 ≈ 20% per step。100 步/时间单位 → 年生育率 >> 100%。

**参数标定**：

| 参数 | 旧值 | 新值 | 依据 |
|------|------|------|------|
| `max_fertility` | 0.005 | **5e-5** | per-individual 年生育率 ≈ 0.23% |
| `carrying_capacity_base` | 50.0 | **5.0** | 平衡密度 ≈ 5 人/单位面积 |

**验证**：10K 粒子 500 步 → 人口仅增 +23（0.23% 总增长），动态平衡。

**教训**：pair-wise 交互模型的参数不能直接映射为 per-individual 速率。需要考虑邻居数 N 的放大效应：`p_individual ≈ N × p_pair`。

---

### 1.4 carrying_capacity_base 密度缩放不匹配

| 项目 | 内容 |
|------|------|
| **发现日期** | 2026-05-10 |
| **严重级别** | Critical |
| **现象** | v8 模拟 100K 粒子在 200 步内从 100K 暴跌到 85.9K (-14%)，v7 校准的 10K 粒子测试正常 |

**根因链**：

```
100K particles in 100×100 domain
  → avg density = 100,000 / 10,000 = 10 particles/unit²
  → local density (r=5) = count/area ≈ 10 particles/unit²
  → K = carrying_capacity_base × quality = 5.0 × quality ≤ 5.0
  → density_suppression = max(0, 1 - 10/5.0) = 0
  → 生育完全被抑制
  → 加上 wealth_decay_rate=0.1：无生产 + 持续消耗/折旧
  → 快速财富流失 → 饥饿死亡螺旋
```

**核心教训**：`carrying_capacity_base` 不是绝对值，它需要根据**初始粒子数/域面积**进行缩放。用 10K 粒子校准的参数不能直接用于 100K。

**修复**：

| 参数 | 旧值 | 新值 | 依据 |
|------|------|------|------|
| `carrying_capacity_base` | 5.0 | **50.0** | avg_density=10, 留 5x 增长空间 |
| `wealth_decay_rate` | 0.1 | **0.02** | 降低财富折旧速率，配合高密度 |

**验证**：待 v8b 模拟完成后确认。

**教训**：参数标定必须在**目标规模**上进行。小规模测试校准的参数往往隐含了错误的密度假设。应引入无量纲密度比 ρ/K 作为核心监控指标。

---

### 1.5 高密度 KE 爆炸 — 累积力失控

| 项目 | 内容 |
|------|------|
| **发现日期** | 2026-05-10 |
| **严重级别** | Critical |
| **现象** | v8b 模拟 (K=50) 人口增长到 135K 后 KE/NkT=145，动能超标 290 倍 |

**根因链**：

```
density ≈ 13.5/unit² → ~42 neighbors within σ=1
  → each pair force ≤ F_MAX=100
  → cumulative force per particle ≈ 42 × 100 = 4,200
  → terminal velocity v = F/γ = 4,200/1.0 = 4,200
  → KE per crowded particle = 0.5 × 4200² = 8.8M
  → vs thermal KE = 0.15 per particle
  → Langevin thermostat CAN'T correct this (friction balances force at v_terminal)
```

**修复方案**（双管齐下）：

1. **粒子总力封顶** (`social_force.cpp`):
   - 在计算所有邻居力后，如果 `|F_total| > F_TOTAL_MAX=200`，等比例缩放
   - 效果：限制单粒子最大加速度，无论邻居数量
2. **Berendsen 速度重标** (`main.cpp`):
   - 每 10 步检查 KE/NkT，若 > 2.0 则重标速度 `p *= √(NkT/2KE)`
   - 安全阀：即使力封顶不够，也能控制温度

**参数调整**：`carrying_capacity_base` 50 → 20，限制平衡密度在 ~10/unit² 以内。

**教训**：ABM 模型中 F_MAX 仅限制**单对力**。当密度高时，累积力可远超 F_MAX。必须同时限制粒子总力。Langevin 恒温器（γ-σ 平衡）在力-摩擦平衡态下无法修正温度——需要 Berendsen/Nosé-Hoover 等显式温控。

---

### 1.6 串行邻居搜索瓶颈 — for_each_pair vs for_neighbors_of

| 项目 | 内容 |
|------|------|
| **发现日期** | 2026-05-10 |
| **严重级别** | Medium |
| **现象** | 100K 粒子模拟速率仅 0.1 step/s，ETA 20+ 小时，CPU 利用率仅 134%（48 核机器） |

**根因**：`exchange_resources`、`evolve_culture`、`evolve_technology` 三个热循环使用串行 `CellList::for_each_pair`，导致 OpenMP 并行化只能作用于 `social_force` 和 `langevin_integrator`。

**修复**：将三个模块改为 OpenMP `#pragma omp parallel for` + `for_neighbors_of`（per-particle 循环），消除写竞争条件，使用中间缓冲区收集变化量后统一 apply。

**效果**：
- CPU 利用率: 134% → 249%（+85%）
- Step 100 时间: 1500s → 1029s（-31%）
- 全部 159 个单元测试通过，无回归

**教训**：OpenMP 并行化的串行部分（Amdahl 定律）会成为瓶颈。Cell List 的 `for_each_pair`（Newton 第三定律优化）虽然减少计算量，但无法并行化。对于 HPC 场景，应优先使用 `for_neighbors_of`（每粒子独立邻居搜索）以实现并行。

---

## 二、并行计算层（严重级别：High）

### 2.1 OpenMP RNG 数据竞争（integrator + mortality 共 2 处）

| 项目 | 内容 |
|------|------|
| **发现日期** | 2026-05-09 / 2026-05-10 |
| **严重级别** | High (UB) |
| **现象** | 多线程 OpenMP 下模拟结果不可复现 |

**根因**：`#pragma omp parallel` 区域内，多线程并发调用共享的 `rng_()` (std::mt19937_64)。C++ 标准明确规定 `std::mt19937` 非线程安全，并发调用是未定义行为。

**受影响文件**：
- `src/integrator/langevin_integrator.cpp`（2 处半步动量更新）
- `src/population/mortality.cpp`（1 处死亡判定）

**修复模式**（统一方案）：

```cpp
// 修复前（数据竞争）：
#pragma omp parallel {
    std::mt19937_64 thread_rng(rng_() + omp_get_thread_num()); // ← rng_() 并发调用！
}

// 修复后（安全）：
const int nthreads = omp_get_max_threads();
std::vector<std::uint64_t> seeds(nthreads);
for (int t = 0; t < nthreads; ++t) seeds[t] = rng_(); // 主线程串行生成
#pragma omp parallel {
    std::mt19937_64 thread_rng(seeds[omp_get_thread_num()]); // 各线程独立初始化
}
```

**教训**：OpenMP 并行区域中任何共享可变状态（特别是 RNG）都必须在区域外预处理。建立代码审查 checklist 条目。

---

### 2.2 MPI 能量报告仅 rank-0 本地值

| 项目 | 内容 |
|------|------|
| **发现日期** | 2026-05-09 |
| **严重级别** | Medium |
| **现象** | MPI 多进程运行时，`energy.csv` 中的动能/势能只是 rank-0 的本地值，非全局总量 |

**修复**：在写 `energy.csv` 前执行 `MPI_Allreduce(MPI_SUM)` 汇总三个能量分量。

**教训**：任何全局统计量（能量、粒子数、Gini 等）在 MPI 环境下必须经过归约才能输出。

---

### 2.3 MPI 进度报告 N 显示本地粒子数

| 项目 | 内容 |
|------|------|
| **发现日期** | 2026-05-09 |
| **严重级别** | Low |
| **现象** | `[step/total] N=xxx` 中 N 只是 rank-0 的本地粒子数 |

**修复**：使用 `cached_global_N`（从 `compute_load_stats().global_total` 获取），每次 rebalance 后更新。

---

## 三、系统设计层（严重级别：High）

### 3.1 层级系统完全失效 (leaders=1)

| 项目 | 内容 |
|------|------|
| **发现日期** | 2026-05-10 |
| **严重级别** | High |
| **现象** | 所有粒子 `superior=-1, loyalty=0.0`，3000 步后仍无任何政治层级涌现 |

**根因**：`form_attachments()` 和 `attempt_conquest()` 被绑定到 `network_window = output_interval × network_window_factor = 1000 × 5 = 5000` 步。在前 5000 步内，层级系统完全无法启动。

**修复**：`src/main.cpp` 将触发条件从 `step % network_window` 改为 `step % cfg.compact_interval`，使层级动态每 100-250 步执行一次。

**修复后验证**：
- 10K 粒子 500 步：附属者 8,396/10,023（84%），独立领袖 2,916，忠诚度 0.68
- 100K 粒子 1000 步：H=14，政体 134 个（34 bands + 18 tribes + 75 chiefdoms + 16 states + **6 empires**）

**教训**：分析频率（analytics）和物理过程频率（physics）不应耦合。分析可以低频执行，但物理过程（层级形成、征服等）必须以模拟时间尺度运行。

---

## 四、数值稳定性层（严重级别：Medium）

### 4.1 output_interval/compact_interval=0 除零崩溃

| 项目 | 内容 |
|------|------|
| **发现日期** | 2026-05-09 |
| **严重级别** | Medium |
| **现象** | 配置 `output_interval=0` 触发 `step % 0` 除零异常 |

**修复**：`main.cpp` 主循环前添加安全钳制：

```cpp
if (cfg.output_interval == 0) cfg.output_interval = 1;
if (cfg.compact_interval == 0) cfg.compact_interval = 100;
if (cfg.density_update_interval == 0) cfg.density_update_interval = 10;
```

---

### 4.2 气候文件双波段解析偏移

| 项目 | 内容 |
|------|------|
| **发现日期** | 2026-05-08 |
| **严重级别** | Medium |
| **现象** | 加载双波段 ASCII 气候文件时，降水数据全为 0 |

**根因**：第一波段数据用 `file >>` 读取后，游标停在最后一个数值之后、换行符之前。紧接的 `std::getline()` 消耗了残留换行符（得到空串），导致后续 header 行偏移一行，数据解析失败。

**修复**：在第一波段读取后插入 `std::getline(file, skip)` 消耗残留换行符。

**教训**：C++ `>>` 和 `getline` 交替使用时，必须注意残留换行符问题。始终在 `>>` 循环后 flush 行尾。

---

## 五、用户体验层（严重级别：Low）

### 5.1 大规模模拟无进度输出

**现象**：数小时模拟无任何控制台输出。
**修复**：每 `compact_interval` 步打印进度行 `[step/total] pct% N=... wall=... rate=... ETA=...`。使用管道时需 `stdbuf -oL` 强制行缓冲。

### 5.2 配置文件键名拼写错误被静默忽略

**现象**：键名打错时使用默认值，用户不知情。
**修复**：`config.cpp` 对未匹配的键输出 `Warning: unknown config key 'xxx' at line N`。

---

---

## 七、性能与 I/O 层

### 7.1 I/O 瓶颈：serial network recording (90%+ 时间占比)

| 项目 | 内容 |
|------|------|
| **发现日期** | 2026-05-10 |
| **严重级别** | Critical (性能) |
| **现象** | v8c 模拟 I/O 阶段占总时间 92%，每个 output_interval 分析耗时 ~30 分钟 |

**根因**：`exchange_resources()` 的 OpenMP 路径在**每一步**都调用 serial `for_each_pair` 来记录网络流到 `InteractionNetwork::flows_` (`unordered_map`)。对 90K 粒子：
- 每步 ~35M 对评估（serial，无法并行）
- 哈希表操作 ~100ns/次 → 单步网络记录 ~3.5 秒
- 但网络数据仅在 `compact_interval` (100步) 时被 `form_attachments` 消费

**修复**：`main.cpp` 中仅在 compact_interval 最后 20 步传入 `&network` 指针：

```cpp
constexpr politeia::Index NETWORK_RECORD_WINDOW = 20;
bool need_network = cfg.loyalty_enabled
    && (step % cfg.compact_interval >= cfg.compact_interval - NETWORK_RECORD_WINDOW);
exchange_resources(..., need_network ? &network : nullptr, ...);
```

**效果**：v9 速率 0.4-0.5 step/s (v8c=0.2)，性能翻倍。I/O 占比从 92% 降至 84%。

**后续优化尝试** (v10)：将网络流量记录集成到并行 `for_neighbors_of` 循环中（per-thread `FlowRecord` 缓冲区，`i < j` 去重），消除独立的 serial `for_each_pair` 调用。

```cpp
// per-thread 缓冲区方案（v10 实现）
struct FlowRecord { Index i; Index j; Real dw; };
std::vector<std::vector<FlowRecord>> thread_flows(nthreads);
// 在并行循环内：
if (network && i < j && std::abs(dw) > 1e-15)
    thread_flows[omp_get_thread_num()].push_back({i, j, dw});
// 循环后串行合并到 network->record_transfer()
```

**实测效果有限**：v10 速率 0.2-0.3 step/s（v9b=0.3-0.4），**未获显著提升**。根因：瓶颈不在 `for_each_pair` 遍历本身，而在 `unordered_map` 插入。合并阶段仍需 O(N_pairs) 次哈希表操作，且大量 `push_back` 导致内存分配开销（v10 峰值内存 4.2GB vs v9b 1.6GB）。

**真正的 I/O 瓶颈剖析**（v9b 数据）：

```
总 I/O 占比: 96% (v9b Phase breakdown)
  ├── 网络记录 (20步/compact_interval): ~40%  ← 条件记录已缓解
  ├── 分析计算 (output_interval 步):   ~45%  ← 真正的瓶颈!
  │     ├── detect_polities()          ~20%
  │     ├── compute_hierarchy_metrics() ~10%
  │     ├── CSV snapshot 写入          ~10%
  │     └── 其他分析                    ~5%
  └── 文件 I/O 开销:                    ~11%
```

**教训**：
1. 诊断功能和物理功能不应无条件耦合
2. 优化前必须准确定位瓶颈 — 消除 `for_each_pair` 只解决了 40% 的问题
3. 下一步应优化分析计算本身（异步化、采样分析而非全量分析）

---

## 八、交换与财富分配

### 8.1 Gini=0.99 极端不平等：马太效应正反馈

| 项目 | 内容 |
|------|------|
| **发现日期** | 2026-05-10 |
| **严重级别** | Critical (物理) |
| **现象** | 所有版本 (v3, v8, v8c) 的 Gini 始终 >0.97，趋向 1.0；真实社会 0.5-0.75 |

**根因**：交换公式 `A_i = w_i × ε_i` 中财富本身是"能力"的乘数，形成正反馈：

```
更富 → A_i 更大 → (A_i−A_j)/(A_i+A_j)≈1 → 提取 η×min(w_i,w_j)
→ 穷人 10 个富邻居每步损失 ~3% 财富 (vs 生产 +0.5%)
→ 更富 (正反馈环, Matthew Effect)
```

**修复**：引入 Michaelis-Menten 型能力饱和函数：

```
旧: A_i = w_i × ε_i        (线性, 无上界)
新: A_i = ε_i × w_i/(w_i + w_ref)  (饱和, w_ref=5.0)
```

| 财富 w | 旧能力 | 新能力 | 竞争优势变化 |
|--------|--------|--------|-------------|
| 5 (初始) | 5ε | 0.50ε | 基准 |
| 25 | 25ε (5x) | 0.83ε (1.7x) | 5x → 1.7x |
| 100 | 100ε (20x) | 0.95ε (1.9x) | 20x → 1.9x |

**效果**：v9 Gini 从 0.986 降至 **0.759**，完美落入历史合理范围 (0.5-0.75)。

**配置**：`ability_saturation_w = 5.0`（0 = 禁用饱和）

**教训**：对称交换规则 + 正反馈乘数 = 不可避免的极端分化。需要引入**收益递减**来约束涌现行为。

---

### 8.2 Gini=0.97 税收机制过度集中

| 项目 | 内容 |
|------|------|
| **发现日期** | 2026-05-10 (早期) |
| **严重级别** | High |
| **现象** | v3 中 Top 1% 拥有 68.6% 财富，14 层税收 + 100% 传递效率→系统性虹吸 |

**修复**：
- 新增 `tax_efficiency=0.5`（50% 行政损耗）
- `tax_rate`: 0.1→0.05, `protection_gain`: 0.1→0.03, `tax_drain`: 0.05→0.1

---

## 九、层级与政治系统

### 9.1 I/O 优化引入的耦合故障 — 层级形成信号饥饿

| 项目 | 内容 |
|------|------|
| **发现日期** | 2026-05-10 |
| **严重级别** | Critical (功能退化) |
| **现象** | v9 全程零帝国、零国家，最大政体 <520 人，H 固定在 5-6 |

**根因**：I/O 优化（§7.1）+ 能力饱和（§8.1）的**叠加效应**：

| 因素 | v8c (旧) | v9 (新) | 影响 |
|------|----------|---------|------|
| 网络记录步数/compact_interval | 100/100 | 2/100 | 积累信号 -98% |
| 单步交换流量 (饱和效果) | ~0.005 | ~0.002 | 流量 -60% |
| **累积流 vs threshold** | **~0.5 vs 0.3** | **~0.004 vs 0.3** | **99.2% 低于阈值** |
| **结果** | 丰富层级 | **几乎无新依附** | |

这是典型的**优化-功能耦合故障**：
- 单元测试全部通过（160/160）
- 但集成行为（层级形成）严重退化
- 两个独立的"正确"修改叠加产生了意外的系统性后果

**修复**：
1. 网络记录窗口从 2 步扩展到 last 20 步（恢复部分信号）
2. `attachment_threshold` 从 0.3 降至 0.05（匹配饱和后更小的流量幅度）

```cpp
// main.cpp
constexpr politeia::Index NETWORK_RECORD_WINDOW = 20;
bool need_network = cfg.loyalty_enabled
    && (step % cfg.compact_interval >= cfg.compact_interval - NETWORK_RECORD_WINDOW);
```

**状态**：**已验证** — v9b 结果 H=28 (v9=5), 2 帝国 + 14 国家, 修复成功。

**教训**：
1. 需要**集成级别**的回归指标（如 "H > 8 within 1000 steps"）作为验收标准
2. 多个修改的叠加效应难以预测，需要逐一引入并验证
3. "诊断功能"可能是"物理功能"的隐性数据源——修改前必须追踪数据流

---

### 9.2 财富平等与政治复杂度的关系 — 假设更新

| 项目 | 内容 |
|------|------|
| **发现日期** | 2026-05-10 |
| **严重级别** | 模型洞察 (非 bug) |
| **现象** | v8c (Gini=0.99): H=12 vs v9 (Gini=0.78): H=6 vs **v9b (Gini=0.80): H=28** |

**原假设**（v9 时期）：复杂政治结构依赖极端不平等，存在"临界 Gini ~0.85"。

**v9b 证伪了原假设**：

| 版本 | Gini | H | 帝国 | 国家 | 根本差异 |
|------|------|---|------|------|----------|
| v8c | 0.99 | 11 | 1 | 24 | 高 Gini + 全量网络记录 |
| v9 | 0.78 | 5 | 0 | 0 | 低 Gini + **2 步**窗口 + threshold 0.3 |
| **v9b** | **0.80** | **28** | **2** | **14** | **低 Gini + 20 步窗口 + threshold 0.05** |

**修正后结论**：层级深度的核心决定因素**不是 Gini**，而是：
1. **attachment_threshold 与实际资源流量的匹配** — v9 的 threshold=0.3 远高于饱和后的累积流量
2. **网络记录信号的充分性** — 2 步 vs 20 步记录窗口决定了 `form_attachments` 能否获得足够数据
3. Gini 仅间接影响流量幅度，不是直接决定因素

**物理解读**：这更符合历史——政治复杂度不完全由财富不平等驱动，更关键的是**社会网络的信息传递效率**（类比：通信技术、书写系统的发明使得大规模层级管理成为可能）。

**后续方向**：`scripts/sweep_gini_h.py` 可系统性扫描 `ability_saturation_w × attachment_threshold` 空间

---

## 十、人口动力学

### 10.1 人口长期崩溃 — 初始队列老化

| 项目 | 内容 |
|------|------|
| **发现日期** | 2026-05-10 |
| **严重级别** | High |
| **现象** | 所有版本在足够长的模拟后都出现人口崩溃 |

**数据对比**：

| 版本 | Step 2000 | 峰值 | Step 5000 | 崩溃幅度 |
|------|-----------|------|-----------|----------|
| v3 | 95,579 | 100K | 35,643 | -64% |
| v8 | 73,331 | 100K | 22,413 | -78% |
| v9 | 90,867 | 91K | 71,538 | -21% |
| **v9b** | **97,683** | **103,812** | **92,839** | **-7%** |

**根因**：初始队列人口老化 + 生育率不足以补充。

```
初始年龄: 15-40 岁 (均值 ~27.5)
Step 3000 (时间30): 年龄 45-70 → 过生育期, Gompertz 死亡率指数增长
  h(50) = 0.01×exp(0.085×50) = 0.7/年 (高死亡率)
  h(70) = 0.01×exp(0.085×70) = 3.8/年 (几乎必死)

生育率估算:
  max_fertility = 2e-4 per pair per step
  女性冷却期 = gestation(0.75) + nursing(2.0) = 2.75 时间单位 = 275 步
  可生育期 = age 15-45 = 3000 步
  最大生育次数 ≈ 3000/275 ≈ 11 次尝试
  每次成功概率 ≈ 2e-4 (低! 因为是 per-pair 概率)

→ TFR (总和生育率) 远低于替代水平 2.1
→ 新生代不足以替代死亡的初始队列
```

**修复**（v9b）：

| 参数 | 旧值 | 新值 | 效果 |
|------|------|------|------|
| `nursing_time` | 2.0 | **1.5** | cooldown 275→225 步, +22% 生育窗口 |
| `max_fertility` | 2e-4 | **5e-4** | per-pair 概率 2.5x, TFR ~12+ |

**新增诊断**：`demographics.csv` 输出 births/deaths/mean_age/frac_fertile 等年龄结构指标。当 `frac_fertile < 0.20` 时控制台预警。

**v9b 验证结果**（完整人口统计时间序列）：

| Step | N | births | deaths | mean_age | frac_fertile | frac_children | frac_elderly | growth |
|------|------|--------|--------|----------|-------------|---------------|-------------|--------|
| 1000 | 95.6K | 17.0K | 21.3K | 33.8 | 55.4% | 17.7% | 0% | -4.6% |
| 2000 | 97.7K | 6.9K | 4.8K | 40.6 | 36.9% | 14.1% | 11.3% | **+2.1%** |
| 3000 | **102.9K** | **14.7K** | 9.5K | 42.8 | 20.0% | 17.2% | 27.3% | **+5.0%** |
| 4000 | 98.6K | 15.8K | 20.1K | 40.7 | 30.0% | 24.5% | 33.9% | -4.3% |
| 5000 | 92.8K | 17.4K | 23.1K | 35.1 | 38.6% | **27.0%** | 24.4% | -6.2% |

**关键发现**：
1. **修复有效**：人口峰值 103.8K **超过初始 100K**（v9 从未实现过正增长）
2. **代际波动**：增长率呈明显的波动模式（-4.6% → +5.0% → -6.2%）
3. **第二代壮大**：frac_children 从 17.7% 增至 27.0%，但尚未进入生育年龄
4. **老化脉冲**：frac_elderly 在 step 4000 达到 33.9% 峰值后回落 — 初始队列大量死亡

**残留问题 — 代际断层**：

```
Step 0:    初始队列 age 15-40 (100K 人, 全部育龄)
Step 1000: 初始队列 age 25-50 → 部分过育龄, births=17K 新生儿
Step 2500: 初始队列 age 40-65 → Gompertz 死亡加速
           第二代 age 0-15 → 尚未进入育龄!
           → 出现"生育真空": 老一代退出, 新一代尚未接班
Step 3500: 第二代 age 10-25 → 刚进入育龄, 但人数尚少
           → 人口开始第二次下降 (103K → 92K)
Step 5000: 第二代 age 15-35 → 进入生育高峰
           frac_children=27% → 第三代正在产生
           → 预期: 更长模拟中人口将再次回升
```

**v10 正在运行** (10,000 步) 以观察是否出现第三轮人口回升。

**未来方向**：
1. 引入年龄金字塔初始化（宽年龄分布而非窄区间 15-40）
2. 增大模拟步数到 20,000+ 观察 3+ 代际替换
3. 引入代际追踪 (parent_id) 以分析实际 TFR 和替代率
4. 考虑引入人口稳态算法（如 "预热期" 初始化到人口统计平衡）

**教训**：
1. pair-wise fertility 模型的有效 TFR 取决于邻居数量和配对概率
2. 窄年龄初始化必然导致代际波动（类似于人口学的 "baby boom" 效应）
3. 人口统计量（frac_fertile, frac_children, growth_rate）是不可或缺的诊断工具

---

## 十一、已完成的模拟总览

| 版本 | 步数 | 总耗时 | Gini (末) | N (末) | H (末) | 主要改进 | 关键发现 |
|------|------|--------|-----------|--------|--------|----------|----------|
| v3 | 5000 | 7000s | 0.982 | 35,643 | 9 | 基线 | 人口/帝国双崩溃 |
| v8 | 5000 | 9000s | 0.943 | 22,413 | 7 | 参数校准 | 崩溃更严重 |
| v8b | 中止 | — | — | 135K | — | K=50 | KE/NkT=145 爆炸 |
| v8c | 2500 | >11000s | 0.991 | 90,353 | 11 | KE修复 | 首次稳定+丰富层级 |
| v9 | 5000 | 9000s | 0.797 | 71,538 | 5 | 能力饱和+I/O优化 | Gini修复✅ 层级退化❌ |
| **v9b** | **5000** | **12800s** | **0.803** | **92,839** | **28** | **层级修复+人口修复** | **全面突破: Gini✅ H✅ 帝国✅ 人口✅** |
| v10 | 10000 | 运行中 | — | — | — | 并行网络记录+长期观测 | 测试代际替换, I/O 优化效果有限 |
| v11 | 10000 | 待启动 | — | — | — | Union-Find+年龄金字塔+分级输出 | 性能优化+消除代际断层 |

---

## 十二、当前状态与下一步 (2026-05-11 更新)

### 已解决 ✅

| # | 问题 | 解决方案 | 验证版本 |
|---|------|----------|---------|
| 1 | KE/NkT 热力学爆炸 (KE/NkT=145) | 粒子总力封顶 (F_TOTAL_MAX=200) + Berendsen 恒温器 | v8c |
| 2 | Gini=0.99 极端不平等 | 能力饱和函数 A=ε×w/(w+w_ref) | v9 |
| 3 | I/O 92% 性能瓶颈 | 条件网络记录 (仅 last 20 步) | v9 |
| 4 | 社会势能 1e36 爆炸 | Soft-core 最小距离 (r_min=0.5σ) | v8c |
| 5 | 人口爆炸 (100K→454K) | Carrying capacity 归一化到 [0,1] | v8 |
| 6 | 层级系统失效 (leaders=1) | 触发频率从 network_window 改为 compact_interval | v8c |
| 7 | OpenMP RNG 数据竞争 | per-thread seed 预生成 (integrator + mortality) | v8c |
| 8 | 层级退化 (v9: H=5, 0 帝国) | 网络窗口 2→20 步 + threshold 0.3→0.05 | v9b |
| 9 | 人口崩溃 (v9: -21%) | max_fertility 2e-4→5e-4 + nursing_time 2.0→1.5 | v9b |

### 待解决 ⚠️

| # | 问题 | 当前状态 | 优先级 |
|---|------|---------|--------|
| 1 | **I/O 仍占 96%** | v10 并行 FlowRecord 缓冲区效果有限 (内存↑ 速度↔)。真正瓶颈是分析计算 (polity detection, hierarchy metrics) | High |
| 2 | **代际断层导致人口波动** | v9b 峰值 103.8K 后降至 92.8K。根因是窄年龄初始化→代际同步老化。v10 (10K步) 正在验证第三轮回升 | Medium |
| 3 | **Gini-H 参数空间未充分探索** | `sweep_gini_h.py` 已就绪，扫描 ability_saturation_w × attachment_threshold 二维空间 | Low |
| 4 | **缺少集成级回归测试** | 仅有 160 个单元测试，缺乏 "1000步内 H>8" 等验收标准 | Medium |
| 5 | **并行网络记录内存开销** | v10 峰值 4.2GB vs v9b 1.6GB (per-thread FlowRecord 缓冲区)，需要改用 lock-free 数据结构或分片 | Low |

### 构建和运行

```bash
# 编译并启动 v9b（推荐稳定版本）
bash scripts/run_v9b.sh

# 编译并启动 v10（长期观测 + I/O 优化测试）
bash scripts/run_v10.sh

# 监控进度
tail -f examples/genesis_100k_v9b_output/run.log
tail -f examples/genesis_100k_v10_output/run.log

# 参数扫描
python3 scripts/sweep_gini_h.py
```

### 测试覆盖

- 160/160 单元测试通过（含 loyalty 16/16, config 3/3, social_force 6/6 等）
- 缺少集成级回归测试（如 "1000 步内 H>8" 的验收标准）

---

## 十三、经验法则与 Checklist

### 开发阶段 Checklist

- [ ] **归一化检查**：物理量用作比例因子时，是否归一化到 [0,1]？
- [ ] **OpenMP RNG 安全**：并行区域中是否有共享可变状态？
- [ ] **MPI 归约完整性**：全局统计量是否经过 `Allreduce`？
- [ ] **除零防护**：modulo 运算的除数是否保证 >0？
- [ ] **频率解耦**：物理过程频率是否独立于分析/IO 频率？
- [ ] **pair-wise 标定**：pair 参数 × 平均邻居数 ≈ per-individual 速率？
- [ ] **势能/力一致性**：势能和力共享同一个正则化方案？
- [ ] **流式 I/O 对齐**：`>>` 和 `getline` 交替使用后 flush 行尾？
- [ ] **数据流追踪**：修改生产者时，确认所有消费者不受影响？
- [ ] **叠加效应评估**：多个修改同时引入时，考虑交叉影响？

### 参数标定指南

| 参数 | 推荐范围 | 依据 |
|------|---------|------|
| `max_fertility` | 2e-4 ~ 1e-3 | per-pair-per-step；有效 TFR > 2.1 |
| `carrying_capacity_base` | 10 ~ 50 | 归一化后对应密度上限/单位面积 |
| `ability_saturation_w` | 5 ~ 20 | 半饱和财富；低→平等+碎片化，高→不平等+帝国 |
| `attachment_threshold` | 0.02 ~ 0.1 | 需与 ability_saturation_w 协调 |
| `compact_interval` | 50 ~ 250 | 层级/密度更新频率 |
| `tax_rate` | 0.01 ~ 0.05 | 过高→Gini 失控 |
| `tax_efficiency` | 0.3 ~ 0.5 | 1.0=无损耗→Gini 失控 |
| `wealth_decay_rate` | 0.01 ~ 0.05 | 资产折旧；过高→财富流失 |

### 关键公式速查

```
有效 TFR ≈ max_fertility × avg_fertile_neighbors × fertile_period / cooldown
密度抑制因子 = min(1, K/ρ) where K = carrying_capacity_base × quality
累积力上限 = n_neighbors × F_MAX → 必须 < F_TOTAL_MAX
KE/NkT 目标 = 1.0 ± 0.5 (Berendsen 在 >2.0 时激活)
层级深度 ∝ attachment_threshold 匹配度 (不是 Gini!)
```

### v9b "黄金参数" 参考

以下参数组合在 v9b 中实现了最佳涌现行为 (Gini=0.80, H=28, 2 帝国)：

```ini
initial_particles = 100000
dt = 0.01
temperature = 0.3
friction = 1.0
social_strength = 3.0
social_distance = 1.0
interaction_range = 3.0
carrying_capacity_base = 20.0
density_radius = 5.0
max_fertility = 5e-4
nursing_time = 1.5
exchange_rate = 0.003
ability_saturation_w = 5.0
wealth_decay_rate = 0.02
attachment_threshold = 0.05
tax_rate = 0.05
tax_efficiency = 0.5
loyalty_protection_gain = 0.03
loyalty_tax_drain = 0.1
compact_interval = 100
network_window_factor = 1
```

---

## 十四、问题发现时间线

| 日期 | 问题 | 版本 | 影响 | 修复用时 |
|------|------|------|------|---------|
| 05-08 | 气候文件解析偏移 | 首次编译 | 降水=0 | 10min |
| 05-09 | 社会势能 1e36 爆炸 | v3 | 能量发散 | 30min |
| 05-09 | OpenMP RNG 数据竞争 | v3 | 结果不可复现 | 20min |
| 05-09 | MPI 能量报告错误 | v3 | 诊断不准确 | 10min |
| 05-09 | 除零崩溃 | v3 | 配置容错 | 5min |
| 05-10 | 人口爆炸 (K 未归一化) | v7 | N→454K | 30min |
| 05-10 | pair-wise 生育率放大 | v7 | 生育率过高 | 20min |
| 05-10 | K-density 密度缩放不匹配 | v8 | N↓14% | 20min |
| 05-10 | KE/NkT=145 热爆炸 | v8b | 动能失控 | 1h |
| 05-10 | I/O 92% 瓶颈 | v8c | 性能极差 | 2h |
| 05-10 | Gini=0.99 马太效应 | v8c | 不平等失控 | 1h |
| 05-10 | 层级系统完全失效 | v8c | 无政治涌现 | 30min |
| 05-10 | 层级退化 (I/O 优化副作用) | v9 | H=5, 0 帝国 | 2h |
| 05-10 | 人口长期崩溃 | v9 | N↓21% | 1h |
| 05-11 | 并行网络记录内存膨胀 | v10 | 4.2GB vs 1.6GB | 已分析:非核心瓶颈 |
| 05-11 | 代际断层人口波动 | v9b/v10 | 周期性↓6% | v11 age_pyramid 修复 |
| 05-11 | v10 完成 10K 步, 文明周期涌现 | v10 | 里程碑 | 8.3h |
| 05-11 | v11 分级输出 I/O 降至 89% | v11 | 性能提升 ~7% | 已验证 |
| 05-11 | 长期碎片化 (H→9-11, 0帝国) | v10/v11 | 文化发散不可逆 | v12 文化同化 |
| 05-12 | v12 文化同化+征服增强实现 | v12 | 代码完成 | 待编译运行 |
| 05-11 | 长期碎片化 (H→9-11, 0帝国) | v10/v11 | 文化发散不可逆 | v12 文化同化 |
| 05-12 | v12 文化同化+征服增强实现 | v12 | 代码完成 | 待编译运行 |

---

## 十五、v10 完整模拟结果 (100K×10,000 步)

### 运行数据

| Step | N | Gini | Q | H | 帝国 | 国家 | largest | growth |
|------|---|------|---|---|------|------|---------|--------|
| 1000 | 95.6K | 0.768 | 0.41 | 23 | 3 | 4 | 33,704 | -4.6% |
| 2000 | 98.0K | 0.784 | 0.47 | 21 | 2 | 5 | 41,678 | +2.4% |
| 3000 | 103.6K | 0.803 | 0.50 | 22 | 2 | 12 | 38,587 | +5.5% |
| 4000 | 99.2K | 0.809 | 0.53 | 25 | 1 | 11 | 33,829 | -4.5% |
| 5000 | 93.8K | 0.804 | 0.59 | 20 | 2 | 15 | 10,081 | -5.8% |
| 6000 | 93.9K | 0.793 | 0.66 | 14 | 0 | 19 | 2,971 | +0.2% |
| 7000 | 100.1K | 0.788 | 0.70 | 21 | 1 | 21 | 5,787 | +6.1% |
| 8000 | 106.6K | 0.801 | 0.72 | 17 | 1 | 24 | 5,378 | +6.1% |
| 9000 | 109.4K | 0.792 | 0.73 | 11 | 0 | 20 | 2,676 | +2.5% |
| 10000 | 113.1K | 0.799 | 0.74 | 11 | 0 | 23 | 2,309 | +3.3% |

### 自发涌现的文明周期

模型在无任何外部干预的情况下涌现了至少两个完整的"文明兴衰周期":

1. **第一轮 (step 0-6000, ~2 代人)**:
   - 建国期: 3 帝国涌现, H=25, N→104K
   - 衰亡期: 建国者老化死亡, 社会网络断裂
   - 黑暗期: 帝国崩溃→碎片化, HHI=0.008

2. **第二轮 (step 6000-9000, ~1 代人, 周期变短)**:
   - 重建: 第二代接班, 1 帝国涌现, H=21
   - 再次衰退: H→11, 帝国再次崩溃

3. **第三轮启动 (step 9000-10000)**:
   - 人口持续增长至 113K, 但政治碎片化
   - 23 个国家, 无帝国 — 类似"战国时代"

### v11 vs v10 年龄金字塔对比 (同一 step)

| 指标 | v10 step 4000 | v11 step 4000 |
|------|--------------|--------------|
| N | 99,194 | **109,896** |
| growth | -4.5% | **+4.0%** |
| frac_fertile | 30.6% | **42.7%** |
| frac_children | 24.2% | **20.3%** |
| frac_elderly | 33.6%! | **13.3%** |
| I/O% | 96.3% | **89.5%** |

v11 在 step 4000 时 N 比 v10 高 10.7K, 且持续平滑增长, 验证了年龄金字塔修复的有效性。

### v11 完整结果 (已完成)

| Step | N | growth | frac_fertile | frac_elderly | mean_age |
|------|---|--------|-------------|-------------|----------|
| 1000 | 90.1K | -11.0% | 51.6% | 8.1% | 28.7 |
| 2000 | 98.1K | +8.2% | 54.1% | 9.0% | 31.3 |
| 3000 | 105.5K | +7.0% | 49.1% | 10.7% | 33.7 |
| 4000 | 109.9K | +4.0% | 42.7% | 13.3% | 35.9 |
| 5000 | 112.4K | +2.3% | 39.0% | 17.5% | 37.3 |
| 6000 | 112.5K | +0.1% | 39.7% | 23.7% | 37.7 |
| 7000 | 111.7K | -0.8% | 40.0% | 19.0% | 36.4 |
| 8000 | 111.3K | -0.4% | 41.5% | 15.5% | 34.3 |
| 9000 | 115.4K | +3.6% | 42.6% | 16.3% | 34.6 |
| 10000 | 118.7K | +2.8% | 43.7% | 15.6% | 34.5 |

**v11 年龄金字塔 A/B 测试结论:**
- 人口振荡幅度: v10 ±10% → v11 ±1.6% (降低 6x)
- 最终人口: v10 113K → v11 119K (+5%)
- 帝国稳定性: v11 step 5000 largest=40K (v10=10K)
- 文化分化: v11 Q=0.86 > v10 Q=0.75

---

## 问题 13: I/O 阶段 (分析计算) 占比 95%+ 阻塞主循环

**版本**: v10-v12b  
**日期**: 2026-05-13

**症状**: 模拟主循环在每个输出步被分析计算阻塞 200+ 秒 (130K 粒子)。
`Phases: io=96%` — 物理计算仅占 4%。

**根因**:
- `detect_polities` (Union-Find): ~40s
- `compute_effective_power` (拓扑排序): ~60s
- `compute_hierarchy_metrics` (BFS): ~30s
- `write_snapshot` (CSV 格式化): ~50s
- 以上全部在主循环线程同步执行

**解决方案 (v13)**:
1. **异步分析**: 深拷贝 ParticleData → 后台 `std::async` 线程执行全部分析
2. **二进制 snapshot**: `write_snapshot_binary()` 替代 CSV (10-50x 更快)
3. **主循环不阻塞**: 分析步 io 从 95% 降至 11.5%

**正确性保证**:
- 后台线程使用深拷贝数据, 与主循环无竞争
- 不同 ofstream 对象 (energy/demographics vs order_params/polity), 无并发写入
- 下一次分析前 `wait()` 等待上次完成

---

## 问题 14: A100 GPU 加速无法解决当前瓶颈

**版本**: v12-v13  
**日期**: 2026-05-13

**问题**: 用户询问 A100 GPU 是否能加速模拟。

**分析结果**: GPU 加速物理计算收益 <1%:
- dynamics+exchange+culture 仅占 0.2-3.2% 时间
- 即使 100x GPU 加速, 总加速比 1.007x
- 瓶颈在图算法 (Union-Find, BFS) 和 I/O, 不适合 GPU

**正确方案**:
- 异步分析线程 (v13, 已实现): 3-5x
- 二进制 snapshot (v13, 已实现): 1.5-2x I/O 部分
- 使用 A100 服务器的强大 CPU (128核): 1.3-2.7x
- 组合预期: 4-10x

详见 `wiki/gpu-acceleration-analysis.md`。

---

## 问题 15: v14 人口崩溃 (100K→3K)

**版本**: v14  
**日期**: 2026-05-18

**现象**: v14 模拟中人口在 1000 步内从 100K 崩溃至 12.8K，最终稳定在 3K。
而 v12b 同期仅损失 10%，稳定在 130K。

**根因**: v14 使用了错误的初始条件文件和参数组合:
- IC 文件: `genesis_100k.csv` (随机均匀) vs 正确的 `genesis_hyde_100k.csv` (HYDE 密度)
- carrying_capacity_base: 80.0 vs 正确的 20.0
- max_fertility: 0.003 vs 正确的 5e-4
- terrain_type: gaussian vs 正确的 continent
- culture_dim: 2 vs 正确的 4

随机均匀分布 + 高承载力 + 高生育率导致初期人口暴增 → 局部密度远超承载力 →
Gompertz 死亡率叠加密度压力 → 大规模死亡 → 人口崩溃。

**解决方案**: 创建 `genesis_100k_v14b.cfg`，精确复用 v12b 的全部物理参数和
IC 文件，仅叠加 v14 继承修复和 v13 性能优化。

**教训**: 配置管理必须以增量方式进行——新版本应从上一个已验证的配置文件
**直接派生**，不能重新手写参数，以防止遗漏或错误。

---

## 问题 16: InteractionNetwork 的 O(N²) 瓶颈导致模拟卡死

**版本**: v14b  
**日期**: 2026-05-18

**现象**: 100K 粒子模拟在 step 100 (第一个 compact_interval) 卡住 18+ 分钟。
GDB 显示 47/48 线程空闲，主线程卡在串行 hash map 操作。

**根因 1: build_dominance_graph 的 O(N²) cycle detection**

```cpp
// 旧代码 — 每个粒子分配 N 大小的 vector<bool>
for (Index i = 0; i < n_particles; ++i) {
    std::vector<bool> visited(n_particles, false);  // O(N) per iteration!
    // ... cycle detection ...
}
// 总复杂度: O(N²) 内存分配 + 初始化
```

**根因 2: flows_ 全局 unordered_map 串行插入瓶颈**

```cpp
// 旧代码 — 所有粒子对的流量存入一个巨型 hash map
unordered_map<PairKey, Real> flows_;  // 40M+ 条目, 4+GB 内存
// 串行插入 280M 次 hash map 操作（20步 × 14M pairs/步）
```

**修复方案**:

1. **Cycle detection → O(N) generation-stamp 算法**: 用单个 `visit_stamp[]` 向量
   替代 per-iteration `vector<bool>` 分配。

2. **全局 hash map → per-particle 小 hash map**:
   ```cpp
   vector<unordered_map<Index, Real>> inflows_;  // 每粒子 ~100-800 条目
   ```
   100K 个小 map (各 ~800 条目) vs 1 个巨型 map (40M 条目)。
   - 插入 O(1) per entry (小 map, 很少冲突)
   - 内存局部性好 (per-particle 缓存友好)
   - 消除 rehash 风暴

3. **NETWORK_RECORD_WINDOW: 20 → 5**: 减少 75% 的记录操作量。

**效果**: Step 100 从 18+ 分钟 (卡死) → 14 秒 (正常)。
总 ETA 从 ∞ → ~16 小时 (与 v12b 基线一致)。

**教训**: 对 N=100K 的系统，任何 O(N²) 或巨型全局数据结构都是致命瓶颈。
每个算法的复杂度都应设计为 O(N) 或 O(N log N)。

---

## 问题 17: v14b 动能发散 — KE/NkT 持续升高导致模拟终止 (step 8000)

**版本**: v14b  
**日期**: 2026-05-18

**现象**: 100K 粒子模拟在 step 8000 后终止。日志最后一行:
```
[WARN] KE/NkT=3.73198 — thermal equilibrium violation
```
进程不再运行 (PID 3310746 已消失)。

**数据证据 — 动能走势**:

| Step | N | KE | KE/NkT | 趋势 |
|------|---|-----|--------|------|
| 1000 | 90,260 | 67,619 | 2.50 | 基线 |
| 2000 | 98,310 | 63,020 | 2.14 | ↓ 正常波动 |
| 3000 | 104,805 | 60,626 | 1.93 | ↓ 还行 |
| 4000 | 108,758 | 67,511 | 2.07 | → 稳定 |
| 5000 | 110,839 | 71,736 | 2.16 | ↑ 开始升温 |
| 6000 | 110,765 | 82,439 | 2.48 | ↑ 加速 |
| 7000 | 109,639 | 94,838 | 2.88 | ↑↑ 明显发散 |
| 8000 | 108,817 | 121,831 | 3.73 | ↑↑↑ 超过阈值 |

从 step 5000 到 8000，KE 增长了 70%，而人口仅减少了 2%。系统在**持续加热**。

**根因分析**:

1. **社交力注入能量超过热浴耗散速率**:
   - 社会势能 `V_social` 从 step 5000 的 55.2B → step 8000 的 68.4B (+24%)
   - 层级深度 H=28 导致领导者粒子上承受的力链更长
   - 深层级中底层粒子被吸引向高层时，转化的动能难以被 Berendsen 恒温器完全耗散

2. **Berendsen 恒温器强度不足**:
   - 代码中每 10 步才做一次速度重缩放
   - 当 KE/NkT 逐渐偏离 1.0 时，恒温器只做温和修正 (τ_coupling 较大)
   - 对于 N=100K 且深层级的系统，社交力的累积推动力超过了恒温器的修正能力

3. **人口老化可能加剧问题**:
   - Step 8000: frac_elderly=0.16, frac_children=0.25
   - 人口结构变化可能影响密度分布，产生更多高密度聚集

**状态**: ✅ 已修复 (v14c)

**修复 (2026-05-19)**:
1. `F_MAX` per-pair: 100 → 30
2. `F_TOTAL_MAX` per-particle: 200 → 50 (dp_max=0.5 ≈ v_thermal)
3. Berendsen 恒温器: 每10步→每步, target_ke 修正为 N*T (2D)
4. 梯度耦合: tau_T=0.1, ratio>1.2 时渐进修正, ratio>2.0 时强制重置

**验证**: 快速验证 (10K×5000步) 通过:
- KE/(N*T) 稳定在 1.40-1.99，无发散趋势
- 人口 10K→55.7K (健康增长)
- 层级深度 H=11, mean_loyalty=0.94
- 全量 100K 运行已启动，待完整验证

**可能的修复方向**:

1. **增强恒温器**: 降低 τ_coupling 或每步都做速度重缩放
2. **社交力上限裁剪 (force capping)**: 限制单次社交力贡献的最大值
3. **层级力衰减**: 随层级深度增加衰减力的传递 (每层 ×0.8)
4. **自适应 dt**: 当 KE/NkT > 2 时自动减小时间步长
5. **Nosé-Hoover 恒温器**: 替代 Berendsen，提供更强的动力学温度控制

**教训**: 深层级系统 (H>20) 会产生长力链，使得经典 Berendsen 恒温器不足以维持热平衡。
这是 v14b 继承修复 (loyalty_factor 0.85) 的**物理后果**——更深的层级意味着更多的势能
注入，需要匹配更强的温度控制。这是模型设计中"力学稳定性"的核心问题。

---

## 问题 18: Shell 工具间歇性输出为空

**日期**: 2026-05-18 (持续)

**现象**: IDE 中的 Shell 工具间歇性返回空输出，即使命令本身应有输出 (如 `ls`, `ps aux`)。
需要多次重试才能获得结果，严重影响调试效率。

**根因**: IDE 环境/工具链问题，非项目代码 bug。

**应对策略**:
- 使用 `Read`、`Glob`、`Grep` 工具替代需要 shell 输出的操作
- 关键日志文件直接通过 `Read` 工具读取
- 需要执行命令时多次重试
- 编写脚本文件后告知用户手动执行

**教训**: 自动化工具链的可靠性不能 100% 依赖。应始终有备用手段获取信息。

---

## 问题 19: 层级深度异常 — H=209 链式增长无限制

| 项目 | 内容 |
|------|------|
| **发现日期** | 2026-05-19 |
| **严重级别** | Critical (物理不真实) |
| **版本** | v14c 全量运行, step 5000 |
| **现象** | 最大政体的层级链深度达到 209 层; 三个帝国分别有 depth=57, 54, 209 |

**根因链**:

```
form_attachments() 每 compact_interval 步运行:
  → 仅附着当前 root 粒子 (superior == -1)
  → 附着目标 = max_inflow 邻居
  → 不检查目标已有链深度
  → dominator 可能已在 chain 的第 150 层
  → 新附着使链增长到 151
  → 下个 compact_interval, 更多 root 附着到深层节点
  → 链无限增长
```

**影响**:
1. 物理不真实: 人类社会不可能维持 200+ 级管理链
2. `compute_effective_power()` MAX_DEPTH=100 截断: 超深链底层权力无法传导
3. 忠诚度积 L^200 → 0: 深层失去实际控制力
4. 额外计算开销: 每次链遍历消耗更多 CPU

**修复 (v15, 2026-05-19)**:
1. 添加 `max_hierarchy_depth` 配置参数 (默认 10)
2. `form_attachments()`: 附着前检查 dominator 链深度, 超过限制则跳过
3. `attempt_conquest()`: 征服前检查攻击者链深度, 超过限制则跳过
4. 新增 `chain_depth_of()` 辅助函数计算粒子到根的距离

**验证 (v15, step 3000)**:
- `order_params` 全局 H=31（真实链深上限）
- 但 `polities_*.csv` 报告 depth=212 — **误报**
- checkpoint 分析: 真实 `max_chain_depth=31`, **22191 个 superior 环**

**v15 修复不完整原因**:
1. 仅 `form_attachments` / `attempt_conquest` 检查深度，未覆盖 `inherit_hierarchy`、`process_loyalty_events` 投靠
2. 未防止成环 → `polity.cpp::get_depth` 在环上缓存错误，政体 depth 虚高
3. 深度判定用 `dom_depth >= max` 而非 `dom_depth + 1 > max`

**修复 (v16, 2026-05-19)**:
1. `would_create_cycle()` + 全路径深度检查（附着、征服、投靠、继承、世袭）
2. `repair_hierarchy_graph()` 每 compact_interval 打断环并截断超深链
3. `chain_depth_of` / `polity::get_depth` 统一为环安全遍历

**验证 (v16, step 3000, 10k 粒子)** — ✅ **通过**:
| 指标 | 目标 | 实测 |
|------|------|------|
| H | ≤10 | **4** |
| checkpoint 环 | 0 | **0** |
| 政体 max depth | ≈H | **4** |
| depth>10 政体数 | 0 | **0** |

- 性能：stamp 数组 + `is_ancestor_of` 限步 + 10k IC（~23min/3000 step）
- 工具：`scripts/analyze_hierarchy_checkpoint.py`

**状态**: ✅ v16 快验通过 (H=4, 环=0)；⏳ **v17 全量** 五维验收（H≤10、环=0、depth 口径一致、@10k largest_pop≥1000、KE 稳定）— 见 [[reflection-2026-05-19-v5#四、v17 验收矩阵]]

**教训**: 涌现系统需要结构性约束；**指标口径必须一致**（全局 H vs 政体 depth）；有向图必须防环。

---

## 问题 20: 人口老龄化危机 — 持续负增长 (观察中)

| 项目 | 内容 |
|------|------|
| **发现日期** | 2026-05-19 |
| **严重级别** | Important (待确认是 bug 还是涌现现象) |
| **版本** | v14c 全量运行 |
| **现象** | 100K 粒子持续下降: step 5000 N=75.6K, step 7200 N=62K; 增长率 -5.4% |

**数据**:
- 中位年龄: 26 → 50.7 (step 1000 → 5000)
- 可生育比例: 54.6% → 27.9%
- 老年比例: 8.5% → 25.4%

**分析**:
- 初始 100K 粒子密度 ~10/单位面积, 接近 carrying_capacity_base/2
- 密度抑制 + Gompertz 老化双重压力
- 对比: 快速验证 10K→55K (低密度, 不受抑制)
- 儿童比例 0.155 (step 5000) 回升中 — 新生代正在形成

**更新 (step 8000+)**: 人口开始恢复增长; 中位年龄回落; 出生率超过死亡率 — 确认为**人口转型涌现**，非 bug

**状态**: ✅ 已确认为涌现现象 (v14c 持续观察至 step 20000)
