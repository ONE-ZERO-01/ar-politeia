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
- 估计量：源的空间组织对财富结构的效应 —— `wealth_gini`、`wealth_variance` 的配对尾窗
  均值差。家族里另两个指标**不承担效应断言**，但都由同一段代码算出并随结果报告：
  - `zero_wealth_fraction`：承担 P4 的**非退化护栏**。实测在本参考体制下退化（全部 960 个
    run 只有 4 个取值、`clustered − shuffled` 的配对差在三个 dt 上恒为 0），做成估计量会产出
    空洞的 null。详见 §15.2 与 §15.3。
  - `mean_wealth`：承担**水平审计**而非效应断言。P4 第 2 条要求三单元实测平均财富落在
    ±10% 带内（否则该对比记 inconclusive），而 §5 力开实测的 `clustered − shuffled` 为
    +43.6%；若力关同向，则"估计 `mean_wealth`"等于宣称一个设计已声明**必须不存在**的差异。
    其配对差照常计算并报告（`claim_eligible = false`，理由码
    `missing_numerical_resolution_limit`），供读者核算 P4 与 §6 的财富尺度通道。详见 §15.5。
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
   判据是单元间实测平均财富的相对偏差落在冻结带内 **±10%**（2026-09-17 定夺并冻结，
   见 §15.5），**不是**要求等于 5.0；
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

- 在 `e1-cycle4-readiness.md` 中于锁冻结前预注册该限定（2026-09-16，已完成）；锁本身通过
  `design_contract.secondary_family = ["wealth_gini"]` 命名该 family，并通过
  `analysis_commit = b6d24b76…` 绑定释放该限定文本的分析器（`_wealth_scale_diagnostics()`，
  `gate_role = "diagnostic only; never enters a gate"`）；
- E1-C4 必须把 `mean_wealth` 作为诊断量随 `result.json` 一并报告，使该合成可被读者核算；
- Gini 结论的措辞限定为"空间组织与其伴随的平衡财富尺度变化"的合成效应，
  不得写成单通道空间效应。

> **复核修正（2026-09-17）。** 本节原文写作"在 `e1-cycle4-readiness.md` **与最终锁中**预注册该限定"，
> 这与锁的 schema 不符：`parameter_lock.cycle4.json` 只能表达 family 名（`secondary_family`）与
> `analysis_commit` 绑定，无法承载限定文本。该限定实际由两条具约束力的路径固定：冻结前登记的
> `e1-cycle4-readiness.md`（2026-09-16），以及锁 `analysis_commit = b6d24b76…` 中
> `_wealth_scale_diagnostics()` 释放的 `interpretation` / `gate_role` 字段（已随
> `research/jobs/E1-MATCHED-LANDSCAPES-C4/paired_effects.json` 归档入 git）。这是**措辞过度承诺**，
> 不是证据完整性缺口；`wealth_gini` 亦非显著（CI 含 0），无结论依赖它。
> **锁不得补写**：E1-C4 的 `config.json`、`result.json`、`parameter_lock_audit` 与归档 manifest
> 均绑定锁 SHA `bee66e70…`，事后改动会切断该绑定链，且落在 `amendment_policy` 所禁的事后知情变更内。

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

- **seeds 必须全新且互斥**。审计已实现为 `seeds-audit` 子命令
  （`research/src/experiments/prepare_cycle4_confirmation.py`），扫描**全部** `research/jobs/*/`
  的三条通道：`seeds.txt`、job JSON 的**顶层** `seeds`/`seed` 字段，以及
  `result.json`/`manifest.json` 运行标识里的 `seed-<n>`。前两条是"抽了什么"的声明，按**消耗**
  记账；嵌套块按**引用**记账。运行标识默认也按消耗记账，方向刻意 fail-closed（多算只会产生
  假重叠并报错逼人声明，少算会静默掩盖真实复用），只有显式登记在 `SEED_REFERENCE_JOBS` 的
  重分析 job 才把其标识改判为引用——且必须被该 job config 里的 `source_experiment` 佐证。
  未登记的跨 job 复用**直接报错**；新实验故意不在 `SEED_REUSE_COMPONENTS` 内，因此 E2-C4
  一旦撞用旧 seed 会在提交前失败。
