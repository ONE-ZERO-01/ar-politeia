# 模拟器改进台账（simulator-remediation-status）

日期：2026-09-17。状态：Cycle 4 代码级修复、顺序敏感性和非平坦步长误差界已通过；V1F 64-seed 独立校准已完成并**全部 Gate 通过**（2026-09-17 08:09 +08:00，960/960 runs，0 失败，340.95 CPU 小时 / 46.13 墙钟小时）；promotion `archive-v1f` → `prepare` → V0G → `finalize` 已完成，Cycle 4 最终参数锁已冻结并授权 `E1-MATCHED-LANDSCAPES-C4`。**E1-C4 已于 2026-09-17 08:10 +08:00 在 umi 提交并运行**（128 runs，8 并发，当前无失败），其分析代码在运行期间不再改动。

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
| S01 | P0 | A | 财富没有反馈到当前空间动力学 | 重写机制解释（E2 空间零效应=结构隔离） | 已完成（`research/model-specification-c4.md` §6，2026-09-16） | 完整模型（social_strength>0）下的中介链未验证 |
| S02 | P0 | A/B | 截断产生零财富后交换跳过该粒子 | 修复交换边界 + 诊断 | 本轮 | 回流是"允许"而非"必然" |
| S03 | P0 | B | Moran's I 与部分财富方差被移出稳态 Gate | 恢复 gate 指标 | 已完成（分析代码与 V1C 实测） | V1C 显示长相关时间，稳态/精度问题仍需独立诊断 |
| S04 | P0 | B | 平坦景观把 Spearman 数值误差校准成零 | 退化相关标 NaN，排除退化 SESOI | 本轮 | 非退化校准仍需 umi |
| S05 | P1 | A/C | Langevin 外叠加阈值速度缩放 | 温控诊断计数 | 本轮 | 社会力截断待完整模型验证 |
| S06 | P1 | A | OpenMP 无噪声分支遗漏摩擦 | 修复 + 回归 | 本轮 | 无 |
| S07 | P1 | A/C | 交换噪声不含 seed、用数组下标 | 稳定 GID + base_seed 子流 | 本轮 | 重排不变性需 umi 实测 |
| S08 | P1 | A/C | 固定顺序原地交换 | 三级步长 × 完整相态重排量化 | V1/V1B/V1C 顺序界均通过 | 当前参数域内已受数值误差界约束；扩大参数域需重校准 |
| S09 | P1 | A/C | E2 同时开关生产与衰减 | 明确估计对象 + 隔离设计（v2） | 设计与代码完成（`model-specification-c4.md` §5.6/§6.4；`e2-cycle4-channel-design.md` v2 + §12 实现记录，2026-09-17）；pilot/冻结 R/授权未开展 | E2-C4 未执行；旧 E2 三效应字段按新设计重解释（aggregate_e2 保持逐字不动） |
| S12 | P0 | A/C | 参考过程运行在深度次饱和区，且运动通道泄漏到财富尺度 | 已实测登记；E1-C4 次要家族预注册限定；E2-C4 P3 增设尺度不变性检验 | 部分（文档与限定已完成；参数层修复未开展） | `w/w_ref = 0.12–0.40`；穿越 `w_ref` 的水平扫描需新校准（P3b） |
| S13 | P1 | B | V1F 的 jobctl artifact 声明用裸文件名，被解析到项目根而非作业 workspace，48 小时后全部记为 valid=false | jobctl 提交期越界/重复拦截 + 记录 resolved 绝对路径 + 新增 `recheck`（按已存声明重算契约、保留执行事实、旧判定留作溯源）；V1F 声明已修正并 reconcile 为 completed | 已完成（2026-09-17） | 提交时产物尚不存在，故"路径写错但界内"的笔误无法在提交期拦下；只能靠 recheck 与 resolved 字段暴露 |
| S14 | P0 | A/C | `finalize` 静默绑定了非校准的 binary：0f4ac29 在 V1F 提交后改了 `ic_loader.cpp`，V0G 重建出 `1e3f052f…` 而非校准所用 `87eafa4e…` | `validate_v1f` 读出并校验校准 binary SHA；候选锁新增 `reference_binary_sha256`；`finalize` 强制"binary 在 V0G workspace 内"且 SHA 等于校准对象，否则拒绝写 final；`ic_loader.cpp` 恢复到校准提交 | 已完成（2026-09-17；V0G 重建实测复现 `87eafa4e…`，无需重跑 V1F） | 若未来确需引入模拟器源码改动，必须重跑校准；编译告警修复推迟到 E1-C4 之后 |
| S15 | P1 | A/B | E2-C4 需要的 per-run `base_production` 被无条件加进共享 spec 构造器，使**已授权实验** E1-C4 的 `run_specs.json`（已声明产物）多出一个键，该产物不再可由其冻结 `source_commit`（b6d24b7）的源码复现 | 键收窄到 `E2_C4_EXPERIMENT` 分支；E2-C4 源项核算缺键时在**任何磁盘 IO 之前** fail-fast（不再默认 0，否则 P2 源总量核算会空过）；E1-C4 spec schema 以冻结字面量入测试（经变异检验确认会失败） | 已完成（2026-09-17） | 跨版本等价性探针只覆盖**输入生成**（128 specs / 706 产物逐字节相同），不逐字节复核分析路径；探针绕过 `require_umi()` 直接在本地调用库函数，仅写临时目录、不执行模拟器 |
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
- E1-C4：新增独立实验 ID、matched 两条件矩阵、V1F 校准 schema、两窗口 ensemble Gate、
  独立 seed 精度和 `max(numerical limit, scientific SESOI)` 判定；Cycle 3 分支不变。
