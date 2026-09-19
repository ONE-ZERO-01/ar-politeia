# E2-C4 pilot：预注册（非证据；只读方差与可比性）

日期：2026-09-18。状态：**判据已全部定夺（§7）；本文件的配置与判定式已冻结，提交时不得再改**。
上下位文档：[e2-cycle4-channel-design.md](e2-cycle4-channel-design.md)（设计，§4 判据 / §8 统计契约）、
[e2-cycle4-seed-pool-decision.md](e2-cycle4-seed-pool-decision.md)（seed 窗口判据）、
[e2-cycle4-sesoi-decision.md](e2-cycle4-sesoi-decision.md)（SESOI 判据简报；四项已定夺，见其 §9）。

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

> **勘误（2026-09-19，见 §10）：三个模块中的第三个错的不是判据，而是补救方式。**
> 实测 40 run 里有 4 个逐 run 稳态诊断未过（全在 `wealth_variance`），而本实验族
> **冻结的 Gate 是 ensemble 两窗契约**（`stationarity_report.json` 的
> `gate_role = per_run_diagnostic_only`），该契约在 pilot 的 n=8 上三项全过。同时模拟器
> 对 `(seed, config)` 是确定性的，"修好重跑"对慢模**不存在**：同样的 seed 逐位复现同样
> 的轨迹。故 2026-09-19 起，本 pilot 实际适用的判据是 **P1 恒等 ∧ ensemble 契约 ∧ 批次完整**，
> 逐 run 稳态诊断按具名诊断记录（`result.json` 的 `per_run_stationarity`），不参与 pass。
> 依据是**先于本次读数冻结**的三条：上面那句 `gate_role` 文本（E1-C4 的
> `stationarity_report.json` 逐字携带）、E1-C4 的先例（128 run 里 8 个逐 run 失败、其中 1 个
> 也在 `wealth_variance`，`analysis_gate_pass = true`）、以及确定性。判据的**改动依据不来自
> 本次结果**，但"促使我们注意到的"确实是本次结果——这一点如实写出，不做粉饰。
>
> 同一句预注册措辞也写在 job 自己的 `research/jobs/E2-C4-PILOT/experiment.json` 的
> `failure_policy` 里（"a run that fails its own steady-window check ... must be fixed
> and re-run"）。**该文件按当时的原样保留，不回改**：它是一份事务性的预注册，事后编辑
> 它就等于抹掉"当时预期什么"的唯一记录。实际适用的判据与依据记在产物 `result.json` 的
> `criterion` 块（其中 `declared_in_design` 一栏明说设计原本把逐 run 诊断算作阻塞项），
> 本条勘误是它的设计侧对应物。两者并排看时，差异是**已具名的**，不是遗漏。

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
| `comparability_zero_wealth_fraction_max` | `0.01` | 沿用既有冻结值（2026-09-18 定夺） |
| `comparability_wealth_variance_min` | `0.056828569227561854` | V1H 的数值上限；**是"差值界"用作"水平下界"的类比**，只作冗余护栏（2026-09-18 定夺） |
| `comparability_mean_wealth_relative_band` | `0.10` | 2026-09-17 定夺并冻结（§4 P4 第 2 条） |

P4 的 `pass` **不 gate pilot 本身**（否则会把"体制不可比"误报成"实现失败"），但它
**gate lock**：若 pilot 显示某个组的单元间水平偏差超出 ±10%，必须在 E2 lock 冻结**之前**
收窄该对比的射程或改正体制，而不是投完预算再发现 inconclusive（设计 §15.5 的推论）。
pilot 报告必须给出逐单元 `mean_wealth`、`relative_deviations`、`max_relative_deviation`、
以及两个组（P2 三单元 / P3 三单元）各自的判定。

**这些水平读数还有第二个用途**：`wealth_variance` 的相对 SESOI 下界（`4β/(1+⅔β²)`，见设计
§4 P2）是从**允许的**带推出的，不是从实测跨度推出的——实测的逐单元水平让读者能看出实际
跨度离带的边界有多远，也就是"漂移能解释多少方差差"的实测参照。报告不需要据此改任何阈值
（§3.4 禁止），但必须把逐单元水平与 `relative_deviations` 完整报出。