- **实测台账（2026-09-17）**：全库 28 个 job 共 **211 个不同 seed**（范围 101–12241）、
  **91 个重叠组**，归属 **3 个 component**，每条的授权都带**可机器校验的 basis**：
  B0 三连为 `same_experiment_reexecution`（三者 `experiment_id` 全同）、V1F↔V1G 为
  `declared_paired_rerun`（引文文件存在且仍含声明文本）、E0/E1/E2 Cycle 1–3 为
  `historical_collision`（其 24 个共享 seed 与 8 个 evidence job 的 174 个 seed **不相交**，
  实测全部 ≤5519 vs 最小 6007）。两处**历史记账缺陷**已登记、不追溯修改：
  `E0-NUMERICS` 与 `E1-MATCHED-LANDSCAPES` 撞用 seed `1103`；三个冻结 seed 非素数
  —— `6407`、`6503`（V1）与 `9071`（V1C）。素数性已对照代码查实：`random_seed` 只作为
  `mt19937_64` 初始状态与 rank 派生偏移的基点，**无任何依赖基点素性的逻辑**，仓库里的素数
  是**偏移量**；故唯一可证成的硬要求是唯一性，素数性对基点无功能作用且选取理由无记载。
- **可用池的上界尚未冻结，这是 R 冻结前必须补的显式决策**。本节只说了"未出现的素数"，未给窗口；
  审计的 `--pool-min/--pool-max` 刻意**没有默认值**，以免该边界被隐式决定。
  **判据、候选与建议见 [e2-cycle4-seed-pool-decision.md](e2-cycle4-seed-pool-decision.md)**
  （该文只列候选、不替 lock 定值）。要点：窗口下界须 > 12241（历史 seed 的最大值）；
  宽度须远小于最小 rank 派生偏移 `999983`（多 rank 时的别名约束，`nprocs=1` 下自动成立）；
  个数须够 pilot 的 8 个与正式的 R 个。建议 `12300–13000`（77 个未用素数，覆盖至 R=64）。
  **pilot 与正式各用独立且不相交的 seed 子集**，依据是 `V1P`（用 `6007`）与 `V1`（`6101…6503`）
  的先例——本项目 pilot 跑在自己的 seed 上，不复用正式运行的 seed。
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
- [x] seeds 互斥审计（记账式，覆盖全部历史 job）（2026-09-17，`seeds-audit` 子命令 + 36 项测试；台账 211 seeds / 28 jobs / 91 重叠组 / 3 component，每条带可机器校验的 basis；重分析 job 的标识按引用记账，见 §8）
- [ ] 冻结可用池窗口（`--pool-min/--pool-max` 无默认值，须与 R 一同写入 lock）——**待办**，判据与候选见 [e2-cycle4-seed-pool-decision.md](e2-cycle4-seed-pool-decision.md)；阻塞 pilot（pilot 自身即需 8 个全新 seed）；窗口已定为 `12300–13000`，待写入 lock
- [x] **E2-C4 推断射程选择——已定 (B′)，见 §15**：校准扩展到 `wealth_variance`（可行性已逐位验证：以 V1F 自己的 `_weak_bound` 重算复现其四个上限、0 处浮点不匹配、无需模拟器时间；信号约为其数值上限的 64 倍）。**`zero_wealth_fraction` 退出估计量家族、保留为 P4 护栏**——实测在参考体制下退化（960 run 仅 4 个取值、clustered/dt=0.005 上 64/64 为 0 且 sd=0、`clustered − shuffled` 配对差在三个 dt 上恒为 0、上限测出 0.0）。**`mean_wealth` 定为水平审计量、不做校准扩展**（三条理由见 §15.5；它从未被 V1F 记过，重取需 ≈28 GB 快照，而它的水平带与"估计它的效应"直接冲突）。新增两条机械判据：claim-eligible 的指标除数值上限与 SESOI 外**还须具有非零方差**（同时挡住"把退化指标当成精度极好"与"把没有差异当成结论"）；以及**设计↔代码一致性控制**（文档的原因码词表与 P2 叙述必须与代码一致，防 §14 类错误重现）。**P4 水平带冻结为 ±10%**（§4 P4 第 2 条），故 P2 存在一个先验可失败的 Gate，由 pilot 提前回答
- [x] **V1H（校准扩展）：已完成并入库**（2026-09-18，见 §16）——只从 V1F 保留的 `replicate_metrics.csv` 重分析；**字段级忠实性检验在 `umi` 执行并通过**（四个旧上限逐位重现，`field_mismatches = 0`），产物级检查（四个旧上限与已入库 `numerical_calibration.json` 逐位相等）在本地由 `record-calibration-extension` 执行并通过。扩展结果为 `wealth_variance: 0.056828569227561854`，无 ceiling；入库 `research/jobs/V1H-CALIBRATION-EXTENSION-C4/{numerical_calibration_extended,result,manifest}.json`
- [x] E1-C4 侧：Gini 限定预注册（`e1-cycle4-readiness.md`，2026-09-16，`prepare` 之前）+ `mean_wealth`/`wealth_scale_ratio` 入表 + 经 `analysis_commit` 绑定释放（2026-09-17 复核确认；见 §6 复核修正）
- [ ] pilot 只读方差与可比性，冻结 R 后生成正式声明——**待办**，需 `umi` 算力；**pilot 预注册已写**（[e2-cycle4-pilot-design.md](e2-cycle4-pilot-design.md)：5 单元 × 窗口内最小 8 个未用素数 `12301/12323/12329/12343/12347/12373/12377/12379`、协议常量逐项 pin 到 E1-C4 已入库 config、binary 绑定到锁里的 reference sha、**护栏量报告水平而估计量只报告配对差 SD**、R 由 §4 的规则在 Δ 冻结后机械求出）。**提交前须关闭三项**（SESOI、两个 comparability 政策量），判据与候选见 [e2-cycle4-sesoi-decision.md](e2-cycle4-sesoi-decision.md)
- [ ] E2-C4 的 `scientific_sesoi` 与两个 comparability 政策量——**待定夺**，判据简报已备（[e2-cycle4-sesoi-decision.md](e2-cycle4-sesoi-decision.md)，只列候选不替 lock 定值）。要点：阈值按**指标**而非按对比设，P2 与 P3 共用同一个 Δ；`wealth_variance` 的数值上限 `0.0568` 是硬地板，Δ 必须显著大于它才有约束力；**方差对尺度敏感而 Gini 不敏感**，故 P4 的 ±10% 水平带推出 `(1.10)²−1 = 0.21` 这一"纯水平漂移能造成的最大相对方差变化"，于是**以相对比例 ρ 表示的 Δ 必须 ρ > 0.21**——而该指标唯一的既有阈值约定恰好是 ρ = 0.2，落在其下，直接沿用会对水平漂移失效。R 由 `wealth_variance` 决定（力开体制下 V1ED 已显示它是限制指标：61 → 64，而 `wealth_gini` 只需 3），故 Δ 的选择有真实的算力后果（ρ = 0.25 与 0.50 之间 R 可差 4 倍）
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
   `mean_wealth` **只作描述性报告**，`claim_threshold_pass` 恒为 `false` 并附
   `descriptive_only` 说明。这里没有就地发明阈值。
   **⚠️ 更正（2026-09-17，见 §14）：此句原写"在 pilot 冻结其阈值之前只作描述性报告"，
   隐含 pilot 之后即可承载主张。该隐含是错的** —— `claim_eligible` 是
   `metric in numerical_resolution_limits AND metric in scientific_sesoi` 的合取，
   而 pilot 只能补上 SESOI 那一半；数值上限来自 V1F 校准，pilot 无法提供。
   详情与修法见 §14。
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

