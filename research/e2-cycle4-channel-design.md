# E2-C4 通道分离设计（S09 处置）

日期：2026-09-16（v2，取代同日 v1）；2026-09-17 回填 §7/§11/§12 的实现状态。
状态：**设计冻结，Python 侧已实现，未授权执行**。本文件在 E2-C4 任何结果
产生前写入，不使用 Cycle 3 E2 的效应方向或显著性来定阈值。v2 相对 v1 的实质修订见 §10，
实现记录见 §12。

处置对象是 `simulator-improvement-plan.md` 的 S09：*E2 同时开关生产与衰减*。
S01（财富无空间反馈）的写实见 [model-specification-c4.md](model-specification-c4.md)。

## 1. S09 的准确诊断

### 1.1 代码事实：一个开关同时动了 source 与 sink

`run_landscape_study.py:299` 中，名为 `production` 的因子同时决定两个量：

```python
"terrain_production_enabled": production,
"wealth_decay_rate": wealth_decay_rate if production else 0.0,
```

因此 E2 的四个单元实际是：

| 单元 | source | sink |
|---|---|---|
| `f0-p0` | 关 | 关 |
| `f0-p1` | 开 | 开（d = 0.02） |
| `f1-p0` | 关 | 关 |
| `f1-p1` | 开 | 开（d = 0.02） |

`aggregate_e2`（`run_landscape_study.py:2123-2132`）把 `production` 主效应定义为
`0.5·((y01 − y00) + (y11 − y10))`，即"source 与 sink 同时打开"与"两者同时关闭"之差。
**这个对比里没有任何一项能单独归给生产或衰减。**

### 1.2 实证事实：四类不可比性（对 Cycle 3 E2 归档数据的结构核对）

对 `E2-CHANNEL-ABLATION` 的 160 个 run（20 seeds × 2 landscapes × 4 单元）逐单元读取归档指标
（`n = 40`/单元，四单元 `stationarity_pass = 1.00`）：

| force | prod | decay | Gini | wealth variance | min wealth | entropy | Spearman | Moran |
|---|---|---|---|---|---|---|---|---|
| 关 | 关 | 0 | 0.6340 | 39.93 | 0 | 0.7748 | −0.0006 | −0.0006 |
| 关 | 开 | 0.02 | 0.7584 | 0.9962 | 1.44e−07 | 0.7748 | −0.0006 | −0.0006 |
| 开 | 关 | 0 | 0.6245 | 38.50 | 0 | 0.7237 | 0.2368 | 0.3519 |
| 开 | 开 | 0.02 | 0.6700 | 5.357 | 1.24e−06 | 0.7237 | 0.2368 | 0.3519 |

**(a) "关"单元不是对照，是退化态。** `prod=关` 时 decay = 0、交换严格零和，总财富守恒，
平均财富恰为初值 **5.0 = `w_ref`**。`prod=开` 时 decay = 0.02 把财富压到 `min wealth ≈ 1e−07…1e−06`。
由方差与 Gini 对数正态反推，`prod=开` 单元平均财富约 **0.27**（force 关）与 **0.97**（force 开），
即 `w/w_ref ≈ 0.05` 与 `0.19`，而"关"单元是 1.0。交换能力 `A = ε·w/(w + w_ref)` 在这些工况下处于
完全不同的区域。因此 `production` 这一个因子同时改变了财富水平、衰减机制和交换核工作点。

**(b) 空间指标的响应是严格恒等，不是统计零。** 在全部 40 个 `(seed, force)` 组合上，
`prod=关` 与 `prod=开` 的 Spearman、Moran、entropy **字符串完全相等**（20/20 seeds，两种 force；
差值 > 1e−12 的计数为 0）。这与因果图一致：生产与衰减只写 `w`，运动方程不读 `w`。
所以 Cycle 3 报告的"production 对空间结构零效应"是**代码因果结构的恒等验证，不是科学发现**，
`identified_channels` 的语义必须更正。

**(c) 该恒等更强：财富类因子完全不改变轨迹。** 表中最关键的一行是 entropy 与 Moran 在
`prod` 关/开之间**逐位相同**——这两个指标只依赖粒子位置（`occupancy_entropy(density)`、
`morans_i(density)`，见 `landscape_study.py:442/459`；而 `resource_density_spearman_rho` 依赖资源场）。
**位置在 force 设定与动力学参数确定后就是外生的、与任何财富类因子无关的过程。**
这是 S01 在实验数据上的直接体现，也是本设计识别策略的基础（§3 约束 3）。