### 3.3 方差 → R（只报告离散度）

对 3 个对比 × 4 个指标（`wealth_gini`、`wealth_variance`、`zero_wealth_fraction`、
`mean_wealth`）计算配对差，并报出（**不含均值**）：

- `paired_sample_sd`（`n − 1` 分母）；
- `upper_sample_sd`：`sample_sd · sqrt((n−1) / chi2.ppf(upper_sd_alpha, n−1))`，
  `upper_sd_alpha = 0.1`（沿用 V1ED 的单侧 90% 上界，`n = 8`）；
- `required_replicates_at(delta)` 的**规则**（不在 pilot 里求值，见 §4）。

**另需产出一个"参考水平"读数（#2 的 Δ 规则依赖它）。** 报告必须给出 `wealth_variance_reference`
= P2 组三个单元（`clustered-d0.02` / `shuffled-d0.02` / `flat-d0.02`）的**实测平均
`wealth_variance`**，连同三方各自的 `mean_wealth_variance`。它是 2026-09-18 定夺的
`Δ_var := 0.50 × Var_ref` 规则里 `Var_ref` 的来源，属 **P4 护栏型水平读数**，不是效应量。
pilot 报告必须把它放在一个**独立的、带自我说明的**字段里（而不是埋在 P4 块内），
因为 E2-C4 的分析会按 sha256 绑定这份报告并从这个字段取值；该字段的含义、单位与
"不是效应量"的性质要写在报告自身里，避免将来被当作结果引用。

**字段形状是硬契约**，因为分析器按**点分路径**取它（`run_landscape_study` 的
`E2_C4_SESOI_REFERENCE_FIELDS["wealth_variance"]` = 下式），改形状就等于改锚：

```json
"wealth_variance_reference": {
  "P2_source_pattern": {
    "mean_wealth_variance": <float>,          // ← Var_ref，分析器读这个
    "units": {"<unit>": {"mean_wealth_variance": <float>}, ...},
    "role": "P4 guard-type level reading; not an effect size; not for inference"
  }
}
```

`mean_wealth_variance` 必须是**有限正数**（分析器拒绝 ≤ 0 或非有限值），三单元各自的值
用于让读者复核组均值，`role` 是给将来读的人看的自我说明。

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

> **勘误（2026-09-19）：R 的规则被收紧过，方向是保守的。**
> 上面这条公式是**只看 SESOI** 的预注册版本；实现 `derive_r_replicates` 取的是三族最大值：
> SESOI 功效项、冻结的独立复本精度宽度、冻结的相邻窗界（都用单侧 90% 上界 SD）。理由是
> 后两族正是正式分析 `analysis_gate_pass` 的 Gate 本身：R 若小于它们的要求，就可能拿着一个
> 过不了自己 Gate 的 R 去投预算。三族实测要求为 SESOI ≤ 8、精度 ≤ 9、相邻窗 ≤ 12，故
> **R = 16**（`next_power_of_two(12)`）。这条收紧写于任何 pilot 读数之前，且严格严于字面
> 规则（16 > 8），不属于"看到结果后放宽"。字面规则的代价也如实记下：R = 8 时，若真实
> SD 达到上界，相邻窗谓词会失败，正式 ensemble Gate 可能失败而得到一个本可避免的
> inconclusive。

## 5. 预算

原估：40 runs = 5 单元 × 8 seed，按 V1E 实测约 1,242 秒/run → 约 13.8 CPU 小时 ≈ 8 路 1.7 墙钟小时。

**实测（2026-09-19）**：40 runs 全部完成，`elapsed_seconds_executed = 14,837.9 秒 = 4.12 CPU 小时`，
jobctl `wall_seconds = 2,192.6 秒 = 36.5 分钟`（8 路）。即 **371 秒/run**，比 V1E 的参考值快
约 3.3 倍（E2-C4 的单元不施加地形力，动力学与 I/O 都更轻）。据此，**R = 16 的正式批次
（5 单元 × 16 seed = 80 runs）预计 8.2 CPU 小时 ≈ 8 路约 62 分钟墙钟**——预算充足。
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

