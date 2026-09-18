# E2-C4 pilot：预注册（非证据；只读方差与可比性）

日期：2026-09-18。状态：**设计已完成；三项判据待定夺（§7）；定夺前不得提交**。
上下位文档：[e2-cycle4-channel-design.md](e2-cycle4-channel-design.md)（设计，§4 判据 / §8 统计契约）、
[e2-cycle4-seed-pool-decision.md](e2-cycle4-seed-pool-decision.md)（seed 窗口判据）、
[e2-cycle4-sesoi-decision.md](e2-cycle4-sesoi-decision.md)（SESOI 判据简报，**待定夺**）。

本文件是 pilot 的**预注册**：判定式、配置、seed 与禁止项都在提交前写死。pilot 的结果是
**非证据**的——它不产出任何效应方向或大小，只产出**离散度**与**可比性**两类量，用来冻结
正式运行的 R（seed 数）。

## 1. 为什么要 pilot

`C2-LANDSCAPE-C4` 的 R = 64 是为**配对景观对比**的估计量定的（V1ED → V1F 链条），而 E2-C4 的
估计量是**财富结构**在两个完全不同的对比上的配对差，且运行体制不同（力关、`social_strength = 0`）。
设计 §8 明确禁止继承 64：R 必须由 E2-C4 自己的方差决定。pilot 就是采这个方差的唯一一轮。

**pilot 能做与不能做。**

| 能做 | 不能做 |
|---|---|
| 量出三个预注册对比上配对差的**样本 SD** 与上界 SD（V1ED 规则） | 报告任何对比的**均值/方向/大小** |
| 量出 P4 三个政策量在真实体制下的实测值 | 用来事后调 band、调单元、调 Δ |
| 确认 P1 恒等护栏在新版源项/交换核下仍成立 | 被引用为任何 C3-CHANNELS-C4 的证据 |

**读数的划分（本 pilot 的核心纪律）**：**护栏量报告水平，估计量只报告离散度**。

- `mean_wealth`、`zero_wealth_fraction`、`wealth_variance` 的量级以**逐单元水平**形式报告——
  P4 判据本身就是逐单元水平（§4 P4 第 1/2 条），不报就无法执行该 Gate；这三个指标
  **不承载任何主张**（`claim_eligible = false`，理由见设计 §15 与 §15.5）。
- `wealth_gini`、`wealth_variance` 作为**估计量**时只报告配对差的 SD，**不报告配对差均值**。
  因此正式运行前，两个估计量的方向在项目内是**未读**的。

## 2. 预注册配置

**单元（5 个，逐字取自 `run_landscape_study.E2_C4_UNITS`，不另立一套）**

| 单元 | landscape | `d` | `base` | 角色 |
|---|---:|---:|---:|---|
| `clustered-d0.02` | clustered | 0.02 | 0.010 | P2 主对比处理组 / P3 `D_ref` |
| `shuffled-d0.02` | shuffled | 0.02 | 0.010 | P2 主对比对照组 |
| `flat-d0.02` | flat | 0.02 | 0.010 | P2 参考对比（不承载主张） |
| `clustered-d0.01` | clustered | 0.01 | 0.005 | P3 低汇速率端 |
| `clustered-d0.04` | clustered | 0.04 | 0.020 | P3 高汇速率端 |

全部单元 `terrain_force_enabled = false`、`terrain_production_enabled = true`、
`social_strength = 0`（约束 1/3，提交期由 `validate_e2_c4_structure` fail-fast）。

**预注册对比（3 个，与 `aggregate_e2_c4` 的构造逐字一致）**

| 标签 | 处理 − 对照 | 承载主张 |
|---|---|---|
| `clustered-minus-shuffled` | `clustered-d0.02` − `shuffled-d0.02` | 是（P2 主对比） |
| `clustered-minus-flat` | `clustered-d0.02` − `flat-d0.02` | 否（参考角色，不进 Holm 家族） |
| `d0.04-minus-d0.01` | `clustered-d0.04` − `clustered-d0.01` | 是（P3） |

**seed（8 个，全新）**

`12301, 12323, 12329, 12343, 12347, 12373, 12377, 12379`