## 14. pilot 无法解锁其余财富指标（2026-09-17 复核发现，影响 E2-C4 的推断射程）

**结论：以当前校准，E2-C4 能承载主张的指标只有 `wealth_gini` 一个**，P2/P3 名义上的其余三个
财富指标（`wealth_variance`、`zero_wealth_fraction`、`mean_wealth`）**不可能因 pilot 而变得
可承载主张**。这与 §12 第 1 条及代码注释原先的隐含不符，在此更正。

### 14.1 判定式是合取，两半都要

`run_landscape_study.py:2709`：

```python
claim_eligible = {
    metric: bool(metric in numerical_limits and metric in scientific_sesoi)
    for metric in E2_C4_EFFECT_METRICS
}
```

- `numerical_limits = calibration.get("numerical_resolution_limits", {})`，来自
  `load_e2_c4_calibration` 加载的 V1F 校准，并经 `_load_checksum_bound_calibration`
  以 SHA 绑定，不能手改；
- `scientific_sesoi = config.get("scientific_sesoi", {})`，可由 config 冻结。

pilot 能影响后者，**不能**影响前者。

### 14.2 实测：V1F 校准只覆盖 4 个指标

`research/jobs/V1F-NONFLAT-CALIBRATION-C4/numerical_calibration.json` 的
`numerical_resolution_limits` 恰有 4 个键：

| 指标 | 上限 |
|---|---|
| `resource_density_spearman_rho` | 0.004590 |
| `density_morans_i` | 0.003259 |
| `occupancy_entropy` | 0.000995 |
| `wealth_gini` | 0.001441 |

