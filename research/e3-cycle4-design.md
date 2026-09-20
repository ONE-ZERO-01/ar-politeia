# E3 Cycle 4 robustness 设计

日期：2026-09-20。状态：**设计评审中**——本文件先给出对现行 E3 实现的审计与估计量可比性分析，
再给出设计；其中若干选择需要定夺（§6）。

本文件在 E3-C4 的任何结果产生前写入，不读取或使用 Cycle 3 E3 残段的效应方向、大小或显著性。
唯一的例外是对残段**耗时**的使用（用于预算），那不是科学信息。

---

## 1. 主张与可证伪条件

`C4-ROBUSTNESS-C4`：

> Any supported Cycle 4 landscape effect retains direction under separately designed
> system-size, density, grid-discretization, and holdout-landscape checks.

证伪条件：

> Effect direction reverses, falls inside the frozen equivalence region, or depends on
> conflated scale/density/grid changes.

把这句话拆成可检验件，得到**四条腿**加**一个条款**：

| 腿 | 被操作的一维 | 证伪触发 |
|----|-------------|---------|
| S | system size | 方向反转 / 落入冻结等效区 |
| D | density | 同上 |
| G | grid discretization | 同上 |
| H | holdout landscape family | 同上 |
| — | conflation | 效应**依赖于**把 scale/density/grid 混在一起的变化 |

最后一条不是"再测一次"，而是一个**关于其他四条腿自身结构的断言**：必须能证明每条腿只在它
命名的那一维上变化。下面的审计显示，现行实现恰恰在这一条上站不住。

---

## 2. 现行 E3 实现审计

`prepare_e3_inputs`（`run_landscape_study.py:513`）的操作矩阵是
`populations × grid_shapes × landscape_families × seeds × {clustered, shuffled}`，
其中 `bounds` 是**单个**值。这个矩阵与 C4 的四条腿不是一回事。

### F1 没有 system-size 操作；`populations` 实际是 density

`bounds` 取单值（`run_landscape_study.py:725`），`populations` 与 `grid_shapes` 在**固定域**上独立变化。
于是：

- 改 `populations`（域面积不变）= 改**粒子密度**，不是改系统尺寸；
- 改 `grid_shapes`（域面积不变）= 改**格距 dx**。

**实现里没有任何东西会改变域的尺寸**。C4 的 "system-size" 腿在现行实现中不存在，而 `populations`
这个命名会让读者以为它存在。Cycle 3 的 `E3-ROBUSTNESS-HOLDOUT` 计划把它写成
"population N in {2000, 5000, 10000}" 并称其为 scale——那一步测的是密度。

### F2 全交叉矩阵按构造无法把 size/density/grid 分开

因为 `populations` 与 `grid_shapes` 是独立的两条列表、域固定，矩阵中的每个 cell 同时改变密度与
格距。效应若随 cell 变化，无法归因到三维中的哪一维。这与证伪条件的 conflation 条款**正面冲突**：
现行设计不能产生一个"不混淆"的断言。

### F3 旧配置不是 Cycle 4 工作点，且绑定已作废的校准

Cycle 3 E3 config：`dt=0.01`、`total_time=2000`（参考为 `dt=0.005`、`total_time=4500`），
并绑定 `research/jobs/E0-NUMERICS-C3/numerical_calibration.json` 与 `research/parameter_lock.json`。
`aggregate_e3` 的 SESOI 来自 `load_e0_calibration`（Cycle 3 E0）。
所以旧 E3 的效应是在**未由 V1F/V1H 校准的数值体制**里测量的，其判据也来自已作废的校准。

### F4 判据统计上弱，且仍把各维平均在一起

- `direction_consistency`：比较 `overall_mean_effect`（对 populations × grids × families **全部平均**）
  的符号与每个 population 水平的符号。只看符号、不看区间——一个由噪声驱动的极小非零效应即可"通过"。
- `resolution_sensitivity`：`|effect(256²) − effect(128²)| / max(|effect(256²)|, sesoi) ≤ 0.2`。
  分母只取**较高分辨率**一侧的幅值，因此对两级不对称；而 `20%` 没有任何 provenance——
  dx 轴从未被校准（见 F3 与 §4.2 Leg G）。
- `claim_supported` 只由 `resource_density_spearman_rho` 一条主指标决定
  （`run_landscape_study.py:3600-3606`），其余两条主指标不参与。
- Holm 家族是 4 指标 × 3 population × 2 grid × 2 family = 48 个 cell，而主张实际只关于四条腿；
  多重比较的负担被结构性地放大了。

### F5 代价实测与残段事实