即冻结窗口 `[12300, 13000]` 中**最小的 8 个未用素数**（`seeds-audit --pool-min 12300
--pool-max 13000 --propose 8` 的输出）。窗口判据见 seed-pool 决策文；窗口内共 77 个未用素数，
pilot 取 8 个后仍余 69，足够正式运行至 R = 64。**pilot 与正式的 seed 子集互不相交**，
依据是 V1P/V1 的先例（pilot 跑在自己的 seed 上）。

**协议常量（逐项 pin，与 `E1-MATCHED-LANDSCAPES-C4/config.json` 交叉核对）**

`temperature = 0.5`、`dt = 0.005`、`total_time = 4500.0`、`output_time_interval = 5.0`、
`steady_snapshots = 144`、`population = 1000`、`grid_shape = [64, 64]`、
`bounds = [0, 100, 0, 100]`、`friction = 1.0`、`interaction_range = 2.5`、
`exchange_rate = 0.5`、`exchange_noise_strength = 0.05`、`exchange_reversion_rate = 1.0`、
`epsilon_log_sigma = 0.5`、`wealth_log_sigma = 0.01`、`consumption_rate = 0.0`、
`terrain_force_scale = 1.0`、`terrain_production_scale = 1.0`、`w_ref/mean_wealth = 5.0`、
`ranks = 1`、`mpi_enabled = false`、`omp_threads = 1`、`confirmative_mode = true`、
`strict_numerics = true`。
与 E1-C4 共享的键由脚本逐字比对 E1-C4 的**已入库** config，任一处不同即拒绝运行——
协议漂移会让方差不可比。

**binary 绑定**

`research/jobs/V0G-SIMULATOR-TESTS-C4/workspace/build-off/src/politeia`，
sha256 必须等于参数锁 `numerical_calibration.reference_binary_sha256 =
87eafa4e1e9b0ca24d45b49eb6508f45f07bcd4f67cc72f436210f0e8d7ddee3`（与 E1-C4 config 的
`binary_sha256` 一致）。pilot 问的是"**这个** binary 上的方差"，换 binary 则方差作废。

## 3. 预注册判定式

Pilot 的 job `pass` = 三个模块全部成立。任一不成立都是**实现问题**，必须修好重跑，
不得作为结果报告。

### 3.1 P1 恒等护栏（fail-fast，非科学检验）

对每个 seed，`occupancy_entropy` 与 `density_morans_i` 在 `clustered/shuffled/flat`
三单元之间必须**逐位相等**（`format(x, ".17g")`）。`resource_density_spearman_rho`
**允许**不同（它依赖资源场，且在常量 `flat` 上未定义），不参与本护栏。

任一处不等 ⇒ 位置被财富污染或存在非确定性 ⇒ **拒绝运行**，不写任何方差表。
判据、实现与错误措辞沿用 `aggregate_e2_c4` 的 P1 块。

### 3.2 P4 可比性（逐单元，只报告不 gate pilot）

用与正式分析**同一段代码**（`_e2_c4_comparability`）与**同一组冻结政策量**（§4 P4）：

| 政策量 | 冻结值 | 来源 |
|---|---|---|
| `comparability_zero_wealth_fraction_max` | **待定夺**（见 SESOI 简报 §4） | 设计 §4 P4 第 1 条 |
| `comparability_wealth_variance_min` | **待定夺**（同上） | 设计 §4 P4 第 1 条 |
| `comparability_mean_wealth_relative_band` | `0.10` | 2026-09-17 定夺并冻结（§4 P4 第 2 条） |

P4 的 `pass` **不 gate pilot 本身**（否则会把"体制不可比"误报成"实现失败"），但它
**gate lock**：若 pilot 显示某个组的单元间水平偏差超出 ±10%，必须在 E2 lock 冻结**之前**
收窄该对比的射程或改正体制，而不是投完预算再发现 inconclusive（设计 §15.5 的推论）。
pilot 报告必须给出逐单元 `mean_wealth`、`relative_deviations`、`max_relative_deviation`、
以及两个组（P2 三单元 / P3 三单元）各自的判定。

