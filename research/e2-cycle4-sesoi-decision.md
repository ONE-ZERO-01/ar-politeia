# E2-C4 的 `scientific_sesoi`：判据简报（**只列候选，不替 lock 定值**）

日期：2026-09-18。状态：**待研究者定夺**。
上下位文档：[e2-cycle4-channel-design.md](e2-cycle4-channel-design.md)（§4 P2/P3/P4 判据、§8 统计契约、§14/§15 推断射程）、
[e2-cycle4-pilot-design.md](e2-cycle4-pilot-design.md)（用本简报定下的 Δ 与 pilot 的 SD 一起冻结 R）。

本文件**不选值**，只把候选、每个候选的后果与理由摊开。三个待定夺项见 §7。

## 1. 这个数在哪三处起作用

| 位置 | 用法 | 代码 |
|---|---|---|
| claim 判定 | 每个指标的 `effective_claim_threshold = max(numerical_resolution_limit, scientific_sesoi)` | `aggregate_e2_c4` 的 `thresholds` |
| 样本量 R | `R = f(Δ, pilot 的配对差 SD)`；Δ 越小 R 越大 | `run_v1e_sampling_diagnostic._required_replicates` |
| claim-eligible | 指标不在 SESOI 表里 ⇒ 理由码 `missing_scientific_sesoi`，只能描述性报告 | `e2_c4_claim_ineligibility_reasons` |

**关键结构性事实：阈值是按指标、不是按对比设的。** `aggregate_e2_c4` 的 `effective_thresholds`
以指标为键，所以 P2 主对比与 P3 用**同一个 Δ**；不能给 P3 单独放宽。这不是实现细节，
是 §14 的推论：SESOI 与 R 都在同一批配对差上做推断。

**第二条结构性事实：数值上限已经是硬地板。** 阈值取 `max(limit, Δ)`，而
`wealth_variance` 的 V1H 上限是 `0.056828569227561854`。若 Δ 不超过它，SESOI 就**不产生任何
约束**，等于把该指标的判定交给数值分辨率。所以第一个判据是：
**Δ 必须显著大于该指标的数值上限，否则这个指标实际上没有科学阈值。**

## 2. 可复用的先例（全部已入库，不是新造）

| 量 | 值 | 出处 |
|---|---|---|
| E1-C4 `wealth_gini` 的 SESOI | `0.025`（绝对） | `E1-MATCHED-LANDSCAPES-C4/config.json` |
| E1-C4 空间三指标的 SESOI | `0.05 / 0.05 / 0.025` | 同上 |
| V1H `wealth_variance` 数值上限 | `0.056828569227561854` | `V1H-CALIBRATION-EXTENSION-C4/numerical_calibration_extended.json` |
| `wealth_variance` **唯一的既有阈值约定** | **相对**：`0.2` × 水平（`relative_to_larger_window_mean`） | `E1-MATCHED-LANDSCAPES-C4/config.json` 的 `independent_precision_relative_half_widths` |
| P4 水平带 | `±10%` | 设计 §4 P4 第 2 条（2026-09-17 定夺） |
| P4 `zero_wealth_fraction` 上界 | `0.01` | `adjacent_window_absolute_bounds` / `independent_precision_absolute_half_widths` |
| 上取 SD 的 α 与 2 的幂政策 | `α = 0.1`，`next_power_of_two` | `V1ED-SAMPLING-DIAGNOSTIC-C4/config.json` 与 result |
| V1ED 的实测结论 | 力开体制下 **`wealth_variance` 是限制指标**（保守估计 61 → R = 64）；`wealth_gini` 只需 **3** | `V1ED-SAMPLING-DIAGNOSTIC-C4/result.json` |
| E1-C4 力开实测 `wealth_gini` 效应与其精度 | 效应 `+0.00303`，95% CI `[−0.00043, +0.00688]` ⇒ 配对差 SD ≈ `0.0149`，2·SE ≈ `0.00365` | `E1-MATCHED-LANDSCAPES-C4/paired_effects.json` |

**读这两行时的一个精度差别（不要混用）。** V1ED 的 `61` 来自**逐条件**的
`independent_replicate_precision` 块（阈值是**相对** 0.2 × 窗内均值），而 `3` 来自
**配对** clustered/shuffled 的最细 dt 块（阈值是绝对 0.025）。两者统计量不同、不该并列比较。
它们在这里的用途只有一个：**提示 `wealth_variance` 的离散度在参考体制下远大于 `wealth_gini`，
因此 R 会由前者决定**。pilot 要产出的正是与后者同型的**配对差** SD。