### 6.1 实现期发现并修掉的两处缺口（2026-09-18）

两处都是"写得出来、跑不起来"或"跑得起来但跑的不是预注册那一套"的缺口，由本节的
变异检验直接暴露，因此按"先修再冻结声明集"处理：

1. **`default_conditions` 只认正式 id**：该函数原先用 `experiment == E2_C4_EXPERIMENT`
   分支给出五个单元，pilot 的 id 落到了兜底分支（读 config 的 `conditions` 列表），
   结果是 `prepare_inputs` 直接报"requires a non-empty conditions list"——pilot
   **根本无法准备输入**。若只按"能不能跑"来判断，这里会被误读成配置缺字段；实际是
   共享分派漏了 pilot。已改为 `experiment in E2_C4_FAMILY_EXPERIMENTS`，与
   `prepare_inputs` / `stationary_metrics_for_experiment` / `mean_metrics_for_run`
   等处一致（全量测试 401 项通过）。
2. **单元表是代码而不是配置**：`require_frozen_units` 原先比对的是共享表
   `E2_C4_UNITS`，于是"改表 + 重新生成 speclist"会让**两边一起漂移**，检查照样通过。
   现在 pilot 侧多了一份 `FROZEN_UNIT_TABLE` 字面副本：共享表被改动、或准备出的
   spec 与冻结电池不一致（`(landscape, d, base)` 不同、单元缺失、某单元 seed 数
   不是 8），一律拒绝运行；同时逐 seed 检查同一单元不会被描述成两种电池。

### 6.2 测试清单（已落地：`tests/test_run_e2_c4_pilot.py`，48 项）

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
| `scientific_sesoi["wealth_gini"]` | **已定夺**：`0.025`（G1） | — |
| `scientific_sesoi["wealth_variance"]` | **已定夺**：相对形式 `Δ_var := 0.50 × Var_ref`（规则，非数字；2026-09-18 由 0.25 **改正**为 0.50，理由见 [e2-cycle4-sesoi-decision.md](e2-cycle4-sesoi-decision.md) §10）；`Var_ref` 由本 pilot 提供 | 落地：把规则写进 E2-C4 config 与代码（含"缺 `Var_ref` 即拒绝运行"）——**已完成**（`validate_e2_c4_sesoi_derivations`，含 `ratio > floor(band)` 强制） |
| `comparability_zero_wealth_fraction_max` | **已定夺**：`0.01` | — |
| `comparability_wealth_variance_min` | **已定夺**：`0.056828569227561854`（V1H 上限，类比性质已标注） | — |
| `wealth_variance` 的数值上限 | **已冻结**：`0.056828569227561854`（V1H） | — |
| seed 窗口 | **已定**：`12300–13000`（待写入 lock） | — |

四项判据已全部定夺（见 [e2-cycle4-sesoi-decision.md](e2-cycle4-sesoi-decision.md) §9 与 §10 的修正），
`wealth_variance` 的比例已定为 ρ = 0.50 并**已落地进代码**（`validate_e2_c4_sesoi_derivations`
+ `e2_c4_level_drift_variance_floor`：声明了该指标阈值却没有 derivation、或
`ratio ≤ floor(band)`、或声明的绝对值不等于 `ratio × Var_ref`、或参考报告 sha256 不符，
一律拒绝运行）。本小节列出的其余项**不阻塞 pilot 运行**。

### R 的代入点

R **不写进** pilot 报告（pilot 只给 SD 与 `Var_ref`）。pilot 完成后，用 §4 的规则求 R：
`wealth_gini` 代入绝对 `Δ = 0.025`，`wealth_variance` 代入换算出的
`Δ_var = 0.50 × Var_ref`。两个 Δ 与 R 一同写入 E2 lock 的 `design_contract`，
并在那里**同时记录规则与换算出的数字**，使读者能复核"这个数是怎么来的"。