`wealth_variance`、`zero_wealth_fraction`、`mean_wealth` 在该文件全文中的出现次数为
**0 / 0 / 0** —— V1F 从未计算过它们。其 `scope` 自述为
"non-flat weak timestep convergence plus deterministic exchange-order sensitivity"，
`threshold_policy` 亦明写"Resolution limits bound numerical error only. Scientific
relevance thresholds for E1 must be frozen separately"。

因此 `claim_eligible` 对这三个指标恒为 `false`，与 pilot 是否冻结 SESOI 无关。
E2-C4 的 **P2 主对比与 P3 梯度的可承载主张部分实际只有 `wealth_gini`**，
Holm 家族规模也相应为 1（`clustered − flat` 参考对比按 §12 第 2 条已排除在外）。

这不是代码缺陷——判定式本身是正确的、fail-closed 的；错的是**叙述**：让读者以为 pilot 之后
这三个指标就能承载主张。

### 14.3 修法很便宜，但**不能就地改 V1F 的校准文件**

两个已查实的事实使补救代价远低于预期：

1. **指标已经算过。** `landscape_study.py::snapshot_metrics` 的返回字典**已包含**
   `wealth_variance`、`mean_wealth`、`zero_wealth_fraction`（第 635/641/642 行）。
   所以扩展覆盖不是新增计算逻辑，只是把这些指标纳入校准的指标列表。
2. **快照完整保留。** UMI 上 V1F 的 workspace 有 **960 个 run 目录、864,960 个
   `snap_*.csv`**，而 `run_v1_calibration.py` 正是读取 `snap_*.csv` 后调用
   `snapshot_metrics`。所以扩展覆盖是**对已保留快照的重分析**，不是重跑模拟器：
   **无 C++ 改动、无 binary SHA 改动**。

**但绝对不能编辑 V1F 的 `numerical_calibration.json`。** E1-C4 的 config 以
`numerical_calibration_sha256 = 143007f7…` 绑定了它，且 `_load_checksum_bound_calibration`
会逐次校验；就地改文件会切断 E1-C4 已归档的证据链，与"不得补写参数锁"是同一类错误。
正确做法是产出一个**新的**校准产物（例如一次 V1H 式的"指标覆盖扩展"重分析，生成自己的
`numerical_calibration` 文件），由 E2-C4 的 lock 引用它，V1F 原文件保持逐字不动。

### 14.4 需要研究者定夺的射程选择

| 选项 | 内容 | 代价 | 后果 |
|---|---|---|---|
| (A) 接受单指标射程 | E2-C4 只以 `wealth_gini` 承载主张，其余三个指标在结果中明确标为描述性 | 0 | 结论更窄但完全可证；**必须先更正 §8/§12 的叙述**，否则预注册文本与代码行为不符 |
| (B) 扩展校准覆盖 | 对 V1F 保留快照做一次 V1H 式重分析，为新产物冻结三个指标的数值上限；pilot 再冻结其 SESOI | 重分析（无模拟器时间），加一轮产物与 lock 更新 | 四个指标全部可承载主张，P2/P3 的射程恢复到设计本意。**实测后收窄为 (B′)，见 §15**：只扩展 `wealth_variance` 与 `mean_wealth`；`zero_wealth_fraction` 实测退化，退出估计量家族 |

**关于顺序的诚实说明。** pilot 的**原始 run 不是**一次性消耗品：8 seeds × 5 单元的逐 seed
指标在 (A)/(B) 两种选项下都可复用（SESOI 与 R 都是对同一批配对差做的推断），
所以先跑 pilot 再改选选项**不会**浪费算力。真正随选项变化的是两件事：

- pilot 的**分析产物契约**：pilot 模式必须拒绝输出效应（§8 的"只看方差与可比性"），
  而在 (B) 下它还要为另外三个指标产出可冻结的 SESOI 依据；
- **E2-C4 lock 的措辞**：声明哪些指标可承载主张、Holm 家族规模是 1 还是 4。

因此这里不存在硬阻塞，只有"先定夺可少改一次预注册文本与一次 pilot 分析器"的便利。
但 (B) 若采用，其校准扩展重分析应在 **E2-C4 lock 冻结之前**完成——lock 要引用那个新产物
的 SHA，事后补写等于补写锁。

## 15. (B) 的可行性已验证，但射程须收窄（2026-09-17 实测复核）

选定 (B) 后先做了两项**只读**实测（不跑模拟器、不写任何产物），结论改变了 (B) 的形状。

