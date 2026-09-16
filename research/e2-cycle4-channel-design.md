# E2-C4 通道分离设计（S09 处置）

日期：2026-09-16。状态：**设计冻结，未授权执行**。本文件在 E2-C4 任何结果产生前写入，
不读取 Cycle 3 E2 的效应方向、效应大小或显著性用于本设计。文件依据是活动源码、
`run_landscape_study.py` 的条件生成逻辑，以及对 Cycle 3 E2 已归档数值的**结构核对**
（核对的是"因子动了什么"，不是"效应有多大"）。

处置对象是 `simulator-improvement-plan.md` 的 S09：*E2 同时开关生产与衰减*。
S01（财富无空间反馈）的写实已完成，见 [model-specification-c4.md](model-specification-c4.md)。

## 1. S09 的准确诊断

### 1.1 代码事实：一个开关同时动了 source 与 sink

`run_landscape_study.py` 的 E2 条件生成（第 285–303 行）中，名为 `production` 的因子同时决定两个量：

```python
"terrain_production_enabled": production,
...
# production↔decay 配对（参数锁 v3）：生产通道 = 生产(source) + 衰减(sink) 平衡对。
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
`0.5·((y01 − y00) + (y11 − y10))`，即"source+sink 同时打开"与"两者同时关闭"之差。
**这个对比里没有任何一项能单独归给生产或衰减**。加 `wealth_decay_rate` 配对的理由在原注释中
写得很清楚（避免 `production=0, decay>0` 时财富指数坍缩），但那个补救本身把因子变成了 bundle。

### 1.2 实证事实：四类不可比性（对 Cycle 3 E2 归档数据的结构核对）

对 `E2-CHANNEL-ABLATION` 的 160 个 run（20 seeds × 2 landscapes × 4 单元）逐个读取归档指标，
得到（`n = 40`/单元，全部单元 `stationarity_pass = 1.00`）：

| force | prod | decay | Gini | wealth variance | min wealth | occupancy entropy | Spearman | Moran |
|---|---|---|---|---|---|---|---|---|
| 关 | 关 | 0 | 0.6340 | 39.93 | 0 | 0.7748 | −0.0006 | −0.0006 |
| 关 | 开 | 0.02 | 0.7584 | 0.9962 | 1.44e−07 | 0.7748 | −0.0006 | −0.0006 |
| 开 | 关 | 0 | 0.6245 | 38.50 | 0 | 0.7237 | 0.2368 | 0.3519 |
| 开 | 开 | 0.02 | 0.6700 | 5.357 | 1.24e−06 | 0.7237 | 0.2368 | 0.3519 |

由此确认四条事实：

**(a) "关"单元没有可比的长期状态，而是退化态。** `prod=关` 时 decay = 0，交换严格零和，
所以总财富守恒，平均财富恰为初值 **5.0 = `w_ref`**。`prod=开` 时 decay = 0.02 把财富压到
`min wealth ≈ 1e−07…1e−06`，财富方差从 ~39 掉到 ~1（force 关）与 ~5.4（force 开）。
由于均值未被记录，用方差与 Gini 对数正态反推，`prod=开` 单元的平均财富约为 **0.27**
（force 关）与 **0.97**（force 开），即 **`w/w_ref` 约 0.05 与 0.19**，而"关"单元是 1.0。
交换能力函数 `A = ε·w/(w+w_ref)` 在这两种工况下处于完全不同的区域：`w ≪ w_ref` 时
`D_ij → (ε_i − ε_j)/(ε_i + ε_j)`，**交换几乎不再依赖财富**；`w = w_ref` 时能力函数的
半饱和结构与 `w` 耦合。因此 E2 的 `production` 对比同时改变了财富水平、衰减机制和交换核的
工作点。这不是三个可分辨的效应，是一个包。

**(b) 空间指标对 `production` 因子的响应是严格恒等，不是统计零。** 在每一个 (seed, force)
组合上，`prod=关` 与 `prod=开` 的 `resource_density_spearman_rho`、`density_morans_i`、
`occupancy_entropy` **字符串完全相等**（20/20 seeds，两种 force 各 20 组，差值 > 1e−12 的
计数为 0）。这与因果图一致：生产与衰减只写 `w`，而运动方程不读 `w`
（[model-specification-c4.md](model-specification-c4.md) §4.2、§6.2）。
所以 Cycle 3 E2 报告的"production 对空间结构零效应"**不是一项科学发现，而是代码因果结构的
恒等验证**；把它写进 `identified_channels` 语义下是误读。

**(c) force 因子同样移动财富尺度，所以 movement×production 交互项被混淆。** force 关→开
使 `prod=开` 单元的平均财富从约 0.27 升到约 0.97（约 3.6 倍）：力把粒子送进资源阱，
`Σprod_i` 随之上升，平衡水平 `ω* = Σprod_i/(N·d)` 改变。于是交互项 `y11 − y10 − y01 + y00`
里"位置改变邻接图"的贡献与"位置改变资源收支总量"的贡献混在一起，无法分开。

**(d) 旧稳态 Gate 无法发现上述问题。** 四个单元的 `stationarity_pass` 全为 1.00。
逐运行稳态只回答"这个 run 自己稳不稳"，不回答"各单元是否处在可比的长期状态"。
这是判据层的缺口，不是数据层的噪音。

### 1.3 结论

S09 不是"命名不当"，而是**可识别性缺陷**：旧的 `production` 因子在任何意义上都不能承担
单通道归因，且旧 Gate 结构上无法暴露这一点。

## 2. 为什么不能简单地"拆成 2×2"

一个自然的想法是改成 source × sink 的真 2×2。这在稳态估计量下**不可识别**，原因是数学的，
不是设计选择：

设单位时间的源为 `prod_i ≥ 0`、衰减率为 `d`。总财富满足
`dW/dt = Σ prod_i − d·W`，平衡水平 `ω* = Σ prod_i/(N·d)`。

- `(source 开, sink 开)`：`ω*` 有限，平稳分布存在；
- `(source 开, sink 关)`：`dW/dt = Σ prod_i > 0`，财富**线性发散**，不存在平稳分布；
- `(source 关, sink 开)`：`W → 0`，落入退化吸收区（正是 §1.2(a) 观察到的 `min wealth ≈ 1e−07`）；
- `(source 关, sink 关)`：只剩零和交换，`W` 守恒 —— 这是唯一另一个有非平凡平稳分布的单元。

**四个单元中只有两个有非平凡稳态**，所以"source 主效应"和"sink 主效应"作为**平稳态的**
水平对比在数学上不存在。任何声称能给出这两个主效应的设计，都只能是在非平稳单元上取有限时间值，
那与稳态估计量不是同一个量。

**由此得到本设计的核心判断**：sink 不是一个可以开关的通道，它是**使稳态存在**的条件。
因此"纯生产"与"纯衰减"不能作为两个可独立开关的因子；能问的是另外两个问题——

1. 源的**空间组织**（同一总量下分布在何处）是否改变财富结构？
2. **衰减速率**（在平衡水平被匹配的条件下）是否改变财富结构与时间相关？

这两问都要求"各单元处于可比的长期状态"，而这正是 §1.2(d) 暴露的缺口。识别策略如下。

## 3. 识别策略

三条约束，缺一不可：

**约束 1（非退化）**：每个单元必须有非平凡平稳分布，即同时存在源与汇。
**约束 2（水平匹配）**：若被检验的机制不是"财富尺度"本身，则各单元的平衡水平必须匹配
（`Σprod/(N·d)` 相等），否则财富尺度的变化会经由 `w_ref` 改变交换核工作点，成为混杂
（§1.2(a)）。
**约束 3（结构隔离作为前置恒等检查）**：任何只写 `w` 的因子对空间指标的效应必须
**严格为零**；这一条按恒等检查（逐 seed 字符串相等）执行，而不是按统计检验执行。

在约束 1–3 下，"生产"与"衰减"被分别落实为：源的空间组织（可开关，因为总量可用均匀源补齐）
与汇的速率（不可开关，只能沿 `s/d` 常数线变化）。这就是下面 P2 与 P3 的来源。

## 4. E2-C4 设计矩阵

统一契约继承 Cycle 4 参考过程：`N = 1000`、`64×64`、`dt = 0.005`、`total_time = 4500`、
输出间隔 5、最后两段相邻 144 帧、`temperature = 0.5`、`friction = 1`、`social_strength = 0`、
`interaction_range = 2.5`、`exchange_rate = 0.5`、`noise = 0.05`、`reversion = 1`、
`epsilon_log_sigma = 0.5`、`w_ref = 5.0`、单 rank、`OMP = 1`。

### P1 — 结构隔离恒等检查（前置，非科学检验）

- 单元：force ∈ {关, 开} × 源型 ∈ {景观依赖, 均匀}，共 4 个单元。
- 判据：在每一个 (seed, force) 上，两源型之间的 `resource_density_spearman_rho`、
  `density_morans_i`、`occupancy_entropy` 必须**字符串完全相等**。
- 处置：任一处不等即视为**实现失败**（伪耦合或非确定性），必须阻断该批次，不得报为效应。
- 性质：这是回归护栏。Cycle 3 E2 已经在旧代码上证明该恒等成立（§1.2(b)），E2-C4 需要
  在新版交换核与新版源项上重新确认。
- 注意：P1 的 4 个单元**不用于任何财富效应估计**，因为 force 会内生地改变 `Σprod`
  （§1.2(c)），四单元在财富轴上不可比。

### P2 — 源的空间组织消融（`force = 开` 固定）

- 单元（2 个，均在 `d = 0.02`）：
  - `S_land`：`prod_i = base·terrain_production_scale·r(x_i)·ε_i·dt`，`r = max(0, −V)`；
  - `S_unif`：`prod_i = base·terrain_production_scale·ρ·ε_i·dt`，`ρ` 为**预先冻结的标量**。
- `ρ` 的取值依据可以精确化：`generate_clustered_resource` 与
  `generate_correlated_random_resource` 都把资源场归一化到**均值恰为 1**，因此按面积加权的
  源总量在 `ρ = 1` 时与 `S_land` 完全一致。所以取 `ρ = 1.0`，并在申报中把依据写成
  "资源场按构造均值为 1"。
- sink 在两者中恒为 `d = 0.02`，因此约束 2 在**期望意义上**成立：两单元的 `ω*` 相同。
- 估计量：源空间组织对财富结构（Gini、wealth variance、zero-wealth fraction）的效应。
  空间家族仅作 P1 恒等检查，不作科学结论。
- 已知残余：实际源总量取决于占据分布，而占据分布是内生的。`ρ = 1` 只匹配**面积加权期望**，
  不匹配**实现值**。因此 P4 可比性 Gate 是强制的，不是可选的。

### P3 — 汇速率的匹配平衡响应（`force = 开` 固定）

- 单元（3 个），沿 `base_production/wealth_decay_rate` 常数线：

| 单元 | `d` | `base_production` 缩放因子 | 松弛时间 `τ = 1/d` |
|---|---:|---:|---:|
| `D_low` | 0.01 | 0.5 | 100 |
| `D_ref` | 0.02 | 1.0 | 50 |
| `D_high` | 0.04 | 2.0 | 25 |

- 共同源型：`S_land`（与 P2 的 `S_land` 共享同一单元，不重复计算预算）。
- 匹配量：`ω* = s·base·r̄_occ·ēps/d` 在三单元中相同（`s/d` 常数），故财富尺度匹配；
  不同的是松弛时间 `τ`（相差 4 倍）。
- 估计量：`d` 在匹配平衡下对财富结构与**时间相关诊断**（IAT / ESS / 跨窗稳定性）的效应。
- 这条线同时是一个**模型尺度不变性的可证伪检验**：若模型在 `w ↔ c·w`、`t ↔ t/c`
  下自相似，则三单元的结构指标应无差异；任何偏离都定量给出交换核经由 `w_ref`、
  `share` 夹紧与绝对零下界引入的尺度依赖。§1.2(a) 已经把"财富尺度会改变交换工作点"
  确认为一项模型性质，P3 把它从混杂变成了**被测量的对象**。
- 时间可行性：`d = 0.01` 的 `τ = 100`，`total_time = 4500` 为 45τ，仍在同一物理时长契约内；
  不需要为不同单元改 `total_time`（改时长会破坏"所有单元同一物理时长"的既有纪律）。

### P4 — 可比性 Gate（强制，预先冻结）

在计算任何效应之前，逐单元检查并写入结果：

1. 非退化：`zero_wealth_fraction` 低于冻结上界；`minimum_wealth_observed ≥ 0`；
   非有限计数为 0；`wealth_variance` 高于冻结下界（用于捕捉 §1.2(a) 式的坍缩）；
2. 水平：**实测**尾窗平均财富落在设计目标 `w_ref = 5` 的冻结带宽内
   （建议 ±10%，实施时冻结）；
3. 工作点：报告 `mean(w)/w_ref`，要求落在冻结带内；
4. 承继 Cycle 4 契约的尾窗稳态、相邻双窗稳定性与独立 seed 精度 Gate。

任一单元未通过可比性，则该对比记为 **inconclusive**，不得记为 null，也不得删单元或事后调带宽。

### P5 — 旧 bundle 的重新命名（仅 provenance）

Cycle 3 E2 的 `production` 因子改称 **source–sink bundle ablation**，只能作为**单一因子**
报告财富指标的效应，禁止归因于生产或衰减；其空间家族结果改述为 P1 的恒等检查。
Cycle 3 数值不重跑、不改写，但 `identified_channels` 字段的解释必须随本文件更正。

## 5. 必需代码改动

1. **新增 `uniform_production`（源的空间均匀分量）**。`SimConfig` 新字段（默认 `0.0`，
   向后兼容）、`apply_key_value` 新键、`validate_config` 用 `isfinite` 且 `≥ 0` 校验、
   传入 `apply_resource_dynamics`，源项改为
   `local_resource = base·terrain_production_scale·max(0,−V)·[terrain_production_enabled] + uniform_production`
   （均匀分量的启用由取值是否为 0 决定，避免再加一个布尔开关）。
   需配套 CTest：`uniform_production = 0` 时与旧行为逐位一致；`> 0` 时源随 ε 线性放大。
2. **补齐可比性所需字段**。当前 `replicate_metrics.csv` **没有记录平均财富**
   （表头只有 `wealth_gini`、`wealth_variance`、`minimum_wealth`、`total_wealth_relative_drift`），
   这正是 §1.2(a) 只能靠反推估计的原因。新增 `mean_wealth`、`zero_wealth_fraction`、
   `mean_source_rate`、`wealth_scale_ratio = mean_wealth/w_ref` 四列。
3. **P1 恒等检查进入分析器**：对 (seed, force) 分组比较源型之间的空间指标，不等即
   `raise`，而不是产生一个效应条目。
4. **`aggregate_e2` 的重写**：拆成 `isolation_identity`（P1）、`source_pattern`（P2）、
   `sink_rate`（P3）、`comparability`（P4）四块；不再产生 `movement`/`production`/`interaction`
   三个旧效应字段。

## 6. 统计契约、seeds 与预算

- **seeds 必须全新且互斥**。可用池 = 未出现在 Cycle 1–3、`V1`/`V1B`/`V1C`/`V1E`/`V1F`/`V1P`
  与 E1-C4 的 64 个冻结 seeds 中的素数（E1-C4 已占用 `11657–12241` 段）。沿用 E1-C4 的
  记账式互斥审计（对全部 `seeds.txt` 与 job config 的 `seed` 字段做全量比对），
  该审计已在本轮复核过一遍，方法可复用。
- **样本量不得继承 E1-C4 的 64**。64 是为配对景观对比的估计量定的，与 P2/P3 的估计量不同。
  必须先用**非证据 pilot** 估计各对比的方差（只看方差与可比性，不看对比方向或大小，
  与 V1ED 对 V1E 的用法一致），再按既有的"上取 2 的幂"政策冻结。
- **单元数与预算估计**。去重后 6 个单元（P1 的 4 个 + P3 的 2 个额外汇水平；`D_ref` 与
  P2 的 `S_land` 共享）。按 V1E 实测约 **1,242 秒/run**（`N=1000`、`dt=0.005`、`T=4500`）：
  - pilot：6 单元 × 8 seeds = 48 runs ≈ 16.6 CPU 小时 ≈ 8 路 2.1 墙钟小时；
  - 正式（若 R = 32）：6 × 32 = 192 runs ≈ 66.2 CPU 小时 ≈ 8 路 8.3 墙钟小时。
  以上为数量级估计，实施前须用 pilot 的实测速率修正。
- **执行纪律**：jobctl 提交、preflight 通过后执行、完成后 `jobctl reconcile`；
  重产物进 `research/jobs/E2-CHANNEL-ABLATION-C4/workspace/`。

## 7. 禁止事项与不作出的主张

- **不得**为了得到非零的空间效应而临时加"财富驱动迁移"。财富→空间反馈是另一个研究问题，
  需要微观行为依据、额外参数校准与新因果图（[model-specification-c4.md](model-specification-c4.md) §6.2）。
- **不得**把 P1 的恒等结果报告为"生产对空间结构无效应"这一科学结论。
- **不得**在 P2/P3 上事后调整 `ρ`、`d` 梯度或可比性带宽以挽救判定。
- **不得**给出"纯生产效应"或"纯衰减效应的社会意义"这类表述。P3 给出的是
  *匹配平衡下的汇速率效应*，P2 给出的是 *等期望总量下源的空间组织效应*。
- 本设计**不**声称任何关于真实历史、国家或制度的结果；证据边界仍是合成景观中的生成机制。

## 8. 与其他工作的关系与启动顺序

- E2-C4 在 `plan.json` 中的状态是 `deferred`，阻塞条件为"V1 calibration and estimand freeze"。
  本设计冻结了估计量，但 V1F 校准与最终 Cycle 4 参数锁仍未生成。
- 数值分辨率界与科学 SESOI 必须**分别**绑定：P2/P3 的等效区半宽沿用
  `max(V1F numerical_resolution_limit, scientific_sesoi)` 的形式，但 V1F 的界是在
  `total_time=4500`、`dt=0.005` 的最细步长上建立的主指标分辨率界；P3 改变了衰减速率，
  因此其时间相关诊断与 ESS 需求必须由 pilot 重新说明，不得直接搬 V1E 的 ESS 结论。
- 启动顺序：V1F 通过 → promotion `archive-v1f` → `prepare` 生成 candidate 锁 → V0G 通过 →
  `finalize` 绑定 binary 与 final 锁 → E1-C4 执行 → **E2-C4 才进入实施**。
  E2-C4 不得与 E1-C4 并行，也不得复用 E1-C4 的 seeds。

## 9. 交付检查表

- [ ] `uniform_production` 实现 + CTest（`=0` 逐位向后兼容）
- [ ] `mean_wealth`、`zero_wealth_fraction`、`mean_source_rate`、`wealth_scale_ratio` 入表
- [ ] P1 恒等检查在分析器中 fail-fast
- [ ] `aggregate_e2` 拆为 P1/P2/P3/P4 四块，旧三效应字段删除
- [ ] seeds 互斥审计（记账式，覆盖全部历史 job）
- [ ] pilot 只读方差与可比性，冻结 R 后生成正式声明
- [ ] preflight 通过、`confirmative_mode`、`nprocs=1`、`OMP=1` 写入 config
- [ ] E2-C4 新实验 ID 与独立目录，Cycle 3 E2 结果不改写、只改解释