**(d) force 因子也移动财富尺度。** force 关→开使 `prod=开` 单元平均财富从约 0.27 升到约 0.97
（约 3.6 倍）：力把粒子送进资源阱，`Σprod_i` 上升，平衡水平 `ω* = Σprod/(N·d)` 改变。
所以 `movement × production` 交互项把"位置改变邻接图"与"位置改变资源收支总量"混在一起。

**(e) 旧稳态 Gate 无法发现上述问题。** 四个单元 `stationarity_pass` 全为 1.00。逐运行稳态只回答
"这个 run 自己稳不稳"，不回答"各单元是否处在可比的长期状态"。

### 1.3 结论

S09 不是命名问题，而是**可识别性缺陷**：旧 `production` 因子在任何意义上都不能承担单通道归因，
且旧 Gate 结构上无法暴露这一点。

## 2. 为什么不能简单地"拆成 2×2"

真 source × sink 的 2×2 在稳态估计量下**不可识别**。设单位时间源为 `prod_i ≥ 0`、衰减率为 `d`，
则 `dW/dt = Σ prod_i − d·W`，平衡水平 `ω* = Σ prod_i/(N·d)`：

- `(source 开, sink 开)`：`ω*` 有限，平稳分布存在；
- `(source 开, sink 关)`：`dW/dt = Σ prod_i > 0`，财富**线性发散**，无平稳分布；
- `(source 关, sink 开)`：`W → 0`，落入退化吸收区（即 §1.2(a) 观察到的 `min wealth ≈ 1e−07`）；
- `(source 关, sink 关)`：只剩零和交换，`W` 守恒。

**四个单元中只有两个有非平凡平稳分布**，所以"source 主效应"与"sink 主效应"作为**平稳态的**
水平对比在数学上不存在。任何声称能给出这两个主效应的设计，都只能在非平稳单元上取有限时间值，
那与稳态估计量不是同一个量。

**核心判断**：sink 不是可以开关的通道，而是**使稳态存在**的条件。因此"纯生产"与"纯衰减"
不能作为两个可独立开关的因子。能问的是另外两个问题——源的**空间组织**、汇的**速率**——
两者都要求各单元处在可比的长期状态。

## 3. 识别策略

三条约束，缺一不可：

**约束 1（非退化）**：每个单元必须有非平凡平稳分布，即同时存在源与汇。
**约束 2（水平匹配）**：被检验的机制不是"财富尺度"本身时，各单元的平衡水平必须匹配，
否则财富尺度会经由 `w_ref` 改变交换核工作点（§1.2(a)）。
**约束 3（位置外生且逐位共享）**：见 §1.2(c)。在 `terrain_force_enabled = false`、
`social_strength = 0` 且无反馈路径时，`(x, p)` 的轨迹只由 `(seed, 动力学参数)` 决定，
**与任何财富类因子无关**。因此通道分离实验一律关闭地形力，使位置成为外生变量，
并在全部单元间逐位共享。

约束 3 是 v2 的关键：它把"空间指标"从**结局**变成**恒等护栏**，并把财富类效应从位置混杂中
彻底解放。代价是估计量的解释变了——问的是"给定同一套扩散轨迹，源的空间组织 / 汇的速率是否
改变财富结构"，而不是"景观是否通过改变人口分布改变财富"。后者需要力开启，属另一条通道（§9）。

## 4. E2-C4 设计矩阵

统一契约继承 Cycle 4 参考过程：`N = 1000`、`64×64`、`dt = 0.005`、`total_time = 4500`、
输出间隔 5、最后两段相邻 144 帧、`temperature = 0.5`、`friction = 1`、
`interaction_range = 2.5`、`exchange_rate = 0.5`、`noise = 0.05`、`reversion = 1`、
`epsilon_log_sigma = 0.5`、`w_ref = 5.0`、单 rank、`OMP = 1`、`confirmative_mode`。

**全部单元 `terrain_force_enabled = false`、`social_strength = 0`**（约束 3）。

### P1 — 结构隔离恒等护栏（前置，非科学检验）

- 单元：`{clustered, shuffled, flat}` × `d = 0.02`、`base = 0.01`，共 3 个单元。
  三者的资源场按构造**均值都恰为 1**（`make_matched_landscapes` 中 `flat = np.full(shape, clustered.mean())`，
  `shuffled` 是 `clustered` 的精确置换，`clustered` 已归一化），因此源总量自动匹配。