### 15.1 复现是逐位精确的，故重分析可行

V1F 的 workspace 保留完整：`run_specs.json`（960 runs）、`replicate_metrics.csv`（960 行 ×
62 列）、以及全部 run 目录与快照。以 V1F 自己的 `_weak_bound` 原语、从该 CSV 重算各层的
`coarse_vs_fine` 与 `fine_vs_finest`，与 `numerical_calibration.json` 逐字段比对：

**0 处不匹配**（三个 landscape × 全部指标 × 两层的全部浮点字段），且四个上限完全重现：

| 指标 | 重算值 | V1F 冻结值 |
|---|---|---|
| `resource_density_spearman_rho` | 0.004589992673223881 | 0.004589992673223881 |
| `density_morans_i` | 0.0032587589468579255 | 0.0032587589468579255 |
| `occupancy_entropy` | 0.0009948207537034592 | 0.0009948207537034592 |
| `wealth_gini` | 0.0014407792015185721 | 0.0014407792015185721 |

所以扩展覆盖**不需要模拟器时间**，而且"新产物必须逐位重现 V1F 的四个上限"是一条可以
机械校验的**忠实性检验**（见 §15.3）。

### 15.2 但三个指标里有两个的射程与预期不同

实测（V1F 校准 runs，力**开启**，故只作指示；全部 960 run）：

| 指标 | `zero_wealth_fraction` | 取值 |
|---|---|---|
| 全部 960 run 的不同取值个数 | **4** | `{0, 6.94e-6, 1.39e-5, 2.08e-5}` |
| clustered / dt=0.005 / 64 seeds | **恰为 0 的有 64/64，sd = 0** | — |
| `clustered − shuffled` 配对差（dt=0.02/0.01/0.005） | **三者都恰好为 0** | — |
| 由 `_weak_bound` 导出的数值上限 | **0.0** | — |

**`zero_wealth_fraction` 在本参考体制下是退化的**，因此它**不能作为估计量**。要分清两件事：

- 它测出的上限 `0.0` **不是"精度极好"**，而是"对 dt 逐位不敏感"。对常数指标这是同义
  反复、不载信息——与 `wealth_gini` 那个随 dt 收缩的 9.4e-5 形成对照（后者才是真信息）。
- 它作为**可比性护栏**（§4 P4 的"`zero_wealth_fraction` 低于冻结上界"）却完全称职：
  恒为 0 必然低于任何上界。

问题出在 §4 P2 把 `zero_wealth_fraction` **同时列为估计量**。数据说明它只能承担前一个角色。
若把它做成 claim-eligible，会得到一个**空洞的 null**——正是 §4 P4 明令"不得记为 null"的
那种情形。这不是校准缺口，是**度量的科学不可用性**，属于另一个类别。

**`wealth_variance` 恰恰相反，是三个里最有承载力的**：

| dt | `clustered − shuffled` 的 \|mean\| | 2·SE | 数值上限 |
|---|---|---|---|
| 0.02 | 3.6866 | 0.424 | — |
| 0.01 | 3.6554 | 0.414 | — |
| 0.005 | 3.6507 | 0.428 | **0.0568** |

即信号约为其数值上限的 **64 倍**（3.65 / 0.0568），且随 dt 稳定。（对照：`wealth_gini`
在同一比较上 \|mean\| = 0.00225 而 2·SE = 0.00388，本身就不显著——这提醒 E2-C4 的 P2 主对比
在力**关**的新体制下必须用 pilot 重新确定可检测性，不能沿用 V1F 力**开**时的尺度。）

`mean_wealth` **不在**保留的 CSV 中（62 列里没有它）。原因不是"漏记"，而是**代码版本**：
V1F 跑在 `48ad02a`，其 `snapshot_metrics` 返回 8 个键，**没有** `mean_wealth`；该键是在
V1F 之后、随 S12 加入的。

| | V1F 提交 `48ad02a` | 当前 |
|---|---|---|
| `snapshot_metrics` 的键数 | 8（3 个空间/结构 + 5 个财富/计数） | 9（+`mean_wealth`） |
| `replicate_metrics.csv` 是否含 `mean_wealth` | 否 | 是（`write_metrics_csv` 写全部标量键） |

