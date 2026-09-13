# 模拟器改进台账（simulator-remediation-status）

日期：2026-09-13。状态：Cycle 4 代码级修复已通过本地非数值检查；待提交并在 umi 完成 OpenMP OFF/ON 双构建与 CTest。实验重跑与重新校准尚未开始。

本文件是 `simulator-improvement-plan.md`（下称"计划"）的执行台账，按问题（S01–S11）记录证据、本次代码修改、回归测试、完成状态与残余限制。它不覆盖或修改 `plan.json`、`parameter_lock.json`、`findings.json` 与服务器任务状态；旧结果目录不变。

## 1. 可追溯基线

| 项 | 值 |
|---|---|
| 源码 commit（工作区起点） | `d4373544461bfbb7cf0047086ae83a95eaac4eb1` |
| 分支 | `codex/cycle3-validation` |
| 参数锁 | `research/parameter_lock.json`，`ar-politeia-cycle3-confirmatory-v3`，SHA-256 `034c3dd357f13d1192a887b31759dbd2b0d3f05ae50409823d00c371fa8dd36e` |
| E0 校准 | `research/jobs/E0-NUMERICS-C3/numerical_calibration.json`，SHA-256 `cf484987a3c9d63ff5276f098ae75a66312065f5bfdaef9d0588e7b9b8f9c73e` |
| 旧结果版本 | E0-NUMERICS-C3 / B0-DYNAMICS-PILOT-C3 / E1-MATCHED-LANDSCAPES / E2-CHANNEL-ABLATION（Cycle 3，均已提交）；E3-ROBUSTNESS-HOLDOUT 执行中（不阻塞） |
| 分析脚本版本 | `research/src/experiments/landscape_study.py`、`run_landscape_study.py`（Cycle 3） |

## 2. 问题台账

证据类别：A=代码可直接确认；B=已提交记录暴露的验证缺口；C=需实验确定影响程度。

| ID | 优先级 | 类别 | 问题 | 处置 | 完成状态 | 残余限制 |
|---|---|---|---|---|---|---|
| S01 | P0 | A | 财富没有反馈到当前空间动力学 | 重写机制解释（E2 空间零效应=结构隔离） | 待办（文档，非代码） | 需随新因果图成文 |
| S02 | P0 | A/B | 截断产生零财富后交换跳过该粒子 | 修复交换边界 + 诊断 | 本轮 | 回流是"允许"而非"必然" |
| S03 | P0 | B | Moran's I 与部分财富方差被移出稳态 Gate | 恢复 gate 指标 | 本轮（分析代码） | 能否通过需 umi 重跑 |
| S04 | P0 | B | 平坦景观把 Spearman 数值误差校准成零 | 退化相关标 NaN，排除退化 SESOI | 本轮 | 非退化校准仍需 umi |
| S05 | P1 | A/C | Langevin 外叠加阈值速度缩放 | 温控诊断计数 | 本轮 | 社会力截断待完整模型验证 |
| S06 | P1 | A | OpenMP 无噪声分支遗漏摩擦 | 修复 + 回归 | 本轮 | 无 |
| S07 | P1 | A/C | 交换噪声不含 seed、用数组下标 | 稳定 GID + base_seed 子流 | 本轮 | 重排不变性需 umi 实测 |
| S08 | P1 | A/C | 固定顺序原地交换 | 量化后选方案 | 待办 | 需对照实验 |
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
| R08 | `ExchangeDiagnostics` 新增 `nonzero_transfer_pairs`；锁定参数边界 + ≥3 粒子重排测试 | 本地完成 |
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

本地（2026-09-13 复核）：`python3 -m pytest -q` 为 141 passed；改动 C++ 的逐文件 `c++ -std=c++20 -fsyntax-only` 与 `git diff --check` 均通过。这些检查不执行模拟器，不构成数值证据。

下一 Gate：提交并 push 到 `umi`，随后在 `umi` 进行 OpenMP OFF/ON 双构建与 CTest。只有两套构建均通过，才进入非平坦 dt 校准设计和小规模数值验证。

### 4.3 Cycle 3 E3 证据纠正

2026-09-13 在 umi workspace 核查：E3 共计划 240 runs，实际存在 71 个 completion marker，其中 62 completed、9 timeout（10,800 秒），169 未尝试；最后 marker 日期为 2026-09-07，当前无执行进程，也没有 aggregate artifacts。因此 E3 状态从陈旧的“执行中”纠正为 `incomplete`，不支持 C4-ROBUSTNESS。部分 Cycle 3 runs 保留为 provenance，不与 Cycle 4 修复后的模型合并。