umi 上 `research/jobs/E3-ROBUSTNESS-HOLDOUT/workspace`：240 个 run 目录，71 个 completion 记录，
其中 **62 completed、9 failed（命中 10800 s timeout，全部在 N=10000/128²）**，
**169 个从未尝试**（128² 下 49 个 + 256² 下全部 120 个）。

按 (population, grid) 汇总的 `elapsed_seconds`（128²，200,000 步）：

| N | n | min | median | max |
|---|---|---|---|---|
| 2000 | 24 | 306 | 389 | 1212 |
| 5000 | 24 | 1017 | 1284 | 6039 |
| 10000 | 23 | 3121 | 4151 | 10802 |

对 N 的标度强于线性（2000→10000 是 5× N，中位耗时 10.7×）：交换按 pair 施加，每粒子的对数 ∝ 密度，
故代价 ∝ N × 密度 = N²/面积。**密度的提高会把代价推成二次的**，这是 256² 腿完全没跑成的原因之一。

按 `research/state.md`：残段**不得续跑、不得与 Cycle 4 合并**，只作 provenance。E3-C4 必须是新声明、
新 seeds。

---

## 3. 估计量在腿之间的可比性

F1–F5 是关于"操作了什么"。下面三条是关于"**测的是什么**"——它们对 grid 腿是决定性的。

主指标族的三条（`S01` 之外）定义在 `landscape_study.py`：

三条主指标定义在 `landscape_study.py`，其中两条的量纲里含**格**：

```
occupancy_entropy:  H(p)/log(n_cells),  p = density/Σdensity, 只对 p>0 求和   ← 分母含 n_cells
morans_i:           四邻格（rook）权重，W = 2·(rows·(cols−1) + (rows−1)·cols)  ← 邻域 = 一格
```

这是一个**纯粹由测量定义产生的**分辨率依赖，与动力学无关。为了把它测出来而不是估算，
用 `research/src/experiments/check_metric_lattice_sensitivity.py`（本次新增的可复算工具）
在 umi 上取 E1-C4 全部 64 个 seed 的**最终快照**（`snap_00900000.csv`，条件 clustered/shuffled），
**粒子位形逐位固定不变**，只改测量格重算指标：

| metric | 测量格 | clustered | shuffled | effect (C−S) |
|---|---|---|---|---|
| `density_morans_i` | 64² | 0.75545 | 0.20093 | **+0.55451** |
| `density_morans_i` | 128² | 0.50627 | 0.23223 | +0.27404 |
| `density_morans_i` | 256² | 0.23023 | 0.14957 | +0.08066 |
| `occupancy_entropy` | 64² | 0.66387 | 0.74698 | **−0.08311** |
| `occupancy_entropy` | 128² | 0.64790 | 0.67135 | −0.02345 |
| `occupancy_entropy` | 256² | 0.60377 | 0.60881 | −0.00504 |

诊断口径：64 seeds、单个末帧、非尾窗均值，仅用于量化伪影量级，不是确认性估计量
（工具输出里带 `not_a_claim_input: true`）。

### F6 `density_morans_i` 的效应在加密下塌掉约 85%

同一批粒子，测量格从 64² 换到 128²，效应从 **0.5545 掉到 0.2740（−51%）**，
到 256² 只剩 **0.0807（−85%）**。机制是机械的：N=1000 在 64² 上每格约 0.24 粒子、
在 256² 上几乎全是 0/1 的二值占据，Moran's I 的信号退化为"四邻恰好同时被占"的巧合概率。
按 V1F 式的相邻级判据（相邻级效应差 ≤ ceiling = 0.02）：

```
64² → 128² 的纯测量伪影 = 0.5545 − 0.2740 = 0.2805  ≈ 14.0 × ceiling
128² → 256² 的纯测量伪影 = 0.2740 − 0.0807 = 0.1934  ≈  9.7 × ceiling
```

**光靠改测量格就会让 grid 腿以 10–14 倍超限"失败"。**

### F7 `occupancy_entropy` 的效应在加密下跨过等效区

效应从 −0.0831 变成 −0.0235（128²）到 −0.0050（256²）。相邻级纯测量伪影
`0.0831 − 0.0235 = 0.0597 ≈ 6.0 × ceiling (0.01)`；而且 128² 上的 −0.0235
已经**落进该指标的 SESOI（0.025）之内**——即在 native lattice 上，entropy 效应在 128² 就已不可判。

### F8 `resource_density_spearman_rho` 近似不变