故 `mean_wealth` 的上限**不能**从 CSV 重算，只能回到保留的原始快照重取：每 run 尾窗
`steady_snapshots = 144` 帧、960 个 run，约 **1.4 × 10⁵ 次快照读取（≈28 GB）**——仍是
重分析而非重跑，但代价比 CSV 路径高三个数量级。另外，§5 那组平均财富数字（1.98/1.38/0.59、
+43.6%）是 V1F 运行期间**临时命令**读出的，**没有**对应的入库脚本，因此目前只有散文级的
可审计性；`mean_wealth` 若能入库为校准量，顺带也把这组数字变成可重算的。

`mean_wealth` 同时也是 §6 要求随 E1-C4 报告的财富尺度诊断量。它的**角色**（估计量还是
审计量）见 §15.5。

### 15.3 因此 (B) 收窄为 (B′)，并新增一条机械判据

**建议 (B′)：校准扩展到 `wealth_variance` 与 `mean_wealth`；`zero_wealth_fraction` 明确
退出估计量家族、保留为 P4 护栏。** 同时把"能否作为估计量"从散文变成**机械校验**：

> claim-eligible 的指标除了要有数值上限与 SESOI，还必须在参考配置下**具有非零方差**。
> 一个数值上限为 `0.0`（或方差为 0）的指标不得进入断言家族——否则会产出空洞的 null。

已按此实现为 `run_landscape_study.e2_c4_claim_ineligibility_reasons`：每个原因都**不含任意
常数**（只判定"成立/不成立"），且要求全部原因都不成立才得 claim。

| 原因码 | 判定 |
|---|---|
| `missing_numerical_resolution_limit` | 指标不在校准产物的数值上限表内 |
| `zero_numerical_resolution_limit` | 上限**恰为 0.0**——这是"对 dt 逐位不敏感"，不是"精度极好"；该数无法界定一个离零的误差 |
| `missing_scientific_sesoi` | 指标不在配置的 SESOI 表内 |
| `degenerate_metric_no_variance` | 该指标在**被分析的 run 上取值恒定**（或缺失）——没有可估计的对象 |

结果写入 payload 的 `threshold_provenance.ineligibility_reasons`，故每个被排除的指标都带着
**理由**，而不是被静默剔除；`claim_eligible_metrics` / `descriptive_only_metrics` 照旧。
`zero_wealth_fraction` 在实测数据上**同时命中两条**（上限 0.0 与取值恒定）。

这条判据同时挡住两类错误：把退化指标当成"精度极好"（§15.2），以及把"没有差异"当成结论。

另有一条**忠实性检验**（只在 (B′) 实施时适用）：新校准产物必须**逐位重现** V1F 的四个上限，
否则它就不是一次忠实的扩展，而是另一次测量。该检验分两级，可执行的位置不同：

- **产物级（本地可执行）**：新产物的四个旧指标上限，与已入库的 `numerical_calibration.json`
  逐位相等。两个文件都在 git 里，故这一级不依赖任何服务器数据。
- **字段级（须在 `umi` 执行）**：以 V1F 自己的 `_weak_bound` 从保留的 `replicate_metrics.csv`
  重算 3 个 landscape × 4 个指标 × 两层（每个 bound 6 个浮点字段），全部逐位相等。
  CSV 是 workspace 产物（`gitignore`，不入库），所以这一级只能在持有该 workspace 的机器上跑。

只做产物级是不够的：它只能证明"新产物抄了旧上限"，不能证明新指标的上限与旧上限出自同一条
计算路径；字段级才能证明后者。

### 15.4 仍需研究者定夺的一处

新指标的**数值上限是测出来的**（不需选择），但 `aggregate_v1` 还要求 `numerical_error_ceilings`
覆盖每个指标——而"该指标的数值误差不能超过多少"是一个**选择**，V1F 当时给空间类取 0.02、
给 [0,1] 类取 0.01。对 `wealth_variance`（尺度约 2–20）与 `mean_wealth`（尺度不同）**没有
可类比的现成值**。

**建议不为新指标发明 ceiling**：新指标只用**数据导出的判据**（trend_pass 与
bounded_by_discretization，两者都已在 `aggregate_v1` 里定义、都不含任意常数），把 ceiling
显式记为"待 SESOI 冻结时一并确定"，而不是就地编一个数。这样 (B′) 不引入任何新的
事后可调的阈值。

### 15.5 `mean_wealth` 的角色：估计量还是审计量（待定夺；pilot 会免费回答一半）

(B′) 把 `mean_wealth` 列入校准扩展，也就隐含把它列入 §4 P2 的估计量。但三条**已在库的**
证据指向另一个角色：

1. **代码自述。** `snapshot_metrics` 对 `mean_wealth` 的注释是 "the mean wealth level is an
   auditing quantity, **not a gate** ... any wealth-family effect must therefore be reported
   **together with** this level"。它是为**伴随报告**而加入的，不是为充当结局变量。
