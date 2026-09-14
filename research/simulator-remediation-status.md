# 模拟器改进台账（simulator-remediation-status）

日期：2026-09-14。状态：Cycle 4 代码级修复、顺序敏感性和非平坦步长误差界已经通过；V1C 的稳态/精度 Gate 仍失败。确认性实验尚未开始。

本文件是 `simulator-improvement-plan.md`（下称"计划"）的执行台账，按问题（S01–S11）记录证据、本次代码修改、回归测试、完成状态与残余限制。它不覆盖或修改 `plan.json`、`parameter_lock.json`、`findings.json` 与服务器任务状态；旧结果目录不变。

## 1. 可追溯基线

| 项 | 值 |
|---|---|
| 源码 commit（工作区起点） | `d4373544461bfbb7cf0047086ae83a95eaac4eb1` |
| 分支 | `codex/cycle3-validation` |
| 参数锁 | `research/parameter_lock.json`，`ar-politeia-cycle3-confirmatory-v3`，SHA-256 `034c3dd357f13d1192a887b31759dbd2b0d3f05ae50409823d00c371fa8dd36e` |
| E0 校准 | `research/jobs/E0-NUMERICS-C3/numerical_calibration.json`，SHA-256 `cf484987a3c9d63ff5276f098ae75a66312065f5bfdaef9d0588e7b9b8f9c73e` |
| 旧结果版本 | E0-NUMERICS-C3 / B0-DYNAMICS-PILOT-C3 / E1-MATCHED-LANDSCAPES / E2-CHANNEL-ABLATION（Cycle 3，均已提交）；E3-ROBUSTNESS-HOLDOUT 不完整（62 completed / 9 timeout / 169 unattempted） |
| 分析脚本版本 | `research/src/experiments/landscape_study.py`、`run_landscape_study.py`（Cycle 3） |

## 2. 问题台账

证据类别：A=代码可直接确认；B=已提交记录暴露的验证缺口；C=需实验确定影响程度。

| ID | 优先级 | 类别 | 问题 | 处置 | 完成状态 | 残余限制 |
|---|---|---|---|---|---|---|
| S01 | P0 | A | 财富没有反馈到当前空间动力学 | 重写机制解释（E2 空间零效应=结构隔离） | 待办（文档，非代码） | 需随新因果图成文 |
| S02 | P0 | A/B | 截断产生零财富后交换跳过该粒子 | 修复交换边界 + 诊断 | 本轮 | 回流是"允许"而非"必然" |
| S03 | P0 | B | Moran's I 与部分财富方差被移出稳态 Gate | 恢复 gate 指标 | 已完成（分析代码与 V1C 实测） | V1C 显示长相关时间，稳态/精度问题仍需独立诊断 |
| S04 | P0 | B | 平坦景观把 Spearman 数值误差校准成零 | 退化相关标 NaN，排除退化 SESOI | 本轮 | 非退化校准仍需 umi |
| S05 | P1 | A/C | Langevin 外叠加阈值速度缩放 | 温控诊断计数 | 本轮 | 社会力截断待完整模型验证 |
| S06 | P1 | A | OpenMP 无噪声分支遗漏摩擦 | 修复 + 回归 | 本轮 | 无 |
| S07 | P1 | A/C | 交换噪声不含 seed、用数组下标 | 稳定 GID + base_seed 子流 | 本轮 | 重排不变性需 umi 实测 |
| S08 | P1 | A/C | 固定顺序原地交换 | 三级步长 × 完整相态重排量化 | V1/V1B/V1C 顺序界均通过 | 当前参数域内已受数值误差界约束；扩大参数域需重校准 |
| S09 | P1 | A/C | E2 同时开关生产与衰减 | 明确估计对象 | 待办 | 纯生产/纯衰减分离设计 |
| S10 | P1 | C | 邻域/MPI/重启/完整模型验证不充分 | 邻域 cell 修复 + 配置校验（本轮）；MPI/checkpoint 审计待办 | 部分 | MPI/checkpoint 待审计 |
| S11 | P2 | C | 高密度交换计算成本快速增加 | 基线冻结后优化 | 待办 | 性能报告待 umi |

## 3. 本次代码级修改清单（随实现回填）

- S06：`langevin_integrator.cpp` OpenMP 无噪声分支补 `- half_dt_gamma * p[i]`。
- S02：`resource_exchange.cpp` 边界政策 + `ExchangeDiagnostics`。
- S07：`antisymmetric_sign` 改用稳定 GID + base_seed。
- S10.1：`main.cpp` cell cutoff 纳入 `exchange_cutoff`。
- S10.4：`config` 新增 `validate_config`；interval 归一化前移。
- S05：`main.cpp` 温控触发计数/最大修正。
- S04：`landscape_study.py` 退化相关标 NaN、SESOI 排除退化指标。
- S03：`run_landscape_study.py` 恢复 Moran's I / wealth_variance、新增 zero_wealth_fraction。

## 4. 复审修复（R01–R12 · 阶段 A+B 本地，2026-09-08）