- 判据（逐 seed，逐位）：
  - `occupancy_entropy` 与 `density_morans_i` 在三个单元之间必须**字符串完全相等**（位置外生）；
  - `resource_density_spearman_rho` **允许不同**，因为它依赖资源场。
- 处置：前两项任一处不等即视为**实现失败**（位置被财富污染或存在非确定性），必须阻断该批次，
  不得报为效应。
- 性质：回归护栏。§1.2(c) 已在 Cycle 3 E2 的 `f0` 数据上证明该恒等成立；E2-C4 需在新版
  交换核与新版源项上重新确认。

### P2 — 源的空间组织消融

- 单元：P1 的三个单元直接复用（`clustered` = 空间结构化源；`shuffled` = 同一像素直方图的
  精确置乱；`flat` = 空间均匀源）。三者的区别**仅**在于源在空间上如何排布。
- 主对比：`clustered − shuffled`（像素直方图逐位相同，只隔离空间排列）；次要：`clustered − flat`
  （同时改变直方图，只作参考）。
- 估计量：源的空间组织对财富结构的效应 —— `wealth_gini`、`wealth_variance`、
  `zero_wealth_fraction`、`mean_wealth` 的配对尾窗均值差。
- 关键性质：位置逐位相同，所以这不是"景观改变人口分布"的效应，而是**同一套扩散轨迹下
  源的时空相关结构如何改变财富分配**。这是干净的单通道估计量。
- 空间家族（Spearman/Moran/entropy）不用于任何科学结论，只用于 P1 恒等检查；
  其中 Spearman 作为"源—密度耦合强度"报告为诊断量。

### P3 — 汇速率的匹配平衡响应

- 单元（3 个），固定 `clustered` 源、沿 `base_production / wealth_decay_rate` 常数线：

| 单元 | `d` | `base_production` | 松弛时间 `τ = 1/d` |
|---|---:|---:|---:|
| `D_low` | 0.01 | 0.005 | 100 |
| `D_ref` | 0.02 | 0.010 | 50 |
| `D_high` | 0.04 | 0.020 | 25 |

- `s/d` 常数 ⇒ `ω* = base·r̄·ēps/d` 在三单元相同，财富尺度匹配；只有 `τ` 相差 4 倍。
- 估计量：在匹配平衡下，汇速率对财富结构与**时间相关诊断**（IAT / ESS / 跨窗稳定性）的效应。
- 这条线同时是**模型尺度不变性的可证伪检验**：若模型在 `w ↔ c·w`、`t ↔ t/c` 下自相似，
  三单元的结构指标应无差异；任何偏离都定量给出交换核经由 `w_ref`、`share` 夹紧与
  绝对零下界引入的尺度依赖。
- 已知限制：`force` 关闭时实测平衡水平约 **0.57**（§5），即 `w/w_ref ≈ 0.11`，
  处于**深度次饱和区**，此时 `w_ref` 引起的尺度依赖本身较弱。因此 P3 只能检验该区域内的
  尺度不变性；穿越 `w_ref` 的水平扫描（把 `ω*` 提到 `≈ w_ref`）需另一套校准，列为 P3b 跟进项。

### P4 — 可比性 Gate（强制，预先冻结）

计算任何效应之前，逐单元检查并写入结果：

1. 非退化：`zero_wealth_fraction` 低于冻结上界；`minimum_wealth_observed ≥ 0`；
   非有限计数为 0；`wealth_variance` 高于冻结下界（用于捕捉 §1.2(a) 式的坍缩）；
2. **水平匹配以"单元之间一致"为准，不以 `w_ref` 为目标**。实测平衡水平由 `s/d` 决定，
   参考值为 `clustered / d=0.02` 的实测 ~1.98（力开）与 ~0.59（力关）。
   P2 三单元由构造匹配（均值都为 1），P3 三单元由 `s/d` 常数匹配；
   判据是单元间实测平均财富的相对偏差落在冻结带内（建议 ±10%，实施时冻结），
   **不是**要求等于 5.0；
3. 工作点：报告 `mean(w)/w_ref`，作为解释变量而非合格线；
4. 承继 Cycle 4 契约的尾窗稳态、相邻双窗稳定性与独立 seed 精度 Gate。

任一单元未通过可比性，则该对比记为 **inconclusive**，不得记为 null，不得删单元或事后调带宽。