### 3.3 方差 → R（只报告离散度）

对 3 个对比 × 4 个指标（`wealth_gini`、`wealth_variance`、`zero_wealth_fraction`、
`mean_wealth`）计算配对差，并报出（**不含均值**）：

- `paired_sample_sd`（`n − 1` 分母）；
- `upper_sample_sd`：`sample_sd · sqrt((n−1) / chi2.ppf(upper_sd_alpha, n−1))`，
  `upper_sd_alpha = 0.1`（沿用 V1ED 的单侧 90% 上界，`n = 8`）；
- `required_replicates_at(delta)` 的**规则**（不在 pilot 里求值，见 §4）。

**为什么只报 SD 就够。** 正式运行的检验统计量是配对差的 2·SE，而 `SE = SD/sqrt(R)`；
R 只依赖 SD，不依赖均值。所以"读 SD"与"读效应"是可分离的，pilot 只做前者。

**为什么用上界 SD 而不是点估计。** `n = 8` 时样本 SD 本身很宽（`sd_upper/sd ≈ 1.6`），
用点估计会系统性低估 R。V1ED 的规则正是为此设计：取上界、再上取 2 的幂。两者叠加后的
保守度是预注册的，不是事后调的。

### 3.4 禁止项

- **不得**在 pilot 报告中出现任何对比的配对差均值、方向、显著性、p 值或区间。
- **不得**用 pilot 的读数选择 Δ（SESOI）：Δ 是科学相关性判断，与实测方差独立，须由
  SESOI 告判据单独定夺，且定夺时 pilot 的 SD 只用于算 R，不得回改 Δ。
- **不得**因 pilot 的 P4 结论而调 `comparability_*` 三个政策量；超带只能**收窄射程**
  （把该对比标为 inconclusive 并事先登记），不得放宽带宽或删单元。
- **不得**把 pilot 的 run 与正式运行的 run 合并进同一个分析（seed 不相交、体制相同，
  但合并会把非证据样本混进证据）。
- **不得**在 pilot 上宣称任何 C3-CHANNELS-C4 结论。

## 4. R 的冻结规则（pilot 完成后、lock 之前）

R 是两个独立输入的**函数**，故分两步：

1. **Δ（SESOI）** 由 SESOI 判据简报定夺并冻结（`wealth_gini`、`wealth_variance`；
   P3 使用同一对值，理由见简报）。这一步**不看** pilot 数据。
2. **R** 由 pilot 的 `upper_sample_sd` 与已冻结的 Δ 机械求出：

```
R = next_power_of_two( max over (claim-bearing metric, contrast) of
        max(3, ceil( (2 · upper_sample_sd / Δ)² )) )
```

`next_power_of_two` 与 `max(3, ·)` 沿用 V1ED 的 `_required_replicates` /
`_next_power_of_two`（V1ED 用它给出 64）。只对**承载主张**的对比
（`clustered-minus-shuffled` 与 `d0.04-minus-d0.01`）与**claim-eligible** 的指标
（`wealth_gini`、`wealth_variance`，见设计 §15）取最大值；参考对比
`clustered-minus-flat` 与另外两个非估计量指标不进该最大值。
`wealth_gini` 与 `wealth_variance` 共享同一个 R（设计 §14：同一批配对差上做推断，故
SESOI 与 R 都对同一套 run 生效）。

R 一旦冻结即写入 E2 lock，**不得**在正式结果出现后更改；且 R 只由 Δ 与 pilot 的 SD 决定，
两者都在看到任何效应方向之前写下。

## 5. 预算

40 runs = 5 单元 × 8 seed，按 V1E 实测约 1,242 秒/run：约 **13.8 CPU 小时 ≈ 8 路 1.7 墙钟小时**。
执行方式：`jobctl` 提交、`preflight` 通过后运行、完成后 `jobctl reconcile`，
重产物写入 `research/jobs/E2-C4-PILOT/workspace/`。

## 6. 实现要点