2. **§4 P4 已经这样用它。** P4 第 3 条把 `mean(w)/w_ref` 定为"作为**解释变量**而非合格线"。
   同一份文件里 P2 又把它当估计量，是两处不一致（与本文件 §14 记录过的那类"散文宣称的
   射程超过代码实际给予的射程"同型）。
3. **P4 第 2 条与"估计 `mean_wealth`"直接冲突。** P4 要求 P2 三单元**实测平均财富**的相对
   偏差落在冻结带内（建议 ±10%），任一单元不过则该对比记为 inconclusive、且不得记为 null。
   §5 在力**开**体制下实测 `clustered − shuffled` 的平均财富差为 **+43.6%（+0.6028）**，
   远超该带。若力**关**的新体制同向，则 P2 主对比按 E2-C4 自己的 Gate 就是 inconclusive；
   此时再宣称"空间组织改变财富水平"，等于宣称一个自己已经声明**必须不**存在的差异。

**pilot 会免费回答一半。** 当前代码的 `snapshot_metrics` 已含 `mean_wealth`，故 E2-C4 pilot
（8 个全新 seed × 5 单元）的 `replicate_metrics.csv` **天然带 `mean_wealth` 列**，不需要任何
额外计算，即可在**真实体制**（力关、E2-C4 单元、全新 seed）下量出：单元间水平偏差是否落在
±10% 带内、以及该对比的 2·SE。这正是 §15.2 结尾要求"必须用 pilot 重新确定可检测性"的那件事。

**但 pilot 是单 dt 的**，所以它给不出 `mean_wealth` 的数值上限（那需要一对细化步长）。因此
"是否值得那 ≈28 GB 快照重取"完全取决于它的角色：

| 选项 | 含义 | 代价 |
|---|---|---|
| (i) 审计量 | 不做校准扩展。`mean_wealth` 随结果报告、进 P4 可比性判据；`claim_eligible` 因缺上限而为 false，理由码 `missing_numerical_resolution_limit` | 0 |
| (ii) 估计量 | 须做快照重取以定上限，且须先解决上面第 3 条的 P4 冲突 | ≈28 GB 只读 |
| (iii) 由 pilot 定夺 | 先按 (i) 推进；pilot 数据到手后再定 (i)/(ii) | 0（延后） |

无论选哪个，`wealth_variance` 的扩展都不受影响（它就在 CSV 里，代价为零）。

> **定夺（2026-09-17）。** 选 **(i) 审计量**：不做 `mean_wealth` 的校准扩展，那 ≈28 GB 的
> 快照重取**不做**。它随结果报告、参与 P4 可比性判据，`claim_eligible = false`，理由码
> `missing_numerical_resolution_limit`。同时把 P4 第 2 条的水平带**冻结为 ±10%**（不再写
> "建议／实施时冻结"），即明确接受上面第 3 条的后果：若实测单元间偏差超出该带，P2 主对比按
> 设计自己的 Gate 记为 **inconclusive**——不得记为 null、不得放宽带子。

> **推论（须在 E2-C4 提交前登记）。** 水平带既然冻结在 ±10%，而 §5 力开体制的实测偏差是
> +43.6%，E2-C4 的 P2 就存在一个**先验可失败**的 Gate。pilot 会在真实体制（力关、全新
> seed、5 单元）下量出该偏差，因此 pilot 的职责之一正是**提前**回答"P2 是否可比"；若 pilot
> 显示超带，应在 E2 lock 冻结前收窄 P2 的射程，而不是投完预算再发现 inconclusive。

## 16. V1H 执行与判定记录（2026-09-18）

V1H 是 §15 收窄为 (B′) 之后的实施与回收。它**不跑模拟器**：只读 V1F 留在 workspace 里的
`replicate_metrics.csv`（sha256 `902b286a…`），用 V1F 自己的 `_weak_bound` 重算分层误差界。
墙钟 0.37 s，无 GPU，无新 seed。

**预注册的判定式（提交前写下，事后不得更改）。**

1. 四个旧上限必须**逐位重现**（3 landscape × 4 指标 × 2 层、每个 bound 6 个浮点字段全部相等），
   否则**整份产物不发布**——差一点点不是"更严格"，而是对另一个对象的又一次测量。
