# Politeia 经验教训

> 从 v3→v11 六代模拟中提炼的开发原则。
> 每条教训标注来源（反思/troubleshooting 中的具体案例），以便追溯。
> 目标：后续开发者（包括未来的自己）**不重蹈覆辙**。

---

## 一、性能优化：先测量，再动手

### 原则 1.1：永远不要凭直觉猜瓶颈

**反模式**：v10 中凭"serial `for_each_pair` 肯定很慢"的直觉实施了并行 FlowRecord 缓冲区。

**结果**：速度未变 (0.3 step/s ≈ v9b)，内存膨胀 2.6 倍 (4.2GB vs 1.6GB)。

**真相**：瓶颈在分析计算 (`detect_polities` ~120s, `compute_hierarchy_metrics` ~80s)，不在数据采集。

**正确做法**：
1. 用计时器精确测量每个阶段耗时
2. 按时间占比排序，优化排名第一的
3. 优化后再次测量，确认改善

> 来源：[[wiki/reflection-2026-05-11#1.1 误判瓶颈位置]]

### 原则 1.2：算法复杂度 > 并行化

**案例**：`find_root()` 的 O(N×depth) 链式查找在 H=28 时产生 2.8M 次哈希查找，比 serial `for_each_pair` 慢得多。改用 Union-Find (路径压缩) 可将复杂度降至 O(N×α(N)) ≈ O(N)。

**原则**：在考虑并行化之前，先检查是否有更好的算法。O(N log N) 的单线程通常快于 O(N²) 的多线程。

> 来源：[[wiki/reflection-2026-05-11#2.2]], [[wiki/troubleshooting#1.6]]

### 原则 1.3：避免冗余计算，定期做"计算流图审计"

**案例**：`compute_effective_power()` 在 `main.cpp` 和 `compute_hierarchy_metrics()` 中各调用一次，对 100K 粒子做了两次拓扑排序。

**做法**：每当模块增长到一定程度，画出数据流图，标注每个计算的调用者和消费者，识别重复。

> 来源：[[wiki/reflection-2026-05-11#1.2]]

---

## 二、耦合陷阱：这个系统比你想的更紧密

### 原则 2.1：优化 ≠ 纯局部操作——每次修改都要追踪数据流

**模式**：项目已出现**三次**"优化导致功能退化"：

| 次数 | 修改 | 预期 | 实际副作用 |
|------|------|------|-----------|
| 1 | v9 网络记录窗口 100→2 步 | I/O 减少 | 层级信号饥饿 → H 从 12 降至 5 |
| 2 | v10 并行 FlowRecord | 速度提升 | 内存 2.6x，速度不变 |
| 3 | v8c 能力饱和 | Gini 合理化 | 附属流量幅度骤降 → 政治碎片化 |

**根因**：交换→网络→层级→政体 是一条紧密耦合链。任何环节的"局部优化"都可能产生全局副作用。

**防御措施**：
- 修改生产者时，**列出所有消费者**并评估影响
- 多个修改**逐一引入**并分别验证，不要批量合并
- "诊断功能"可能是"物理功能"的隐性数据源

> 来源：[[wiki/reflection-2026-05-10-v2#二]], [[wiki/reflection-2026-05-11#1.3]]

### 原则 2.2：分析频率 ≠ 物理过程频率

**案例**：`form_attachments` 被绑定到 `network_window = 5000` 步，导致前 5000 步层级系统完全无法启动。

**原则**：分析（输出 CSV、画图）可以低频。物理过程（层级形成、征服、人口更新）必须以模拟时间尺度运行，与 I/O 频率**完全解耦**。

> 来源：[[wiki/troubleshooting#3.1]]

### 原则 2.3：参数空间是高度耦合的——不能逐个调参

**案例**：修复 carrying capacity → 暴露生育率太高 → 修复生育率 → 暴露忠诚度太均匀 → 修复忠诚度 → 暴露 Gini 太极端。

**做法**：
- 定义多目标健康指标（Gini ∈ [0.5,0.8], H > 8, N 增长 ∈ [-5%,+5%]）
- 用参数扫描脚本 (`param_sweep.py`, `sweep_gini_h.py`) 联合搜索
- 不要手动逐个调参

> 来源：[[wiki/reflection-2026-05-10#3.2]]

---

## 三、pair-wise 模型的参数陷阱

### 原则 3.1：pair 参数 × 邻居数 = 个体速率

**案例**：`max_fertility=0.005` 看起来很小，但每粒子 ~46 个邻居 → 有效个体生育率 ≈ 23%/步。

**公式**：
```
p_individual ≈ 1 - (1 - p_pair)^N_neighbors ≈ N_neighbors × p_pair  (当 p_pair 很小时)
```

**实践**：设计 pair-wise 参数时，**先估算有效个体速率**，再与物理预期对比。

> 来源：[[wiki/troubleshooting#1.3]]

### 原则 3.2：累积力可远超单对力上限

**案例**：F_MAX=100 仅限制单对力，但 42 个邻居的累积力 = 42 × 100 = 4,200。Langevin 恒温器在力-摩擦平衡态下无法修正温度。

**做法**：除了 per-pair F_MAX，还需要 per-particle F_TOTAL_MAX。高密度场景需要 Berendsen/Nosé-Hoover 等显式温控。

> 来源：[[wiki/troubleshooting#1.5]]

---

## 四、尺度不变性：小规模校准 ≠ 大规模有效

### 原则 4.1：参数必须在目标规模上标定

**案例**：用 10K 粒子校准的 `carrying_capacity_base=5.0` 在 100K 粒子下完全失效——密度从 1/unit² 变为 10/unit²，繁殖被 100% 抑制。

**做法**：
- 引入无量纲比 `ρ/K` 作为核心监控指标
- 参数扫描用**与生产运行相同规模**的粒子数
- 至少用生产规模的 1/10 做快速验证

> 来源：[[wiki/troubleshooting#1.4]]

### 原则 4.2：初始条件的偏差会被放大

**案例**：所有粒子初始年龄 15-40 岁 → 代际同步老化 → step 2500-4000 人口崩溃。这不是模型错误，是初始条件的人为偏差。

**做法**：使用物理合理的初始分布（如年龄金字塔 `age_pyramid=true`），而非方便的均匀分布。

> 来源：[[wiki/reflection-2026-05-11#2.3]], [[wiki/troubleshooting#10.1]]

---

## 五、测试策略：单元测试不够

### 原则 5.1：需要集成级回归指标

**案例**：v9 修改后 160/160 单元测试全部通过，但层级形成严重退化（H 从 12 降至 5，帝国从 1 降至 0）。

**缺失的测试类型**：
- "1000 步内 H > 8"
- "Gini ∈ [0.5, 0.85]"
- "人口变化率 ∈ [-10%, +10%]"
- "至少存在 1 个 state 级政体"

**原则**：涌现系统的正确性无法用单元测试覆盖——需要**端到端的涌现指标验收标准**。

> 来源：[[wiki/reflection-2026-05-10-v2#二]], [[wiki/troubleshooting#9.1]]

### 原则 5.2：健康指标需要自动预警

**已实现**：
- Gini > 0.85 → 警告
- KE/NkT > 3.0 或 < 0.2 → 警告
- frac_fertile < 20% → 警告
- |V_social| > 1e12 → 警告

**教训**：不要等模拟跑完再分析 CSV。实时预警能节省数小时的无效运行。

> 来源：[[wiki/troubleshooting#十三]]

---

## 六、物理量与数值

### 原则 6.1：物理量用作比例因子前必须归一化

**案例**：地形势能 V ∈ [-138, 0] 直接乘以 `carrying_capacity_base=50` → K=6923，密度抑制完全失效 → 人口爆炸到 454K。

**原则**：任何将物理量（势能、高度、温度等）映射为比例因子或概率的地方，先归一化到 [0, 1]。

> 来源：[[wiki/troubleshooting#1.1]]

### 原则 6.2：势能和力必须共享同一正则化方案

**案例**：力有 F_MAX 封顶但势能没有 → 粒子重叠时势能达 1e36，能量诊断完全失去意义。

**做法**：引入 soft-core 最小距离后，力和势能都基于 `r2_eff = max(r2, r_min_sq)` 计算。

> 来源：[[wiki/troubleshooting#1.2]]

### 原则 6.3：C++ `>>` 和 `getline` 交替使用时注意残留换行符

**案例**：双波段 ASCII 气候文件解析中，`>>` 读完温度数据后残留换行符，导致后续 `getline` 偏移一行，降水全为 0。

**做法**：在 `>>` 循环后始终插入 `std::getline(file, skip)` 消耗残留。

> 来源：[[wiki/troubleshooting#4.2]]

---

## 七、OpenMP / MPI 并行编程

### 原则 7.1：并行区域内禁止共享可变状态（特别是 RNG）

**案例**：`#pragma omp parallel` 区域内多线程并发调用 `rng_()`，这是未定义行为。出现在 integrator 和 mortality 两处。

**模式**：
```cpp
// 错误：rng_() 在并行区域内被并发调用
#pragma omp parallel {
    std::mt19937_64 thread_rng(rng_() + omp_get_thread_num());
}

// 正确：主线程预生成种子
std::vector<uint64_t> seeds(nthreads);
for (int t = 0; t < nthreads; ++t) seeds[t] = rng_();
#pragma omp parallel {
    std::mt19937_64 thread_rng(seeds[omp_get_thread_num()]);
}
```

> 来源：[[wiki/troubleshooting#2.1]]

### 原则 7.2：全局统计量在 MPI 下必须经过归约

**案例**：`energy.csv` 中的动能/势能只是 rank-0 的本地值。

**做法**：任何全局量（能量、粒子数、Gini）在输出前执行 `MPI_Allreduce(MPI_SUM)`。

> 来源：[[wiki/troubleshooting#2.2]]

### 原则 7.3：并行化优先选择 per-particle 循环而非 pair 遍历

**案例**：Cell List 的 `for_each_pair`（Newton 第三定律优化）虽减少计算量，但无法并行化。改用 `for_neighbors_of`（每粒子独立邻居搜索）+ OpenMP `parallel for` 实现并行。

**权衡**：`for_neighbors_of` 计算量翻倍（每对算两次），但可以多线程。在核数 > 4 时净收益为正。

> 来源：[[wiki/troubleshooting#1.6]]

---

## 八、方法论：涌现系统的开发节奏

### 原则 8.1：外科手术式优化

> 当一个复杂系统的涌现行为已经正确时，进一步的优化应该是**外科手术式**的：
> 精确测量 → 定位最大瓶颈 → 最小化改动 → 验证无退化。
> 不是"感觉哪里慢就改哪里"。

> 来源：[[wiki/reflection-2026-05-11#六]]

### 原则 8.2：先定性成功，再定量校准

v3 用 100K 粒子跑出了完整政治光谱（bands→tribes→chiefdoms→states→empires），虽然 Gini=0.97 不合理。但**定性涌现正确是第一步**，定量校准是第二步。

不要在定性行为还不对时就追求定量精度。

> 来源：[[wiki/reflection-2026-05-10#五]]

### 原则 8.3：小规模快速迭代 → 大规模验证

**推荐流程**：
1. 1K 粒子 × 100 步：快速验证代码不崩溃（秒级）
2. 10K 粒子 × 500 步：验证涌现指标方向正确（分钟级）
3. 100K 粒子 × 5000 步：正式生产运行（小时级）

**反模式**：直接跑 100K × 5000 → 发现参数不对 → 浪费数小时。

> 来源：[[wiki/reflection-2026-05-10#3.2]]

### 原则 8.4：人口统计诊断是必需品，不是可选项

`demographics.csv`（births/deaths/mean_age/frac_fertile/growth_rate）是 v9b 最有价值的基础设施投入。没有它，人口崩溃的根因分析将极其困难。

**原则**：对于任何涌现系统，中间诊断量（不只是最终指标）是理解行为的关键。

> 来源：[[wiki/reflection-2026-05-11#六]]

---

## 九、被证伪的假设（避免重犯）

| 假设 | 提出时间 | 证伪版本 | 正确理解 |
|------|---------|---------|---------|
| 临界 Gini ~0.85 才有帝国 | v9 | v9b (Gini=0.80, H=28, 2 帝国) | 层级深度取决于 attachment_threshold 匹配度，不是 Gini |
| serial for_each_pair 是性能瓶颈 | v9b | v10 (优化后速度不变) | 真正瓶颈在分析计算 (detect_polities, hierarchy_metrics) |
| 税收参数控制 Gini | v3-v8 | 参数扫描 (36组, Gini 0.886-0.893) | 不平等从对称交换规则涌现，税收参数几乎无影响 |
| Gini 平等 → 政治碎片化 (不可调和) | v9 | v9b (Gini=0.80, 丰富层级) | 碎片化是因为网络信号不足，不是因为 Gini 低 |

---

## 十、层级图不变量（2026-05-19）

### 原则 10.1：superior 图必须用 checkpoint 验收，不能只看一个 CSV

**案例**：v15 `order_params.H=31`，但 `polities.depth=212`；checkpoint 发现 22191 个环。

**做法**：`scripts/analyze_hierarchy_checkpoint.py` + `order_params.H` + 政体 max depth 三者交叉。

> 来源：[[reflection-2026-05-19-v4]], [[query-2026-05-19-hierarchy-baseline]]

### 原则 10.2：修层级时要同时看「依附率」和「最大政体」

**案例**：v16 H=4、零环，但 n_attached=63%、最大政体 30 人；v14c H=64 却有 3 帝国。

**做法**：快验 10k/3k 记录 H、环、largest_pop、empires；全量对照 v14c。

> 来源：[[reflection-2026-05-19-v4]]

### 原则 10.3：repair 是 O(n) 热路径，禁止 per-particle 堆分配

**案例**：v16 首版 `repair_hierarchy_graph` 每粒子 `unordered_set`，10 万粒子数分钟无 step 100 日志。

> 来源：[[reflection-2026-05-19-v3]]

### 原则 10.4：层级修复要双标准验收（图论 + 文明）

**模式**：v16 满足 H≤10、零环，但最大政体仅 30 人、mean_loyalty=0.30。

**原则**：`max_hierarchy_depth` / `repair` 解决的是 **有向图病态**；帝国、HHI、loyalty 是 **另一轴**。全量验收必须同时看 checkpoint（环、链深）与 `polity_summary`（largest_pop），见 [[reflection-2026-05-19-v5#四、v17 验收矩阵]]。

> 来源：[[reflection-2026-05-19-v4]], [[reflection-2026-05-19-v5]]

---

## 十一、开发 Checklist（每次修改前过一遍）

- [ ] **瓶颈定位**：是否用计时器/profiler 确认了瓶颈位置？
- [ ] **数据流追踪**：修改的模块有哪些下游消费者？它们会受影响吗？
- [ ] **归一化检查**：物理量用作比例因子时，是否归一化到 [0,1]？
- [ ] **pair→individual 换算**：pair-wise 参数 × 平均邻居数 ≈ 合理的个体速率？
- [ ] **累积力检查**：n_neighbors × F_MAX < F_TOTAL_MAX？
- [ ] **OpenMP 安全**：并行区域内是否有共享可变状态？
- [ ] **MPI 归约**：全局统计量是否经过 Allreduce？
- [ ] **势能/力一致**：正则化方案是否同时应用于力和势能？
- [ ] **尺度一致**：参数是否在目标粒子规模下校准？
- [ ] **集成验收**：修改后涌现指标（Gini/H/N/polity）是否仍在目标范围？
- [ ] **层级验收**：checkpoint 环=0？H≤max？largest_polity 未塌缩？
- [ ] **逐一验证**：多个修改是否分开引入并分别验证？

---

*创建日期：2026-05-11*
*来源：reflection-2026-05-10, reflection-2026-05-10-v2, reflection-2026-05-11, troubleshooting.md*