- 新脚本 `research/src/experiments/run_e2_c4_pilot.py`，结构照 `run_v1g_order_thermal.py`：
  `_require_umi()` → 校验 config（协议 pin、单元逐字、seed 逐字）→ 校验 binary sha →
  复用 `prepare_inputs` / `execute_runs` / `analyze_runs` → 只算 §3 的三块 → 写
  `pilot_variance_report.json`。
- **不能**走 `run_landscape_study.py --experiment E2-CHANNEL-ABLATION-C4`：那条路径要求
  **final** 参数锁（`validate_parameter_lock(require_final=True)`），而 E2 lock 是 pilot 与
  R 的**下游**。这也是为什么 pilot 需要自己的脚本，而不是给共享分析器加一个开关——
  共享分析器会算出全部效应，而那正是 pilot 不该读的东西。
- 复用但**不重写**判据：P1 恒等与 P4 可比性直接调用共享实现，避免"pilot 的判据"与
  "正式的判据"漂移成两套。
- 纯函数化：`pilot_variance(rows_by_unit) -> {contrast: {metric: sd}}` 与
  `p1_identity_violations(rows)`、`require_protocol_match(config, reference)` 都是
  无 IO 的纯函数，便于变异检验。
- 记录：完成后 `jobctl reconcile` + 入库结论产物（`pilot_variance_report.json`）与
  由它机械导出的 `result.json` / `manifest.json`。

### 要写的测试（含变异检验）

1. 报告里**没有**任何对比均值/方向/区间字段（结构性禁止，而不是靠人自觉）；
2. 配对差 SD 与手算一致（含 `n−1` 分母与上界 SD 的 chi² 因子）；
3. P1 恒等任一位不等 ⇒ 拒绝运行且不写方差表；
4. 协议常量与 E1-C4 已入库 config 不一致 ⇒ 拒绝运行；
5. 单元集合/参数与 `E2_C4_UNITS` 不一致 ⇒ 拒绝运行；
6. seed 不是窗口内未用素数、或有重复、或与正式集相交 ⇒ 拒绝运行；
7. binary sha 不等于锁里的 reference binary ⇒ 拒绝运行；
8. **变异检验**：改动任一单元的 `d` 或 `base`，或把 SD 的 `n−1` 分母改成 `n`，
   或把上界 SD 的 chi² 因子去掉 ⇒ 至少一项测试失败。

## 7. 未决项（提交前必须关闭）

| 项 | 状态 | 阻塞 |
|---|---|---|
| `scientific_sesoi`（`wealth_gini`、`wealth_variance`） | **待定夺**，判据简报已备 | R 的最终值；claim-eligible |
| `comparability_zero_wealth_fraction_max` | **待定夺**（简报给候选） | pilot 报告里 P4 第 1 条的判定 |
| `comparability_wealth_variance_min` | **待定夺**（同上） | 同上 |
| `wealth_variance` 的数值上限 | **已冻结**：`0.056828569227561854`（V1H） | — |
| seed 窗口 | **已定**：`12300–13000`（待写入 lock） | — |

三个待定夺项都不阻塞 pilot 的**运行**，只阻塞 pilot 报告的**判定**与之后的 R；但按设计
§8 的纪律，pilot 报告的判据必须在提交前写死，故这三项须在**提交前**定夺。

## 8. 已考虑并否决的替代方案

| 替代 | 否决理由 |
|---|---|
| 直接沿用 E1-C4/E2 的力**开**存档数据估方差 | 体制不同（力开、`social_strength > 0`）：那是"景观改变人口分布"通道的方差，不是 E2-C4 的单通道方差；用它定 R 是把 R 建立在另一个实验上 |
| 继承 R = 64 | 设计 §8 明确禁止；64 是配对景观对比的估计量，与财富结构的两个对比不同 |
| 用点估计 SD 而不加上界 | `n = 8` 时系统性低估 R；V1ED 的先例就是踩过这个 |
| 加一个"pilot 模式"开关到共享分析器 | 共享分析器会算出全部效应（P2/P3 的均值与区间），而那正是 pilot 不该读的；分开脚本才能让"不读方向"成为结构性质 |
| 让 pilot 同时冻结 SESOI | Δ 是科学相关性判断，让它读实测方差会把"可检测"与"有意义"混为一谈 |