2. 扩展只**允许新增**上限：既有上限不得被改写、不得被重新声明为"扩展"。
3. 不为新指标**发明 ceiling**：`numerical_error_ceilings` 是预注册的失败阈值，事后填写即为
   未注册阈值；新指标只用数据导出的判据（`discretization_trend_pass` 与
   `bounded_by_discretization`，两者都不含任意常数），ceiling 留给 SESOI 冻结时一并确定。

**实测结果（`pass = true`）。**

| 项 | 值 |
|---|---|
| 忠实性 | `field_mismatches = 0`；四个上限 `bit_equal = true` |
| 复现出的旧上限 | spearman `0.004589992673223881`、Moran `0.0032587589468579255`、entropy `0.0009948207537034592`、Gini `0.0014407792015185721` |
| 新增上限 | `wealth_variance = 0.056828569227561854`（取 discretization 层最差单元 `clustered`） |
| 分层判据 | 三单元 `trend_pass = true`；order 层最细 dt 界 `0.005972…` 小于 discretization 界，故 `bounded_by_discretization = true` |
| `mean_wealth` | 不在扩展范围（§15.5 定为审计量）；产物内以 `out_of_scope` 显式记录，不静默略过 |

**回收：为什么需要一个新子命令。** `load_e2_c4_calibration` 只检查扩展件**自述**的两个性质
（pin 了源的 sha256、自报忠实性干净）。这两条都写在同一个文件里，因此任何"自称扩展 V1F"的
文件都能满足它们。`prepare_cycle4_confirmation.py record-calibration-extension` 在**入库前**
把自述变成事实：读磁盘上那份 `numerical_calibration.json`、算出它的 sha256、再从**那份文件**
里读回四个上限逐个比对，并拒绝以下情形——pin 与磁盘不符、旧上限被改写、某个旧指标被静默
跳过、扩展集为空、把已冻结指标重新声明为"扩展"、配置声明的扩展指标与产物不符、以及为新指标
带上 ceiling。所有校验都在任何写入之前完成，故失败时 job 目录保持原样。

```bash
python3 research/src/experiments/prepare_cycle4_confirmation.py record-calibration-extension \
  --job-dir research/jobs/V1H-CALIBRATION-EXTENSION-C4 \
  --jobctl-dir .autoresearcher/jobs/V1H-CALIBRATION-EXTENSION-C4 \
  --source-calibration research/jobs/V1F-NONFLAT-CALIBRATION-C4/numerical_calibration.json \
  --conclusion-artifact numerical_calibration_extended.json \
  --workspace-artifact numerical_calibration_extended.json
```

入库的三份记录：

| 文件 | 内容 |
|---|---|
| `numerical_calibration_extended.json` | 完整产物，sha256 `545363ea…`，与 workspace 源逐字节相同 |
| `result.json` | 源绑定（路径 + sha256）、忠实性摘要、四个旧上限与一个新上限、`pathwise_claim = false`、ceiling 政策 |
| `manifest.json` | jobctl 对账形状（exit 0、未超时、墙钟、产物 sha256） |

**seed 处置（一处必须写清的细节）。** V1H 不消耗 seed，故声明集里只有 `seed_waiver.txt`，
没有 `seeds.txt`；台账把它记为"无 seed 证据（已豁免）"而非消费者。但 `jobctl submit` 要求
提交时必须给出 seed 声明，因此提交时传入的是 **V1F 的 64 个 seed**，其语义是**provenance**：
它们标识保留表里那些 V1F run，而不是 V1H 要重抽的随机流。这一点写在 `seed_waiver.txt` 里，
并且**列表必须与 V1F 的 `seeds.txt` 逐项相等**——由测试绑定，因为台账只检查 waiver 是否存在，
一份**伪造的** provenance 列表本来可以躺在 git 里不被发现（本地确实先写错过一版，是这条
测试把它挡下来的）。

**测试与变异检验。** `record-calibration-extension` 有 **20 项测试**（含失败/超时/空产物/
pin 不符/源路径不符/改写旧上限/静默跳过/非逐位相等/重复冻结/无新增/伪造 ceiling/指标漂移/
判定自相矛盾/`pathwise_claim` 为真/非 V1F 源等），另有 **3 项入库忠实性检验**：从已入库的产物
重导 `result.json`、把四个上限与 V1F 已入库的 `numerical_calibration.json` 对照、以及把待加载
产物喂给 `_require_cycle4_calibration_identity`（记录器与加载器校验的是同一主张的两半，
一个能过不等于另一个能过）。四类变异——产物内上限漂移、记录漏掉一个旧上限、V1F 事后
被重新校准、记录把已冻结指标重新声明为扩展——**全部被捕获**。