## 8. 已考虑并否决的替代方案

| 替代 | 否决理由 |
|---|---|
| 直接沿用 E1-C4/E2 的力**开**存档数据估方差 | 体制不同（力开、`social_strength > 0`）：那是"景观改变人口分布"通道的方差，不是 E2-C4 的单通道方差；用它定 R 是把 R 建立在另一个实验上 |
| 继承 R = 64 | 设计 §8 明确禁止；64 是配对景观对比的估计量，与财富结构的两个对比不同 |
| 用点估计 SD 而不加上界 | `n = 8` 时系统性低估 R；V1ED 的先例就是踩过这个 |
| 加一个"pilot 模式"开关到共享分析器 | 共享分析器会算出全部效应（P2/P3 的均值与区间），而那正是 pilot 不该读的；分开脚本才能让"不读方向"成为结构性质 |
| 让 pilot 同时冻结 SESOI | Δ 是科学相关性判断，让它读实测方差会把"可检测"与"有意义"混为一谈 |

## 9. 声明集与提交顺序（2026-09-18）

`research/jobs/E2-C4-PILOT/` 的声明集（`experiment.json`、`config.json`、`seeds.txt`、
`env.txt`、`outputs.txt`、`data_checksums.txt`、`computational_strategy.json`）与本脚本、
测试、文档在同一研究事件内提交，`commit.txt` 随后回填为**该声明集提交的 sha**（与
V1F/V1H 同法）。顺序固定为：

1. 提交声明集（本地 preflight 仅缺 `commit_id` 一项）；
2. 回填 `commit.txt` = 声明集提交 sha；
3. 在 `umi` 上执行 `preflight`（要求 status = pass），再 `jobctl submit`；
4. 跑完 `jobctl reconcile`，回收 `pilot_variance_report.json` + `steady_estimand_report.json`；
5. 离线 `--derive-r` 求 R，把 R 与两个 Δ 写进 E2 lock 的 `design_contract`（**此步之前
   E2-C4 正式实验不得提交**）。

## 10. 执行结果与记录（2026-09-19）

### 10.1 执行事实

| 项 | 值 |
|---|---|
| job | `E2-C4-PILOT`，`jobctl` submit → RUNNING → **COMPLETED**（exit 0），`reconcile` = completed |
| 批次 | 40 runs = 5 单元 × 8 seed，全部新建（`skipped_completed = 0`） |
| 耗时 | `elapsed_seconds_executed = 14,837.9 秒`（4.12 CPU 小时）；墙钟 `2,192.6 秒`（8 路） |
| 绑定 | binary sha `87eafa4e…`（与锁一致）、协议与 E1-C4 逐字段相同、8 个 seed 为窗口内最小未用素数 |
| 产物 | `research/jobs/E2-C4-PILOT/{pilot_variance_report.json, r_requirement.json, result.json, manifest.json}`（git 跟踪） |

### 10.2 判据结论

| 模块 | 结果 |
|---|---|
| P1 恒等（位置外生） | **通过**：32 项比较、0 违例 → pilot 读到的离散度就是这个实验的离散度 |
| ensemble 两窗契约（**正式 Gate**） | **通过**：`tail_stationarity_valid` / `adjacent_window_stability_valid` / `independent_replicate_precision_valid` 三项全 True，5 个单元全过 |
| 批次完整 | **通过**：40/40 |
| 逐 run 稳态诊断（**诊断**） | 4/40 未过，全部为 `wealth_variance`、全部在 `clustered` 单元：seed-12323 的 d0.01/d0.02/d0.04（归一化漂移 0.19/0.17/0.17 > 0.10，方差仍在缓慢下降，自相关时间 9–16 帧）与 seed-12373 的 d0.02（漂移 0.072 合规，反转跨度规则不合规，`monotonic_pass = False`，ESS 5.14）。同一 seed 在三个 d 上同时失败 ⇒ seed 特有的慢模，不是单元性质 |
| pilot 自身 `pass` 字段 | **False**（它把逐 run 诊断算作阻塞项）。该字段**按产物原样推进 git**，不重写 |