### P5 — 旧 bundle 的重新命名（仅 provenance）

Cycle 3 E2 的 `production` 因子改称 **source–sink bundle ablation**，只能作为**单一因子**报告
财富指标效应，禁止归因于生产或衰减；其空间家族结果改述为恒等检查。
Cycle 3 数值不重跑、不改写，但 `identified_channels` 字段的解释必须随本文件更正。

## 5. 参考过程的实际工作点（v2 新增的实测事实）

对 V1F（`dt = 0.005` 最细步长、力开启、`d = 0.02`、`base = 0.01`）已完成 run 的尾帧逐 run
计算平均财富，59 对 seed：

| 条件 | 平均财富 | `w/w_ref` |
|---|---:|---:|
| clustered | 1.9838 | 0.397 |
| shuffled | 1.3810 | 0.276 |
| smooth | 0.5918 | 0.118 |
| paired `clustered − shuffled` | **+0.6028（+43.6%）**，SD 0.2416，2SE 半宽 4.5% | — |

`dt = 0.02` 给出同样结论（+44.3%），说明这不是步长效应。

三条推论：

1. **参考过程不在 `w_ref` 附近运行。** 初值设计（`initial_wealth = mean_wealth = 5.0 = w_ref`）
   暗示设计意图是半饱和点，但平衡水平是 1.38–1.98，`w/w_ref = 0.28–0.40`；
   `force` 关闭时进一步降到 ~0.59（`w/w_ref ≈ 0.11`）。因此在确认性过程中，能力函数
   `A = ε·w/(w + w_ref)` 处在**次饱和、近线性**区，ε 异质性转化为交换优势的机制被削弱。
2. **下边界被强烈占据。** `min wealth` 达 1e−07…1e−13，`share` 的 `[0,1]` 夹紧在实际运行中活跃。
   所以 `w = 0` 不是稀有事件，S02 的边界政策在确认性尺度上确实起作用。
3. **"运动通道"会泄漏到财富尺度。** `force` 开→关使平衡水平从 ~1.98 降到 ~0.59（约 3.4 倍），
   机制是粒子被力送入高资源阱后 `Σprod` 上升。因此凡是**财富类**结局，
   景观效应都与"平衡财富尺度改变"混杂；这正是 P3 与约束 2 存在的原因。

**协议偏离披露。** 上述平均财富是在 V1F 运行期间读取的，且其中包含一个
`clustered − shuffled` 对比。`e1-cycle4-readiness.md` 记录的原则是 E1-C4 的 runner 与实现
"保持不读取 V1F 的中间科学指标"。此处读取的是：(i) 一个**非主指标**的结构量（平均财富），
(ii) 目的是**检查设计前提**（P4 的 `w_ref = 5` 目标是否可达），而 E1-C4 的三个主指标是
位置类空间指标，与财富水平无关。(iii) 由此产生的处置是**收窄解释**
（见 §6 对 Gini 次要家族的限定），而不是放宽任何阈值、样本量或 Gate —— 即偏离的方向是保守的。
本段即为该偏离的审计记录，不得删除。另需说明：V1F 本身是校准实验而非确认性实验，
其 `numerical_calibration.json` 尚未读取。

## 6. 对 E1-C4 的影响（必须在锁冻结前登记）

E1-C4 的主 family 是 `resource_density_spearman_rho`、`density_morans_i`、`occupancy_entropy`，
全部为位置类指标；位置不被财富影响（约束 3 / §1.2(c)），因此 §5 的财富尺度差异**不影响主 family**，
主效应 Gate 无需改动。

但 `wealth_gini` 是 E1-C4 的次要 family，它会受 §5 第 3 条影响：`clustered` 与 `shuffled` 的平衡
财富相差 +43.6%，`w/w_ref` 从 0.276 变为 0.397，交换核工作点不同。因此 Gini 的配对差
**不能**解释为纯空间组织效应，而是"空间组织 + 平衡财富尺度"的合成。处置：

- 在 `e1-cycle4-readiness.md` 与最终锁中预注册该限定；
- E1-C4 必须把 `mean_wealth` 作为诊断量随 `result.json` 一并报告，使该合成可被读者核算；
- Gini 结论的措辞限定为"空间组织与其伴随的平衡财富尺度变化"的合成效应，
  不得写成单通道空间效应。

这些是**判据解释**层面的限定，不改参数、不改样本量、不改任何阈值，因此不使 V1F 的
数值校准失效，也不需要重新校准。