复审文档：[research/simulator-review-and-repair-plan-2026-09-08.md](research/simulator-review-and-repair-plan-2026-09-08.md)。阶段 C/D（umi 数值验证、MPI/restart 完整修复、非平坦校准、新参数锁）明确延期。

| R | 处置 | 状态 |
|---|---|---|
| R01 | `landscape_study.py` 新增 `metric_status` 三态（valid/undefined/invalid）；`stationarity_diagnostics` 非有限入参结构化返回；`mean_metrics_for_run`/`analyze_runs` 不泄漏 NaN、JSON 合法 | 本地完成 |
| R02 | `aggregate_e0` 声明 required/expected_degenerate，Inf/坏值抛错，空收敛集/重复种子必失败 | 本地完成 |
| R03 | 新增 `validate_calibration_coverage` + `confirmatory_metrics_for_experiment`，运行前拦截缺 SESOI/版本不匹配 | 本地完成 |
| R04 | no-exchange 关闭 reversion；优先级 condition→global→default；`exchange_enabled` 主开关（C++ 整体跳过） | 本地完成 |
| R05 | 交换前 `std::isfinite`+负财富政策前置；`validate_particle_state` 全体检查（含无邻居粒子）；main 按阶段检查 + 非零退出；执行器失败传播已确认 | 本地完成 |
| R06 | `stationarity_diagnostics` 分层 `stationarity_pass`/`precision_pass` + 子窗口非单调；E0 纳入 `zero_wealth_fraction` | 本地完成 |
| R07 | `validate_config` 改 `isfinite`、正半径、grid 可读文件；`confirmative_mode` 严格拒绝未知键/非法布尔 | 本地完成 |
| R08 | `ExchangeDiagnostics` 新增 `nonzero_transfer_pairs`；稳定 GID 已通过单对重排测试。V0 的三粒子测试证实串行原地交易仍依赖存储/遍历顺序 | 待量化，阻塞确认性执行 |
| R09 | main 分别记录 pre/post 动能；分窗口 `health.json` | 本地完成 |
| R12 | 快照 CSV 用 `max_digits10`；`min_wealth_observed` 全程不变量；结果拆 `execution/numerics/stationarity/precision/claim` 分层 | 本地完成 |
| R10/R11 | `confirmative_mode` 拒绝 `nprocs>1` 与 `--restart`（清晰报错） | 本地完成 |

### 4.1 支持矩阵（R10/R11 显式排除）

| 维度 | 确认性参考 | 状态 |
|---|---|---|
| MPI rank 数 | 单 rank（`nprocs=1`） | 已验证参考；`nprocs>1` 在确认性模式拒绝 |
| 线程数 | 明确 `OMP_NUM_THREADS`（执行器注入） | 参考；OpenMP ON/OFF 双构建留 umi |
| 重启（restart） | 不支持 | `--restart` 在确认性模式拒绝 |
| MPI halo / restart RNG 恢复 | 另立工作包 | 未验证，延期 umi |

### 4.2 本地验证结果与下一 Gate

本地（2026-09-13 复核）：`python3 -m pytest -q` 为 147 passed；改动 C++ 的逐文件 `c++ -std=c++20 -fsyntax-only` 与 `git diff --check` 均通过。这些检查不执行模拟器，不构成数值证据。

当前 Gate：V0B/V0C 双构建均已通过，V1P 已给出运行时估计。完整 V1 的代码、矩阵与 preflight 已就绪，等待 5 CPU 小时 / 1 墙钟小时预算授权；确认性实验仍未授权。

首次 V0（commit `78a742b`）在 umi 的 OpenMP OFF/ON 两套构建均成功，Python 141 tests 通过，两个 CTest 组合中均只有 `exchange_kernel` 失败。失败来自一个假设“多粒子原地交易应对存储重排逐粒子完全不变”的新增测试；实测表明稳定 GID 只固定随机抽样，不能消除非交换的顺序更新效应。这项要求超出了 S07 的单对随机流修复，也证明 S08 仍未完成。后续 V0B 保留单对 GID/seed 回归与所有不变量测试，把多粒子顺序效应移入 V1 的三级步长定量检查；在误差界冻结前不开展确认性实验。

V0B 在 umi 完成：Python 141/141；OpenMP OFF CTest 7/7；OpenMP ON CTest 7/7；`jobctl reconcile` 返回 completed。V0B 关闭实现构建 Gate，但不关闭 S08，也不构成非平坦数值校准或科学证据。

### 4.3 V0C 与 V1P（2026-09-13）

V1 顺序层要求仅改变存储行序，因此 IC loader 新增可选 `gid,px,py` 显式相态输入并拒绝重复 GID；Python 输入生成器可生成 canonical/permuted 两份按 GID 完全相同的状态。V0C 在 umi 完成 Python 147/147、OpenMP OFF/ON CTest 各 7/7，`jobctl reconcile` 为 completed。

V1P 在目标人口 1000、64×64 网格上执行三条总物理时长 10 的非证据 profile，实际总运行 2.80 秒。对冻结的 75-run、每 run 物理时长 1500 的 V1 矩阵按 step 数线性外推并乘 1.5 安全系数，估计 3.47 CPU 小时、并发 8 时 0.43 墙钟小时。完整 V1 已声明且 preflight 8/8；用户于 2026-09-13 授权本项目计算资源不设限并允许多进程/GPU，V1 采用已验证的 CPU 参考实现并发 8 执行。