**从先例读到的重要事实：R 会由 `wealth_variance` 决定，不由 `wealth_gini` 决定。**
力开体制下 `wealth_gini` 在 Δ = 0.025 下只需 3–4 个 seed（我用 §5 的 E1-C4 实测 SD 重算：
点估计 3、上界 4、上取 2 的幂 = 4），而 `wealth_variance` 需要 61 → 64。也就是说
**Δ 的选择**对 R 的影响几乎全部通过 `wealth_variance` 发生。

## 3. `wealth_gini`：候选

| 候选 | 值 | 理由 | 代价 |
|---|---|---|---|
| **G1 沿用** | `0.025` | 同一通道、同一估计量家族（Cycle 4 财富类次要家族），E1-C4 已冻结过一次；且 E1-C4 实测效应仅 `+0.00303`，远低于它——说明它不是为了让结果显著而设 | 无 |
| G2 收紧 | `0.01` | E2-C4 是单通道设计（力关、位置外生），比 E1-C4 的复合通道更干净，可以用更严的相关性门槛 | R 可能上升；但按 §2 的实测 SD，`wealth_gini` 仍不是限制指标，故实际代价≈0 |
| G3 放宽 | `0.05` | 与空间三指标同值 | 与 E1-C4 已发表的同一指标不一致，两个实验的 `wealth_gini` 阈值不同会需要解释 |

**推荐 G1**：没有新证据支持偏离，而偏离会让"同一指标在 Cycle 4 内有两个阈值"。
（`wealth_gini` 是尺度不变量，故 §4 的尺度漂移问题对它不存在。）

## 4. `wealth_variance`：为什么这个数必须**推导**而不是**选**

`wealth_variance` 与 `wealth_gini` 有一个本质差别：**Gini 对尺度不变，方差对尺度敏感。**
把财富整体乘 λ：Gini 不变，方差乘 λ²。而 E2-C4 的两个对比**都带有水平成分**：

- P2 三单元的源总量匹配，但**实测平衡水平不同**（力开时 `clustered − shuffled` 的平均财富差
  是 **+43.9%**，见 `paired_effects.json`），P4 只把它约束在 ±10% 内；
- P3 由 `s/d` 常数匹配平衡，水平成分较小，但阈值按指标统一，无法单独放宽。

因此在 ±10% 的水平带内，**一次纯尺度漂移最多能造成的相对方差变化是**
`(1.10)² − 1 = 0.21`（下界 `(0.90)² − 1 = −0.19`）。这条界是从已冻结的 P4 带**推导**出来的，
不含任何新常数，它给出一个硬下界：

> **若 Δ_var 以"占参考水平的相对比例 ρ"表示，则必须有 ρ > 0.21，否则一个通过了 P4、
> 且完全由水平漂移造成的单元间差异就能越过该阈值。**

注意这与既有约定**冲突**：§2 里 `wealth_variance` 的唯一既有阈值约定是 **ρ = 0.2**，
恰好落在 0.21 之下。也就是说，**直接沿用既有约定会让这个阈值对水平漂移失效**。
这是本简报最实质的一条发现。

（对 `wealth_gini` 不存在这个问题，Gini 尺度不变。）

## 5. `wealth_variance` 的四个候选

记 `Var_ref` 为参考水平（P2 组三个单元的实测平均方差，属 P4 护栏型**水平**读数，
与 `comparability_mean_wealth_relative_band` 用实测组均值同类；**不是效应量**）。

| 候选 | Δ_var | 理由 | 代价 |
|---|---|---|---|
| **V1 相对、ρ = 0.25** | `0.25 × Var_ref` | 是 0.21 之上**最小**的整数百分位；由 P4 带推导出的唯一硬下界来定，不是自由选择 | 需要把"相对阈值"写进判据：lock 时用 pilot 的 `Var_ref` 换算成绝对值，并把**换算规则**（而非数字）预注册 |
| V2 相对、ρ = 0.50 | `0.50 × Var_ref` | 更保守地用"水平漂移贡献的两倍以上"作门槛 | 大幅放松：R 可能降 4 倍（见 §6），科学宣称更容易——**不是**更严谨的方向 |
| V3 绝对、锚在数值上限 | `k × 0.056828…`，如 k = 8 → `0.4546` | 完全预注册、不依赖任何读数 | `k` 是任意数；且同一个绝对量在不同水平的体制里含义不同（唯一致命点：它无法随尺度缩放） |
| V4 不承载主张 | 把 `wealth_variance` 退回描述性 | 最保守；V1H 的上限照常在结果里报告 | 放弃 P2/P3 的第二个估计量；§14 的射程问题只解决一半 |