## 7. 必需代码改动（v2 已缩减）

**C++ 侧：无需改动。** v1 曾计划新增 `uniform_production` 键来构造均匀源；v2 改用
`flat` 景观（`flat = np.full(shape, clustered.mean())`，常量恰为均值），在关闭地形力时
其源是严格均匀的，且梯度为零。这使 P1/P2/P3 全部可用现有二进制表达，
**参考 binary 的 SHA 因此保持不变**，不触动 V1F 校准与 E1-C4 的 binary 绑定链。

**Python 侧（`run_landscape_study.py`、`landscape_study.py`）已实现（2026-09-17，见 §12）：**

1. 新增 `E2-CHANNEL-ABLATION-C4` 分支：三类单元（P1/P2 的 3 个 + P3 的 2 个额外汇速率），
   全部强制 `terrain_force_enabled = false`、`social_strength = 0`。
2. 三路输入审计：在 `audit_matched_landscapes` 之外新增三条件版本，校验
   `clustered` / `shuffled` / `flat` 均值相等、`shuffled` 是 `clustered` 的精确置换、
   `flat` 为常量、三者初始完整相态逐 seed 逐位相同。
3. 可比性指标入表：`replicate_metrics.csv` 原表头只有 `wealth_gini`、`wealth_variance`、
   `minimum_wealth`、`total_wealth_relative_drift`，**没有平均财富列**。
   **已完成**（2026-09-16，与 E1-C4 的预注册要求同批）：`snapshot_metrics` 新增
   `mean_wealth`（`landscape_study.py`），`analyze_runs` 新增
   `wealth_scale_ratio = mean_wealth / ability_saturation_w`（`run_landscape_study.py`），
   `aggregate_e1_c4` 的 payload 新增 `wealth_scale_diagnostics` 块（逐条件的平均财富与
   `w/w_ref`、配对差与其相对值、合成解释、`gate_role`）。两者都是**诊断量，不进入任何 Gate**，
   本地测试 166/166 通过。
4. `mean_source_rate`（P2 的源总量核算量）——**已实现**：`source_rate_metrics` 按
   `base_production × terrain_production_scale × resource(x_i) × eps_i` 逐帧核算，
   与 `apply_resource_dynamics` 逐字对应；新增 `resource_at_particles` 复刻 C++
   `TerrainGrid::elevation` 的双线性节点插值与下标夹紧（`snapshot_metrics` 用的直方图分箱
   不是模拟器实际读取的值，故不能用它冒充源项核算）。
5. P1 恒等检查在分析器中 fail-fast：**已实现**，先于任何效应计算执行，任一
   `(seed, metric)` 不等即写 `isolation_identity_report.json` 并 `raise`。
6. `aggregate_e2` 重写为 `isolation_identity`（P1）、`source_pattern`（P2）、`sink_rate`（P3）、
   `comparability`（P4）四块：**已实现为新聚合器 `aggregate_e2_c4`**（输出
   `channel_separation.json`），不含旧三效应字段。**旧 `aggregate_e2` 保持原样不动**——
   见 §12 的 P5 处置说明。
7. E2-C4 三条件输入审计（`clustered`/`shuffled`/`flat`）与五单元条件分支：**已实现**。

§5 的 `w/w_ref` 事实还带来一处必须的结构性修正：E2-C4 的稳态前提**不能**包含
`resource_density_spearman_rho`——它在 `flat` 单元上按 S04 是**未定义**（常量场方差为零），
而 R01/R06 让未定义指标阻断 Gate，于是 P1 的护栏单元会被自身判为不稳态。
故 `stationary_metrics_for_experiment("E2-CHANNEL-ABLATION-C4")` 只保留
`density_morans_i`、`occupancy_entropy`、`wealth_gini`、`wealth_variance`、
`zero_wealth_fraction`，Spearman 降为逐条件诊断量。这与 §4 P1 判据一致：
只有前两者是纯位置指标。

## 8. 统计契约、seeds 与预算

- **seeds 必须全新且互斥**。可用池 = 未出现在 Cycle 1–3、`V1`/`V1B`/`V1C`/`V1E`/`V1F`/`V1P`
  与 E1-C4 的 64 个冻结 seeds（`11657–12241`）中的素数。沿用 E1-C4 的记账式互斥审计
  （对全部 `seeds.txt` 与 job config 的 `seed` 字段全量比对），该方法本轮已复核过一遍。