- E2-C4（S09，2026-09-17，本地纯代码、无 C++ 改动）：新增五单元
  `E2-CHANNEL-ABLATION-C4` 条件分支与约束 1/3 的提交期 fail-fast（`validate_e2_c4_structure`）；
  三条件输入审计 `audit_three_condition_landscapes`；与 C++ `TerrainGrid::elevation` 逐点对齐的
  `resource_at_particles` 与源项核算 `source_rate_metrics`；P1 位级恒等护栏（fail-fast、
  违规留痕）；P1/P2/P3/P4 四块聚合器 `aggregate_e2_c4`（输出 `channel_separation.json`）与
  强制可比性 Gate；E2-C4 稳态指标集排除在 `flat` 上退化的 `resource_density_spearman_rho`。
  旧 `aggregate_e2` 与 Cycle 3 归档结果逐字不动。本地 190/190 通过（详见
  `e2-cycle4-channel-design.md` §12）。
- S15（2026-09-17，本地纯代码、无 C++ 改动）：E2-C4 的 per-run `base_production` 收窄到
  `E2_C4_EXPERIMENT` 分支，E1-C4 的 `run_specs.json` schema 恢复为冻结状态；E2-C4 源项核算
  缺键时前置 fail-fast；`tests/test_run_landscape_study_gates.py` 新增
  `E1_C4_FROZEN_RUN_SPEC_KEYS` 契约与两条回归（schema 冻结、源项缺键拒绝）。本地 192/192 通过。

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

V1E 在 umi 完成 300/300 runs、0 个运行失败并通过 reconcile，消耗 103.51 CPU 小时 / 14.64 墙钟小时。财富不变量、非平坦三级步长、存储顺序、尾窗稳态和相邻窗口稳定性全部通过，数值分辨率上限为 Spearman `0.00971292`、Moran's I `0.00615936`、occupancy entropy `0.00161097`、wealth Gini `0.00242933`。独立 seed 精度仍在 6/9 条件、12 个 metric cells 失败，点估计最大需要 38 seeds；V1ED 将在固定输出上评估样本量不确定性，E1 继续阻塞。

V1ED 在 umi 完成并通过 reconcile，精确复现 V1E Gate。点估计最大需要 38 seeds；对样本 SD 取单侧 90% 上界后最大需要 61，按预定上取 2 的幂政策选择 64。V1F 已冻结为 64 个新 seeds、960 runs 和不变的 V1E Gate，预计 331.23 CPU 小时 / 41.40 墙钟小时。

V0F 随后在 umi 完成 Python 153/153、OpenMP OFF/ON CTest 各 7/7，reference binary
SHA-256 与 V0E 完全一致。V1F preflight 8/8 后于 2026-09-15 10:01:13 +08:00 提交，
使用 8 个 OMP=1 CPU reference 进程。运行期间同步完成 E1-C4 独立 runner、两阶段 promotion
生成器和 binary SHA-256 执行前强校验；V0G 的非交互测试环境显式绑定当前 checkout 的
`src/`，消除 editable install 隐式依赖；本地全套测试增至 164/164。promotion 的 candidate
阶段不授权 E1，finalize 必须先验证 V0G 及其新建 reference binary。最终锁与作业仍须等待
V1F 完整结果后由该流程生成。

V1F 完成后的证据归档也已纳入 promotion：`archive-v1f` 将 run specs、completion markers、
health、jobctl exit/artifacts、reference binary 和 calibration/steady Gate 交叉验证后再生成 tracked
结果与 manifest，相关全套测试增至 165/165。该命令在作业运行期间不会执行。