**推荐 V1**，理由：它是唯一一个"下界由已冻结的 P4 带推出、且不含自由参数"的候选。
它的代价（把阈值写成相对形式）与 P4 自己的水平带（相对形式）是同一个惯用法，不是新机制。

**V1 的一个诚实弱点**：`Var_ref` 来自 pilot 的水平读数，所以阈值不是"提交前就写死的绝对值"。
但**换算规则**可以在提交前写死（"Δ_var := 0.25 × P2 组实测平均方差"），而该读数不是效应量——
这与 P4 用实测组均值当带宽基准是同一类操作。若研究者不接受任何数据参与的阈值，
V3 或 V4 是仅有的两个替代。

## 6. Δ 对 R 的影响（`wealth_variance`，含预算后果）

按 `R = next_pow2(max(3, ceil((2·SD_upper/Δ)²)))`，`SD_upper` 为 8 seed 的上界 SD
（α = 0.1 时约为样本 SD 的 **1.57 倍**）。设样本配对 SD = `q × Var_ref`：

| `q`（SD 占参考水平的比例） | ρ = 0.20 | **ρ = 0.25** | ρ = 0.50 | ρ = 1.00 |
|---|---:|---:|---:|---:|
| 0.10 | 4 | 4 | 4 | 4 |
| 0.25 | 16 | 16 | 4 | 4 |
| 0.50 | 64 | **64** | 16 | 4 |
| 1.00 | 256 | **256** | 64 | 16 |

`q` 必须由 pilot 实测（力开体制下 V1ED 已显示 `wealth_variance` 是限制指标，提示 `q` 不会小）。
两种极端下的预算：`R = 64` → 5 × 64 = 320 runs ≈ 110 CPU 小时 ≈ 8 路 13.8 墙钟小时；
`R = 256` → 1280 runs ≈ 442 CPU 小时 ≈ 55 墙钟小时。**因此这个选择有真实的算力后果，
必须在看到效应方向之前定下。**

## 7. 需要你定夺的四个数

| # | 项 | 候选 | 我的推荐 |
|---|---|---|---|
| 1 | `scientific_sesoi["wealth_gini"]` | `0.025` / `0.01` / `0.05` | **`0.025`**（沿用 E1-C4，G1） |
| 2 | `scientific_sesoi["wealth_variance"]` 的**形式与比例** | V1（相对 ρ=0.25）/ V2（ρ=0.50）/ V3（绝对 k×0.0568）/ V4（不承载主张） | **V1，ρ = 0.25**（由 P4 带推出的下界之上最小的整数百分位） |
| 3 | `comparability_zero_wealth_fraction_max` | `0.01`（沿用）/ 由 pilot 水平读数收紧 | **`0.01`**（既有冻结约定，直接沿用；力开体制下该量在多数单元上恒为 0，故余量很大——力关体制待 pilot 确认，但该量只是非退化护栏，不承担科学判定） |
| 4 | `comparability_wealth_variance_min` | `0.056828…`（V1H 数值上限）/ `0.01` / `0.05 × Var_ref` | **`0.056828…`**，但须标明这是**类比**：V1H 的上限约束的是**差值**，用作**水平**下界是把"低于自身数值分辨率的量"视为与 0 不可区分。它只是冗余护栏（坍塌主要由 #3 捕获），不承担任何科学判定 |

## 8. 定夺之后写进哪几处

1. `research/jobs/E2-C4-PILOT/config.json`（pilot 报告的 P4 判定需要 #3/#4，#2 的规则需要 `Var_ref`）
2. pilot 的 `pilot_variance_report.json`（由它给出 `Var_ref` 与各对比的 `SD`）
3. `research/parameter_lock.e2.json` 的 `design_contract.scientific_sesoi`（R 与 Δ 一起冻结）
4. 设计 §4 P2 的估计量列表与 §8 的统计契约（把"Δ 是相对形式"这一条写明，否则读代码的人会以为它是绝对阈值）
5. 本简报末尾追加"定夺（日期）"段，与 `e2-cycle4-seed-pool-decision.md` 的写法一致

**未定夺前不得提交 pilot**：pilot 报告的 `pass` 判据必须包含已知的 P4 政策量 #3/#4，
而 §3 的纪律禁止事后改判据。