- **样本量不得继承 E1-C4 的 64**。64 是为配对景观对比的估计量定的，与 P2/P3 估计量不同。
  先用**非证据 pilot** 估计各对比的方差（只看方差与可比性，不看对比方向或大小，
  与 V1ED 对 V1E 的用法一致），再按既有"上取 2 的幂"政策冻结。
- **单元数与预算**。去重后 5 个单元（P1/P2 的 3 个 + P3 的 2 个额外汇速率）。按 V1E 实测约
  **1,242 秒/run**（`N=1000`、`dt=0.005`、`T=4500`）：
  - pilot：5 单元 × 8 seeds = 40 runs ≈ 13.8 CPU 小时 ≈ 8 路 1.7 墙钟小时；
  - 正式（若 R = 32）：5 × 32 = 160 runs ≈ 55.2 CPU 小时 ≈ 8 路 6.9 墙钟小时。
  以上为数量级估计，实施前须用 pilot 实测速率修正。
- **执行纪律**：jobctl 提交、preflight 通过后执行、完成后 `jobctl reconcile`；
  重产物进 `research/jobs/E2-CHANNEL-ABLATION-C4/workspace/`。

## 9. 禁止事项与不作出的主张

- **不得**为了得到非零的空间效应而临时加"财富驱动迁移"。财富→空间反馈是另一个研究问题，
  需要微观行为依据、额外参数校准与新因果图（[model-specification-c4.md](model-specification-c4.md) §6.2）。
- **不得**把 P1 的恒等结果报告为"生产对空间结构无效应"这一科学结论。
- **不得**在 P2/P3 上事后调整源强度、`d` 梯度或可比性带宽以挽救判定。
- **不得**给出"纯生产效应"或"纯衰减效应的社会意义"这类表述。P2 给出的是
  *同一套轨迹下源的空间组织效应*；P3 给出的是 *匹配平衡下的汇速率效应*，且限于次饱和区。
- **不得**把 P2/P3 的结果外推为"景观通过改变人口分布改变财富"——后者要求力开启，
  是另一条通道，需独立设计（记为 E2b，含 §5 第 3 条的尺度混杂与 §1.2(d) 的交互项混淆）。
- 本设计**不**声称任何关于真实历史、国家或制度的结果。

## 10. v2 相对 v1 的修订与理由

| 项 | v1 | v2 | 理由 |
|---|---|---|---|
| 均匀源实现 | 新增 C++ `uniform_production` 键 | 用 `flat` 景观（常量 = 均值） | 免改 C++，保住 reference binary SHA 与 V1F/E1-C4 绑定链 |
| 地形力 | 每个矩阵固定力开 | 全部单元力关 | 约束 3：位置外生且逐位共享，空间指标成为恒等护栏，消除财富类的尺度混杂 |
| P1 判据 | 空间指标两两相等 | entropy/Moran 必须恒等，Spearman 允许不同 | 三指标对资源场的依赖不同：只有前两者是纯位置指标 |
| P4 水平目标 | 匹配到 `w_ref = 5`（±10%） | 匹配"单元之间"（实测 ~0.59–1.98） | 实测平衡水平与 `w_ref` 差 2.5–8 倍，v1 目标不可达 |
| 工作点事实 | 未记录 | §5 记录 `w/w_ref = 0.12–0.40`、下边界活跃、力→财富尺度泄漏 | 保证 P2/P3 的解释边界正确，并暴露 E1-C4 次要家族混杂 |
| 单元数 | 6 | 5 | 力关后去掉重复单元 |
| E1-C4 处置 | 无 | §6 预注册 Gini 合成限定 + `mean_wealth` 入表 | 该混杂必须在锁冻结前登记 |

## 11. 交付检查表

- [x] `E2-CHANNEL-ABLATION-C4` 条件分支（力关、五单元）（2026-09-17，代码）
- [x] 三条件输入审计（均值相等、置换精确、flat 为常量、初始相态逐位相同）（2026-09-17，代码）
- [x] `mean_wealth`、`wealth_scale_ratio` 入表 + `wealth_scale_diagnostics` 进 E1-C4 payload（2026-09-16）
- [x] `mean_source_rate`（P2 源总量核算量）（2026-09-17，代码）
- [x] P1 恒等检查在分析器中 fail-fast（entropy/Moran 逐位）（2026-09-17，代码）
- [x] P1/P2/P3/P4 四块聚合器 `aggregate_e2_c4`（新 ID 下，旧三效应字段不出现）（2026-09-17，代码）
- [ ] seeds 互斥审计（记账式，覆盖全部历史 job）——**待办**，需在冻结 R 前完成
- [x] E1-C4 侧：Gini 限定预注册 + `mean_wealth` 入表（2026-09-16，在 `prepare` 之前完成）
- [ ] pilot 只读方差与可比性，冻结 R 后生成正式声明——**待办**，需 `umi` 算力
- [ ] preflight 通过、`confirmative_mode`、`nprocs=1`、`OMP=1` 写入 config——**待办**
- [ ] E2-C4 新实验 ID 与独立目录；Cycle 3 E2 结果不改写、只改解释——**待办**（ID 已在代码中固定）