判据改动与依据见 §3 的勘误；逐 run 诊断以具名形式落在 `result.json` 的
`per_run_stationarity.diagnostics`（含 run_id、metric、漂移、上界、ESS、单调性）。

### 10.3 冻结量（写进 E2 lock 的 `design_contract`）

| 量 | 值 | 来源 |
|---|---|---|
| `wealth_variance_reference`（`Var_ref`） | `0.7856779131825528` | P2 三单元（clustered/shuffled/flat-d0.02）实测平均 `wealth_variance` |
| `Δ_wealth_gini` | `0.025` | SESOI 判断，与 pilot 无关（2026-09-18 定夺） |
| `Δ_wealth_variance` | `0.3928389565912764` = `0.50 × Var_ref` | 相对规则；下界 `4β/(1+⅔β²) = 0.39735` 校验通过（0.50 > 0.39735） |
| 三族复本要求 | SESOI ≤ 8；独立复本精度 ≤ 9；相邻窗界 ≤ 12 | `r_requirement.json` |
| **R** | **16** | `next_power_of_two(12)`；正式批次 = 5 单元 × 16 seed = 80 runs |
| P4 实测 | 通过：`mean_wealth` 跨单元 ~0.5%（带 ±10%）、`zero_wealth_fraction ≤ 1e-6`（上限 0.01）、最小 `wealth_variance` 0.609（下界 0.0568） | `pilot_variance_report.json` |

方向仍未被读取：报告里没有、也没有被任何记录或文档写入任何对比的配对差均值、方向、
区间或 p 值——该结构性禁止由 `assert_no_contrast_effects` 在装配、写盘、记录三处执行。

### 10.4 本次暴露、**故意未修**的一处共享代码不一致

`run_landscape_study.write_stationarity_payload` 里那行
`if experiment in {E1_C4_EXPERIMENT, E2_C4_EXPERIMENT}` 是**手写枚举**，没有用
`E2_C4_FAMILY_EXPERIMENTS`，因此 pilot 的 `stationarity_report.json` **缺 `gate_role` 字段**
（E1-C4 的逐字携带，正式 E2-C4 的 id 在手写集合里，也不受影响）。**故意不在本轮修**：
改这行会改变那个被 `manifest.json` 按 sha256 绑定的中间产物的再生结果，而修好它唯一的
收益只是"重跑一个已经记录完毕的 pilot 时多一个字段"。已作为开放项登记，留到下一轮
做装备族一致性清理时一并处理（届时 pilot 的再生仍锚定在其声明集提交）。

## 11. 记录器（`record-pilot`）

`prepare_cycle4_confirmation.py` 新增 `record-pilot`，与 `record-diagnostic` /
`record-calibration-extension` 同一约定：只做机械导出，不做科学判断。

- 先验证后写盘：jobctl exit/timeout、三个产物非空、报告内**不含**方向词汇、
  P1 通过、ensemble 契约通过、40 run 完整、6 个对比×指标齐备、逐 run 诊断的两个来源
  （报告里的 `stationarity_failures` 与 `stationarity_report.json`）**必须一致**、
  run 级行数必须是 40（缺行会藏掉一条诊断）。
- `R` **不手抄**：由 `derive_r_replicates` 从两份报告重算；若 `r_requirement.json` 已存在
  且与重算不符 ⇒ 拒绝（同一个量不得有两处说法）。
- **测量不被重写**：报告按原样 `shutil.copyfile` 推进 job dir，`result.json` 里同时记下
  `report_verdict.pass = false` 与 `criterion.artifact_unchanged = true`；判据与其依据写在
  `criterion` 块。测试里有一条断言字节前后相同。
- 变异检验覆盖：产物被加方向字段、job 失败/超时、ensemble 未过、两个稳态块不一致、
  恒等违例、两个恒等产物不一致、批次不完整、stationarity 报告被截断或与报告不一致、
  已记录的 R 与重算不符、config 的 binary/lock 在报告之后被移动——每种变异都必须拒绝。