完整 V1 随后在 umi 完成 75/75 runs，0 个运行失败，累计 7.94 CPU 小时。财富非负/有限性、非平坦三级步长界和存储顺序界全部通过；四项数值分辨率上限分别为 Spearman `0.0199341`、Moran's I `0.0107394`、occupancy entropy `0.00298606`、wealth Gini `0.00438174`。但步长层 45 runs 中 19 个未通过稳态、7 个未通过精度，因此 V1 总 Gate 失败，E1 继续阻塞。失败以 reversal-shape 判据为主（18 个 metric-run），需先做窗口敏感性诊断，再以新 seed 执行 V1B；不得用事后窗口选择挽救 V1。

V1D 随后复用 75 个 V1 运行的最后 96 帧完成确定性诊断，24/1σ 基线逐项复现旧计数，jobctl reconcile 通过。2σ 阈值将 24 帧形状反转从 18 降到 0，但 96/2σ 暴露 37 次漂移失败和 42 次精度失败，说明 `total_time=1500` 的长窗口仍包含瞬态。V1B 在产生任何自身结果前冻结为新 seeds、`total_time=2500`、最后 96 帧与 2σ 反转阈值的完整 75-run 重校准。

V1B 在 umi 完成 75/75 runs、0 个运行失败，jobctl reconcile 通过，消耗 14.49 CPU 小时。延长时长把步长层 96/2σ 的稳态失败从 28/45 降至 8/45、精度失败从 26/45 降至 9/45，但仍未满足逐运行全合取 Gate；smooth 的 Spearman fine-vs-finest 两标准误上界为 `0.0279453`，超过冻结上限 `0.02`，其余步长单元、存储顺序界和不变量通过。V1B 是有效负结果，E1 继续阻塞；下一步 V1BD 将检查条件级 ensemble 稳态与独立重复数需求，不能事后改写 V1B。

V1BD 精确复现 V1B 的逐运行计数，并显示最后 96 帧的 9 个条件 ensemble 全部通过稳态，支持把 Gate 单位对齐到重复总体估计量；6/9 条件的时间 ESS 仍低于 4。按失败 smooth-Spearman 单元的已观察均值与 paired SD，维持 `|mean|+2SE≤0.02` 需要约 14 个重复。V1C 因而在新数据前冻结 15 个新 seeds、`total_time=3000`、最后 144 帧和条件 ensemble Gate，逐运行诊断仍完整保留。

V1C 在 umi 完成 225/225 runs、0 个运行失败，jobctl reconcile 通过，消耗 45.38 CPU 小时 / 6.24 墙钟小时。财富不变量、全部非平坦步长单元和存储顺序误差界通过，四项数值分辨率上限收紧为 Spearman `0.00672590`、Moran's I `0.00997056`、occupancy entropy `0.00251510`、wealth Gini `0.00214101`。但 smooth、`dt=0.02` 的 Spearman ensemble 同时失败 drift 与 ESS，导致稳态为 8/9；另有 6/9 条件因时间 ESS 低于 4 未通过精度。该结果不能用事后改 Gate 挽救，E1 继续阻塞；下一步 V1CD 只复用固定输出，分离持续瞬态、时间自相关和独立 seed 精度，再决定新的独立校准设计。

V1CD 在 umi 完成并通过 reconcile，精确复现 V1C 尾窗。相邻 144 帧窗口的稳态失败由 3/9 降至 1/9，36 个有界指标跨窗变化界全部低于预先存在的规划半宽；时间 ESS 失败仍为 6/9。把每 seed 尾窗均值视为独立样本后，30/36 个规划精度单元通过，clustered 的 Moran/entropy 六个单元估计最多需要 20 seeds。诊断支持将“尾窗动力学稳定”“相邻窗口稳定”和“独立 seed 精度”拆开；V1E 已按 20 个新 seeds、`total_time=4500` 和两段 144 帧窗口冻结设计，等待 runner 与 V0E Gate。

V0E 在 umi 完成 Python 152/152、OpenMP OFF/ON CTest 各 7/7，jobctl reconcile 通过。V1E 的两窗口稳态、跨窗口配对界和独立 seed 精度实现 Gate 已关闭；OpenMP OFF reference 二进制 SHA-256 为 `87eafa4e1e9b0ca24d45b49eb6508f45f07bcd4f67cc72f436210f0e8d7ddee3`。

### 4.4 Cycle 3 E3 证据纠正

2026-09-13 在 umi workspace 核查：E3 共计划 240 runs，实际存在 71 个 completion marker，其中 62 completed、9 timeout（10,800 秒），169 未尝试；最后 marker 日期为 2026-09-07，当前无执行进程，也没有 aggregate artifacts。因此 E3 状态从陈旧的“执行中”纠正为 `incomplete`，不支持 C4-ROBUSTNESS。部分 Cycle 3 runs 保留为 provenance，不与 Cycle 4 修复后的模型合并。