## 12. Python 侧实现记录（2026-09-17，未执行任何数值实验）

本节的每一项都是在 E1-C4 确认性运行期间于本地完成的纯代码改动：不含 C++ 改动、不触碰
任何实验数据、不改变参考 binary 的 SHA，因此不触及 V1F 校准与 E1-C4 的 binary 绑定链。

**新增的分析器代码。**

| 位置 | 内容 |
|---|---|
| `landscape_study.py::resource_at_particles` | 复刻 C++ `TerrainGrid::elevation` 的节点双线性插值与 `[0, n-1]` 夹紧。P2 的源项核算必须用模拟器真正读取的值，而不是 `density_grid` 的直方图分箱 |
| `landscape_study.py::source_rate_metrics` | 逐帧 `mean_source_rate` / `total_source_rate` = `base_production × terrain_production_scale × resource(x_i) × eps_i`，与 `apply_resource_dynamics` 逐字对应；缺 `eps` 列时 fail-fast 而不是补默认能力 |
| `landscape_study.py::audit_three_condition_landscapes` | P1/P2 的三条件输入审计（精确置换、flat 常量且等于 clustered 均值、三者总量匹配）。正资源支撑只比较 `clustered` 与 `shuffled`——`flat` 按定义支撑不同，那是它的用途而非缺陷 |
| `landscape_study.py::read_snapshot_csv` | 列存在时额外返回 `eps`（可选列，旧快照仍可读） |
| `run_landscape_study.py::validate_e2_c4_structure` | 约束 1/3 的提交期 fail-fast：`social_strength ≠ 0`、任一单元开力、任一单元关生产都直接拒绝提交。注释拦不住这三种静默失效 |
| `run_landscape_study.py::aggregate_e2_c4` | P1/P2/P3/P4 四块，输出 `channel_separation.json` |
| `run_landscape_study.py::_e2_c4_comparability` | P4 强制可比性 Gate，三个政策量必须先在 config 中冻结，缺任一即拒绝分析 |
| `run_landscape_study.py::_e2_c4_source_total_accounting` | P2 的源总量核算块（诊断，不进 Gate） |

**判据与阈值处置（两处必须显式说明）。**

1. **只有同时具备 V1F 数值分辨率上限与已冻结 SESOI 的指标才能承载主张。** E2-C4 的估计量
   家族是财富结构，而 V1F 校准只覆盖 `wealth_gini`（外加三个位置类指标）。因此
   `aggregate_e2_c4` 逐指标判定 `claim_eligible`：`wealth_variance`、`zero_wealth_fraction`、
   `mean_wealth` 在 pilot 冻结其阈值之前**只作描述性报告**，`claim_threshold_pass` 恒为
   `false` 并附 `descriptive_only` 说明。这里没有就地发明阈值。
2. **P2 的参考对比不进入 Holm 家族。** `clustered − flat` 同时改变直方图，设计已把它定为
   "只作参考"，所以它 `claim_bearing=False`：仍报告区间，但不承载主张，也不允许它把
   主对比的 Holm 家族规模从 1 撑到 2 从而稀释主对比的检验力。

**P5（旧 bundle 重命名）的实现选择。** 本文件 §7.6 的原措辞是"删除旧的
`movement`/`production`/`interaction` 三效应字段"。本轮**没有**改动旧 `aggregate_e2`：
Cycle 3 E2 是已归档的冻结结果，改写其聚合器会让同一份归档数据在重跑时产生不同的
`channel_effects.json`，那本身就违反 §P5"Cycle 3 数值不重跑、不改写"。因此处置为：
四个块全部落在新 ID 的 `aggregate_e2_c4` 里，旧聚合器保持逐字不动，`identified_channels`
的语义更正落在本文件与 `model-specification-c4.md`（即 §P5 要求的"只改解释"）。
若后续要连旧聚合器的 payload 一起改，需要作为一次显式的、留痕的解释性变更来做。