它是每格密度与每格资源值之间的秩相关。秩相关对单调变换不变，细化不改变二者之间的单调关系，
所以它近似是分辨率不变的；残余差异来自碎格后的噪声衰减。（上表未含它，因为其"格"依赖来自噪声
而非定义；它需要在 V1I 里单独确认，见 §4.2 Leg G。）

**结论**：C2 的三条主指标里，两条按构造不具分辨率不变性，且伪影量级是冻结界与 SESOI 的
6–14 倍。所以 grid 腿的第一个问题不是"跑多少 runs"，而是"**用什么都测**"——而且必须给出
这个新定义的校准，否则无法解释任何结果。这正是证伪条件里 "depends on conflated … grid changes"
所描述的那类失败：**它会以"稳健性失败"的面目出现，实际却是测量定义的问题。**

---

## 4. 设计

### 4.1 测量格纪律（本设计最核心的新约束）

把 **dx 从"被测对象的一部分"变成"固定的测量仪器"**：所有腿的指标都在**参考物理测量格**上计算，
即 100×100 物理区域上的 64×64 格（参考工作点的格）。

- **Leg G**：动力学在更细 dx 上跑，测量时把快照 bin 回参考格（同物理面积）→ 指标定义不变，
  变化只来自动力学。
- **Leg S**：动力学在更大域上跑，测量取自**瓦片化的参考尺寸窗口**（每个 100×100 瓦片，
  按域平铺），在瓦片间平均 → 指标定义不变，且样本更多（提高精度）。
- **Leg D / Leg H**：域与格都不变，测量格不变。

同时把 native-lattice 的指标作为**诊断**一并报告，用来**量化**伪影大小（F6/F7 已实测：
不加这条纪律，grid 腿仅因测量格就会以 6–14 倍于冻结界的幅度"失败"）。诊断不参与判据。

这条纪律的直接后果：若 grid 腿在参考格上通过、而在 native 格上失败，报告出来的是
**"测量定义的分辨率敏感性"**，不是稳健性失败。这点必须在设计里就写明，否则会被误读为对 C2 的
反证。F6/F7 的实测还给出一个必须写进 findings 的事实：**`density_morans_i` 与 `occupancy_entropy`
不是分辨率不变的量**，其效应只在固定测量格下才有跨分辨率的可比性。

### 4.2 四条腿

每条腿给出：变什么、固定什么、**结构预测**、以及失败意味着什么。区分这两类很关键——
前三条腿的预测是"不变"，失败指向**实现或估计量缺陷**；只有 Leg H 的失败是科学发现。

#### Leg S — system size（有限尺寸标度）

- **变**：域线性尺度 L ∈ {100, 200}；格 ∝ L（dx 固定 = 1.5625）；N ∝ L²（密度固定 = 0.1）。
- **固定**：dt、total_time、温度、`interaction_range`、交换 k、以及**景观的物理尺度**。
- **必须先解决的事**：现行 `sigma_fraction`（`landscape_study.py:28`）是**域相对**的，
  `mgrid[0:1:complex(rows)]` 亦然。直接放大域会同时放大势阱宽度，于是
  `interaction_range / 井宽` 这个无量纲比改变——**改的是物理，不是尺寸**。
  标准的有限尺寸标度读法要求：井宽以**世界单位**固定、井数 ∝ 面积（否则单位面积内的井数随域
  下降，景观统计不再平移不变）。这需要景观生成器的一个扩展（绝对井宽 + 井数按面积）。
- **替代**：若不做该扩展，只能采用"相似放大"（域、格、N、景观一起 ×2）。那测的是**相似不变性**，
  而 `interaction_range` 保持世界单位不变，所以严格说仍不是纯尺寸改变。主张文本需相应收窄。
- **结构预测**：不变（局域统计量与域尺寸无关；N 增大只减小噪声）。
- **失败意味着**：实现里存在被误当作尺度不变的世界单位常量（`CellList` 的 `cell_size`、
  `interaction_range` 与井宽之比），或瓦片估计量归一化有误。是**缺陷**，不是科学发现。

#### Leg D — density

- **变**：N ∈ {250, 1000, 4000}（密度 0.025 / 0.1 / 0.4），域与格固定。
- **固定**：其余全部。
- **关键发现**：交换核**按 pair 施加**（`model-specification-c4.md` §5.1–5.2），
  每粒子的对数 ∝ 密度。所以密度 ×4 会把财富混合速率提高约 4×，**财富族的稳态分布必然改变**。
  密度腿因此**只能对空间族**做稳健性断言。
  - 选项 (i)：保持 k = 0.5 锁定值，声明密度腿只覆盖空间族；
  - 选项 (ii)：按密度归一 `k_eff = k_ref · ρ_ref/ρ`，固定每粒子混合率，使密度腿成为纯密度改变。
    代价是 k 在该腿内不再是锁定常数，需在 E3 lock 里单独声明。