### 4.4 Cycle 3 E3 证据纠正

2026-09-13 在 umi workspace 核查：E3 共计划 240 runs，实际存在 71 个 completion marker，其中 62 completed、9 timeout（10,800 秒），169 未尝试；最后 marker 日期为 2026-09-07，当前无执行进程，也没有 aggregate artifacts。因此 E3 状态从陈旧的“执行中”纠正为 `incomplete`，不支持 C4-ROBUSTNESS。部分 Cycle 3 runs 保留为 provenance，不与 Cycle 4 修复后的模型合并。

### 4.5 WP0 交付物与 V1F 期间的独立核验（2026-09-16）

V1F 运行期间完成了两项不依赖其结果的 WP0 工作。

**模型规范与因果结构已写实。** 新建 [research/model-specification-c4.md](model-specification-c4.md)，
逐条对照活动源码给出：单步更新流水线及其顺序、运动/边界/温控的实际过程、交换公式与边界政策、
随机来源、原地更新的顺序效应、生产—衰减组合因子、因果图与缺失的 `w → (x, p)` 边、
可观测诊断的适用边界、执行模式支持矩阵，以及旧结论处置表（WP0 §3.3）。
它同时关闭 S01 与 S09 的文档部分；未关闭的六项在文末列出，其中唯一科学阻塞仍是稳态前提。

写实过程中确认的、此前未在台账中逐条记录的事实：

- `exchange_halos` 在 `main.cpp` 中**没有任何调用点**（`grep` 全仓核实，仅在定义处出现），
  因此 R10.2 的"halo 未接入每步力/交换"是代码级事实而非推测；
- `CellList::for_each_pair` 的行主序遍历 + 计数排序插入序构成原地交换的确定顺序，
  且 `r2 > 0` 严格排除重合粒子对；
- `ability_saturation_w` 未在 V1F config 中显式给出，取默认值 **5.0**，恰好等于
  `mean_wealth = 5`，因此能力函数在均值财富处半饱和——它是模型参数而非数值细节；
- V1F 的 `order` 层显式设 `temperature = 0.0`（配 `initial_temperature = 0.5`），
  与 `timestep` 层的 `temperature = 0.5` 不同，两层结论不可互相引用。

**E1-C4 冻结 seeds 互斥性已复核。** 对仓库内全部 `research/jobs/*/seeds.txt` 与 job JSON 中的
`seed` 字段做全量扫描，E1-C4 的 64 个冻结 seeds（`11657`–`12241`）与 Cycle 1–3 全部任务、
以及 `V1`/`V1B`/`V1C`/`V1E`/`V1F`/`V1P` 的**交集均为 0**，`e1-cycle4-design.md` §2 的冻结声明成立。
复核方法为纯记账比对，不执行任何模拟器或实验脚本。

**S09 的可识别性缺陷已定位，E2-C4 设计已冻结。** 新建
[research/e2-cycle4-channel-design.md](e2-cycle4-channel-design.md)。对 Cycle 3 E2 的 160 个
归档 run 做结构核对（只看"因子动了什么"，不看效应大小）后确认四条事实：

1. E2 的 `production` 因子同时切换 `terrain_production_enabled` 与 `wealth_decay_rate`
   （`run_landscape_study.py:299`），所以它是 source–sink bundle；
2. `prod=关` 单元不是可比对照，而是退化态：decay 为 0 时总财富守恒、平均财富恰为 5.0，
   `prod=开` 单元则被压到 `min wealth ≈ 1e−07…1e−06`；由方差与 Gini 反推的平均财富约为
   0.27（force 关）与 0.97（force 开），即 `w/w_ref ≈ 0.05` 与 `0.19`，交换核工作点完全不同；
3. 在每个 `(seed, force)` 上，`prod` 关/开两单元的三个空间指标**字符串完全相等**
   （20/20 seeds，差值 > 1e−12 计数为 0）。所以"production 对空间结构零效应"是代码因果结构的
   **恒等验证**，不是科学发现，`identified_channels` 的语义必须更正；
4. 四个单元 `stationarity_pass` 全为 1.00 —— 逐运行稳态 Gate 结构上无法发现单元间不可比。