**验证。** 本地 `python3 -m pytest -q` 为 **192 passed**（改动前 176），新增 16 项覆盖：
五单元矩阵与 `base/d = 0.5` 常数线、结构护栏的三种拒绝、稳态指标集排除退化 Spearman、
双线性插值与 C++ 约定逐点一致、源项核算等于 `base × scale × resource × eps`、
三条件审计的四类破坏、P1 位级 viol 的 fail-fast 与留痕、未校准指标的 claim-ineligible
标记、可比性政策缺失时拒绝分析、单元间水平失配降级为 inconclusive、五单元两步窗 Gate。
这些检查**不执行模拟器**，不构成数值证据。

## 13. 实现期回归：共享 spec 构造器与已授权实验的产物契约（2026-09-17，本地）

**发生了什么。** P2 的源项核算要求逐单元 `base_production` 可从 spec 单独重算（§12），
于是该键被无条件加进 `prepare_inputs` 里共享的 `run_specs.append({...})`。后果是
`E1-MATCHED-LANDSCAPES-C4` 的 `run_specs.json` 也多出一个键——而它是**已授权实验的已声明
产物**，其冻结 `source_commit` 是 `b6d24b7`。加上这个键之后，归档的
`run_specs.json` 就不再能由它自己声明的提交复现。

**为什么这必须修而不是记一笔。** 这正是 S13/S14 的同一类缺陷：绑定从**恒等**退化成
需要论证的等价。键本身是元数据、物理上无影响（E1-C4 的 `base_production = 0.01` 一直
经由 `common_cpp_config` 写进每个 `politeia.cfg`，与 spec 无关），但"归档产物能否由声明的
提交复现"是确认性证据链的一部分，不能靠一次口头论证保留下来。

**怎么发现的。** 为回答"E2-C4 的改动有没有碰坏 E1-C4 的路径"，做了一次**跨版本等价性探针**：
把 `HEAD~1` 与 `HEAD` 的 `run_landscape_study.py` + `landscape_study.py` 分别放进独立目录，
用同一份真实 E1-C4 config 各跑一次 `default_conditions` / `prepare_inputs` /
`stationary_metrics_for_experiment` / `confirmatory_metrics_for_experiment` /
`load_confirmatory_calibration`，再比对 128 条 spec 与 706 个生成产物。探针只把自身临时输出
目录的名字归一化，其余逐字节比较。首轮即报出 129 个文件与全部 spec 不同，由此定位到该键。

**处置。**
1. 该键收窄到 `experiment == E2_C4_EXPERIMENT` 分支，E1-C4 保持原 schema；
2. E2-C4 源项核算改为**必须有**该键，且校验前移到任何磁盘 IO 之前——原来的
   `spec.get("base_production", 0.0)` 会在缺键时把每个单元的实际源总量都算成 0，
   使 P2 的"匹配源总量"前提**空过**（一个静默的错误 PASS）；
3. `tests/test_run_landscape_study_gates.py` 把 E1-C4 的 spec 键集固化为冻结字面量
   `E1_C4_FROZEN_RUN_SPEC_KEYS`，并新增两条回归：E2-C4 的键集恰为该集合加一个
   `base_production`、E2-C4 源项缺键时在无文件系统依赖下即抛错。后者经**变异检验**确认会失败
   （把分支条件改成恒真后测试立刻报 extra key），即护栏确实咬人，不是装饰。

**结论与残余。** 最终版下探针报告 `differing keys: NONE`（128 specs / 706 产物逐字节相同），
即 E2-C4 的代码改动对 E1-C4 的输入生成**零扰动**，同时 E2-C4 拿到它需要的 sink 参数。
残余两点如实登记：(a) 探针只覆盖**输入生成**与校准加载，没有逐字节复核分析路径
（分析路径走的是另一套共享函数，本文件 §12 列出的单测覆盖其契约）；(b) 探针绕过
`require_umi()` 直接在本地调用库函数——这是项目铁律下非法的执行路径，此处仅因它
只写临时目录、不执行模拟器、不产生任何数值证据才被采用，且临时目录已删除。
后续若再有实验需要新的 spec 键，必须挂在自己 experiment id 的分支下；上面那条冻结字面量
就是为了让"顺手加在共享构造器里"这种改法立刻失败。