- **结构预测**：空间族不变。位置只由地形势与 Langevin 噪声决定（`social_strength=0`，
  `model-specification-c4.md` §4.2），且位置对一切财富类因子外生（§5.9 的实证恒等）。
- **失败意味着**：实现或估计量问题；若不做 k 归一，则财富族确实变了——但那正是被指名的混淆，
  必须一开始就声明，不能在事后解释。

#### Leg G — grid discretization

- **变**：dx ∈ {1.5625, 0.78125}（64²/128²，视 §6 决定是否加 0.390625 = 256²），域固定 100×100，N=1000 固定。
- **固定**：所有物理参数与 dt。
- **前提（必须先做）**：**dx 轴的数值校准**。V1F 冻结的 `discretization.smooth/clustered/shuffled`
  各指标的 ceiling（rho/Moran 0.02，entropy/gini 0.01）是 **dt 轴**的
  （`timesteps: {coarse: 0.02, fine: 0.01, finest: 0.005}`），对 dx **没有 provenance**。
  需要一次结构化同型的扩展——`V1I-SPATIAL-CALIBRATION-C4`：在参考工作点上把 dx 从 64² 细化到
  128²（及 256²），为三条主指标**在参考测量格上**冻结"空间离散化 ceiling"，结构照
  `coarse_vs_fine` / `fine_vs_finest` / `ceiling` 写。V1I 必须同时记录 native-lattice 的同一比较，
  以把 F6/F7 的伪影与真正的 dx 动力学效应分开。
- **判据**：各级效应（**在参考测量格上**）作配对差 `Δ(dx) = effect(dx) − effect(reference)`，
  要求冻结界内的等价性；同时各级效应同号且区间排除零。
- **实现核对（已做，作为前置证据）**：
  - `TerrainGrid::gradient` 用 `eps = cellsize·0.5` 的中心差分并除以 `2·eps`
    → 物理梯度已按 dx 正确归一，加密**不会**人为放大力的量级 ✔（该归一本身是二阶精度，所以
    加密会减小离散误差——这正是 grid 腿要量化的东西）；
  - `CellList::init` 的 cell size = `max(interaction_range, density_radius, exchange_cutoff)`
    （`main.cpp:249`），与地形格无关 → 交换邻域不随 dx 改变 ✔；
  - `TerrainGrid::elevation` 双线性插值，加密后插值更准 ✔；
  - 但 `TerrainGrid::potential` 减的是 `h_min_`（**该分辨率数组**的最小值），跨分辨率不可比。
    它只用于报告的势能诊断（生产走 `grid_terrain_potential` 的绝对值形式），所以**不影响动力学**，
    但该诊断量在 grid 腿里不可跨级比较，需另做归一或只作定性报告。

#### Leg H — holdout landscape family

- **变**：`gaussian_mixture` → `correlated_random_field`。
  E1-C4 与 V1F 用的是前者（`run_landscape_study.py:741` 的 `make_matched_landscapes(shape, seed)`
  取默认族），所以 CRF 是真正未参与过参数选择的保留族。
- **固定**：其余全部；dx 取参考。
- **结构预测**：方向保持。这是四条腿里唯一的**真泛化检验**。
- **不可进 grid 腿**：`generate_correlated_random_resource` 的核用
  `correlation_fraction × rows × fftfreq(rows)`（`landscape_study.py:80-82`）。由于
  `rows·fftfreq(rows)` 恰是整数波数，相关长度以**格**为单位。加密网格会把该族的物理相关长度减半
  → 变成**另一个景观**。把 CRF 放进 grid 腿会再次把 dx 与景观尺度混起来（与 F1/F2 同型）。

### 4.3 判据形式

- 每腿给出配对差 `Δ_leg` 的 bootstrap 95% 区间。
- **方向**：各水平效应同号，且各水平区间排除 0。
- **不变性腿**（S、D，以及 G 的离散化差）：等价性判据——`|Δ|` 的区间**上界** ≤ 冻结界（TOST 型），
  而不是"没有显著差异"。
- **泛化腿**（H）：效应区间落在冻结等效区之外（与 E1-C4 同形）。
- **conflation 条款做成结构性 Gate**（§4.4 P4）：断言每腿的实际 `run_specs` 只在其声明的那一维上
  变化。任一越界即 `inconclusive`。这把证伪条件的 "depends on conflated … changes" 变成机器可查的东西，
  而不是靠叙述保证。

### 4.4 Gate