设计给出三条识别约束（非退化、平衡水平匹配、结构隔离按恒等检查执行），并据此把"生产/衰减"
落实为 P2 源的空间组织消融（`ρ = 1`，依据是资源场按构造均值为 1）与 P3 沿 `s/d` 常数的汇速率
匹配响应（同时构成模型尺度不变性的可证伪检验），配 P1 恒等护栏与 P4 强制可比性 Gate。
所需代码改动为新增 `uniform_production` 键与四个可比性指标列，并重写 `aggregate_e2`。
E2-C4 仍为 `deferred`，须等 V1F 与最终 Cycle 4 参数锁。

**v2 修订（同日，含 S12 新发现）。** 对 V1F 已完成 run 的尾帧逐 run 测量平均财富（59 对 seed，
`dt = 0.005`）：clustered **1.9838**、shuffled **1.3810**、smooth **0.5918**，
即 `w/w_ref` = **0.397 / 0.276 / 0.118**；配对 `clustered − shuffled` 为 **+43.6%**
（2SE 半宽 4.5%，`dt = 0.02` 给出同样的 +44.3%）。由此登记新问题 **S12** 并改写设计：

1. **参考过程不在 `w_ref` 附近运行。** 初值 `mean_wealth = 5.0 = w_ref` 暗示设计意图是半饱和点，
   平衡水平却是 0.59–1.98，能力函数 `A = εw/(w + w_ref)` 处于近线性区，
   能力异质性转化为交换优势的效率被削弱；
2. **下边界被强烈占据**：`min wealth` 达 1e−05…1e−13，`share` 的 `[0,1]` 夹紧在实际运行中活跃，
   S02 的边界政策在确认性尺度上确实起作用；
3. **运动通道泄漏到财富尺度**：力开使平衡水平比力关高约 3.4 倍，因为力把粒子送入资源阱抬高
   `Σprod`。所以财富类结局的景观效应与平衡财富尺度变化混杂。

设计侧因此改为：**全部单元关闭地形力**，使位置成为外生变量并在单元间逐位共享
（该恒等已在 Cycle 3 E2 的 40 个 `(seed, force)` 组合上逐位确认：位置类指标在财富类因子切换下
字符串完全相等）。空间指标于是从"结局"变为"恒等护栏"，P1 判据改为
`occupancy_entropy`/`density_morans_i` 必须逐位相等而 `resource_density_spearman_rho` 允许不同
（前者只依赖位置，后者依赖资源场）。均匀源改用 `flat` 景观（常量恰为均值）实现，
**因此不再需要任何 C++ 改动，reference binary 的 SHA 保持不变**，不触动 V1F 校准与
E1-C4 的 binary 绑定链。P4 的可比性目标也从"匹配 `w_ref = 5`"改为"单元之间相互匹配"，
因为实测平衡水平与 `w_ref` 相差 2.5–8 倍，原目标不可达。

E1-C4 侧的处置已在锁冻结前写入 `e1-cycle4-readiness.md`：主 family 是位置类指标、
与财富水平无关，故 Gate 与阈值不变；`wealth_gini` 次要家族预注册为
"空间组织 + 平衡财富尺度"的**合成效应**，并要求 `mean_wealth` 与 `wealth_scale_ratio` 随
`result.json` 报告。该处置只收窄解释、不放宽任何阈值，属保守方向。

读取平均财富一事已在 `e1-cycle4-readiness.md` 与 `e2-cycle4-channel-design.md` §5
作为**协议偏离**完整披露（读取对象为非主指标的结构量，目的是检查设计前提）。
V1F 的 `numerical_calibration.json` 当时尚未读取；它已在作业完成后由 `archive-v1f`
正式核验并进入 tracked 证据（见 §4.6），其六层 Gate 与数值上限见该节。

### 4.6 V1F 完成与 promotion 链（2026-09-17）

**V1F 通过全部冻结 Gate。** 作业于 2026-09-17 08:09 +08:00 结束：960/960 runs、
0 运行失败、166,076 墙钟秒（46.13 小时）、340.95 CPU 小时、0 个非空 stderr、
单一 OMP=1 reference binary checksum。六层 Gate 全通过：invariants、
timestep_convergence、storage_order_sensitivity、tail stationarity、
adjacent-window stability、independent-replicate precision。9 条件 × 64 重复在尾窗稳态、
相邻窗口稳定和独立精度上均无失败单元；temporal-ESS 诊断仍标记 8/9 条件未过，
但按冻结设计它是诊断层而非 Gate 层。

数值分辨率上限为 Spearman `0.0045900`、Moran's I `0.0032588`、
occupancy entropy `0.00099482`、wealth Gini `0.0014408`，比冻结的 SESOI
（0.05/0.05/0.025/0.025）小约一个数量级，故 E1-C4 的有效阈值即 SESOI。

`archive-v1f` 在交叉核验 run specs、960 个 completion marker、health、
jobctl 执行事实、reference binary 与 calibration/steady 两报告互证后，写出 tracked
结果与 manifest。随后 promotion 链走完 `prepare` → V0G → `finalize`，生成
`research/parameter_lock.cycle4.json`（`ar-politeia-cycle4-confirmatory-v1`，
status `final`，`confirmatory_execution_authorized = true`，
`source_commit = b6d24b7…`），授权 `E1-MATCHED-LANDSCAPES-C4`。

**S13：jobctl artifact 声明笔误。** V1F 的 jobctl spec 把 8 个 artifact 声明成裸文件名，
worker 按 `spec.cwd`（项目根）解析，于是全部落在 `<root>/result.json` 一类路径上，
46 小时后一律记为 `valid: false`。同期的 V1E/V0E/V0F 都用项目根相对完整路径，
故这是声明错误而非产物丢失——`archive-v1f` 独立校验 workspace 并通过，8 个产物齐全。
`jobctl` 已补三件事：提交期拒绝越界（解析到 `cwd` 之外）与重复的 artifact 声明；
每条 artifact 记录新增 `resolved` 绝对路径与 `contained_in_cwd`；新增 `recheck`
动作，按已存 `spec.json` 重算契约而**不重跑作业**，保留 `exit_code`/`timed_out`/
`wall_seconds` 并写入 `artifact_recheck` 溯源（含旧判定与本次核验的声明）。
V1F 的声明已修正，reconcile 现为 `completed`，执行事实未改（exit 0、46.13 小时）。

提交期拦截对"路径写错但在界内"的笔误无效——提交时产物尚不存在，无法判断正确位置；
这条限制已如实记入残余限制。

**S14：finalize 静默绑定了非校准的 binary（本轮最严重发现）。** V1F 的数值分辨率
上限是在 reference binary `87eafa4e…` 上实测的，并被写进 V1F 归档 `result.json` 的
`binary_sha256`。但 `0f4ac29`（2026-09-15 21:35，即 V1F 于 10:03 提交后约 11.5 小时、
V1F 仍在运行时）改动了 `research/src/experiments/politeia/src/io/ic_loader.cpp`，
于是 V0G 在 `e397bef` 重建出 `1e3f052f…`。`finalize` 照单全收，把一个
"校准对象 ≠ 执行对象"的锁写成了 final。

该改动语义惰性（把文化列名构造从 `"c" + std::to_string(d)` 改为显式拼 `std::string`，
结果字符串逐字节一致），不可能改变模拟行为——但它改变了编译产物。后果因此不是
"告警没修"，而是整条 V1F→V0G→finalize 链所要建立的绑定从**恒等**退化成了需要论证的
等价；留在锁里就等于用一个未实测的等价性假设去支撑整个确认性实验的数值误差界，
正是本项目一直在消除的那类推断（参见 S01、S09）。

允许它发生的两个结构缺口：`validate_build` 只记录 configure/build/ctest 返回码，
完全不记录被测 binary 的 SHA；候选锁只带校准文件的 SHA，不带被校准 binary 的 SHA。
因此没有任何一方有资格判断绑定是否正确。

处置：`validate_v1f` 读出并校验归档的 `binary_sha256`；候选锁新增
`numerical_calibration.reference_binary_sha256`；`finalize` 强制两条——绑定的 binary
必须位于 V0G workspace 内（即确实由 V0G 构建产出），且其 SHA-256 必须等于校准对象，
否则拒绝把锁写成 final（报错文案提示"恢复模拟器改动或重新校准"）。
`ic_loader.cpp` 恢复到 48ad02a 的内容，`git diff 48ad02a -- research/src/experiments/politeia/`
为空，即该子树完全回到被校准状态；编译告警修复推迟到 E1-C4 之后单独提交。

关键点是**没有重跑 V1F**：在恢复后的源码（`b6d24b7`）上，V0G 重建**实测复现**出
`87eafa4e…`，与校准对象逐字节相同，证明构建是确定性的、恢复源码足以还原被校准的
artifact。该等价性是被实测的，不是被论证的。最终锁的两处 binary SHA
（`reference_binary_sha256` 与 `simulator_validation.binary_sha256`）均为 `87eafa4e…`。

被作废的中间产物（`e397bef` 上的候选/最终锁与 V0G/E1 声明）已删除，其 jobctl 记录
留档为 `.autoresearcher/jobs/V0G-SIMULATOR-TESTS-C4.superseded-e397bef`。