| Gate | 内容 | 失败后果 |
|------|------|---------|
| P1 结构 | 每腿内 matched-input（直方图、总量、可达格数）逐 seed；两条件初始完整相态逐 seed 相同；观测层数与配置声明一致 | inconclusive |
| P2 稳态/精度 | 沿用 E1-C4 的 condition-ensemble 与相邻窗口冻结界 | inconclusive |
| P3 可比性 | 把 E2-C4 的 P4（`zero_wealth_fraction`、`wealth_variance`、`mean_wealth` ±10%）推广到**跨腿对参考**；任一腿的财富分布离开带 → 该腿财富族 inconclusive | 该腿财富族 inconclusive |
| P4 conflation | §4.3 的结构断言：每腿只在声明的那一维变化 | inconclusive |

四个 Gate 全部通过才进入判据。

### 4.5 R 与预算

R 由 V1E/V1F 的方差与 N 的标度规则预注册，取 2 的幂（照 E1-C4 §2 的方法），**不使用任何 E3 效应**。
标度规则需在 §6 定夺后写入；其中 Leg S 因 N 增大而噪声更小、Leg D 的低密度级因交换对更少而
财富族方差更大，两者的 R 可能不同——这种按**方差**（而非按预期效应）分配 R 是合法的预注册，
但必须写下规则再取值。

预算（按实测折算，参考工作点 900,000 步）：

- 参考级（64²/N=1000）：E1-C4 实测 128 runs / 34.97 CPU-h，即约 **984 s/run 均值、3655 s 最大**。
- Leg G：N 不变 → 每级约与参考同量级，128²/256² 略增（地形查表与插值开销）。
- Leg S：域 ×2 → N ×4 → 约 4× 参考；若加到 ×4（域 400²/256²/N=16000）则约 16×，
  **单 run 会显著超过 10800 s 的既有 timeout**，需相应提高 timeout 或把该腿收到 2 级。
- Leg D：代价 ∝ N × 密度 = N²/面积 → N=4000 约 16× 参考（不是 4×）。这是 F5 那条二次标度的直接后果。

总量级与 wall-hours 在 §6 定夺腿数与级数后填入。**残段不续跑、不合并**；E3-C4 用全新 job 与 seeds。

### 4.6 Seeds

新 seed 池，经 `seeds-audit` 的台账强制与一切已用 seed 不相交（含 E1-C4 的 64 个、E2-C4 的 16 个、
pilot 的 8 个、以及各校准 job）。生成规则照 E2-C4 的做法：在窗口内取最小的未用素数，按腿与级
分配固定顺序；生成后写入 `seeds.txt` 并复算校验。

---

## 5. 不声称的东西与残余风险

- 不声称任何**幅度**泛化，只声称方向与不变性（C4 的措辞是 "retains direction"）。
- 不替换失败水平、不追加到显著、不删减到显著。
- **Leg G 的测量格纪律会改变"grid 腿通过"的含义**：它证明的是"在固定测量定义下，动力学对 dx 稳健"，
  不是"所有指标都对 dx 稳健"。F6/F7 已经说明后者为假。这条要在论文与 findings 里同时写明。
- **Leg S 若不扩展景观生成器**，它退化为相似不变性检查，主张文本须收窄。
- **Leg D 若不归一 k**，其财富族结论不可用；只能断言空间族。
- 残段的 62 个 completed run 是 Cycle 3 数值体制下的产物，**不进入任何 Cycle 4 判据**。

---

## 6. 待定夺

1. **C4 覆盖哪些效应**：只覆盖 C2（clustered vs shuffled 的景观效应），还是也覆盖 C3 的通道分解？
   C4 的措辞是 "any supported Cycle 4 landscape effect"，C2 是其自然所指，C3 是通道分解而非
   景观效应本身。
2. **Leg G 是否需要 V1I 空间校准**：做一次 dx 轴校准（贵，但使 grid 腿可解释），
   还是承认 grid 腿不可做、把 C4 收窄为三条腿？
3. **Leg S 的景观生成器扩展**：做（绝对井宽 + 井数按面积，有限尺寸标度的正确读法），
   还是接受相似放大并在主张里收窄？
4. **Leg D 的交换率**：保持 k 锁定并只断言空间族（i），还是按密度归一并把 k 的归一写入 E3 lock（ii）？
5. **腿的级数**：Leg G 用 2 级（64²/128²）还是 3 级（加 256²）？Leg S 用 2 级（×1/×2）还是 3 级？
   Leg D 的密度级取值？
6. **R**：按方差标度规则从 V1E/V1F 推出（给出规则与出处），还是为了让跨腿可比而统一取参考级的 R？
