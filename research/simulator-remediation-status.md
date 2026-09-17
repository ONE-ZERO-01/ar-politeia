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
| S16 | P1 | A | `main.cpp` 从不调用 `exchange_halos`（两套分解类都只定义未使用），`discover_neighbors` 的邻居表无处消费：`nprocs>1` 时粒子只与**同 rank** 粒子作用，跨 rank 对被静默丢弃。确认性模式已拒绝 `nprocs>1`，但非确认性 `mpirun -np N` 仍会跑出不同物理 | 审计完成；修复为 C++ 层"`nprocs>1` 一律拒绝，除非显式 `allow_unvalidated_mpi`"，**待 E1-C4 后**（任何 C++ 改动都会使参考 binary SHA 变化，需重跑校准） | 审计完成（2026-09-17，静态） | 修复未实施；MPI halo 的接入本身另立工作包 |
| S17 | P1 | A | restart 不能复现连续运行：① checkpoint 只存粒子字段，**不存 RNG 状态**，而 `LangevinIntegrator` 的热噪声来自有状态 RNG（成员 `rng_` 与"每步按线程数抽种子"的每线程 RNG）且按**数组下标**消费；② checkpoint 里嵌入了 config 块，但 `read_checkpoint` 无返回 config 的接口、`main.cpp` 用命令行传入的 cfg，**嵌入配置被静默忽略**；③ `id_seed` 不入 checkpoint | 审计完成；修复为 C++ 层"非显式 opt-in 时拒绝 `--restart`"以及（或）在 read 侧校验嵌入 config 与运行时 cfg 一致，**待 E1-C4 后** | 审计完成（2026-09-17，静态） | 修复未实施；确认性模式已拒绝 `--restart`（R11），故不影响任何确认性结论 |
| S18 | P1 | A/C | V1F 的 `order` 层以 `temperature = 0.0` 运行（`run_v1_calibration.py:69-75` 强制），因此**存储顺序误差界从未在有热噪声（`temperature = 0.5`，即 E1-C4/E2-C4 的实际配置）时被检验**：热噪声按数组下标消费，而 `redistribute`/`migrate_particles` 在 `nprocs=1` 时直接返回，故参考配置下数组顺序恒等于 IC 文件行序，换行序即换噪声指派。该层实测：`wealth_gini` 2.20e-4→9.38e-5（随 dt 收缩，上限 0.01，pass），其余三指标恰好 0.0——这个结构自洽并**支持** R08（参考配置里唯一的成对原地操作是交换，只改财富；位置类指标因 `social_strength=0` 只剩单粒子地形力而与行序无关） | 审计定位；需一次 V0 规模的廉价实测（**T=0.5** 下 canonical vs permuted 的尾部指标差）来判定该界是否覆盖热噪声↔行序耦合 | 审计完成（2026-09-17，静态）；**实测已提交运行**（2026-09-17，jobctl pid 2149600，128/128 run 目录已建立）：`V1G-ORDER-THERMAL-C4`（`research/v1g-order-thermal-design.md` 预注册；脚本 `run_v1g_order_thermal.py`；配置与 18 项测试已入库） | 若不通过，需把存储顺序纳入参考配置的误差界或改为不依赖行序的噪声指派 |
| S19 | P2 | A/B | 配置面从未审计：`config.cpp` 接受 **185** 个键，参考 `politeia.cfg` 只显式声明 **47** 个，其余 138 个取 C++ 类内默认值（`default_config()` 返回 `SimConfig{}`）。逐键定位消费点后，136 个中性（11 个模块开关包住 136 个、IC 文件取代 5 个、分支未走 4 个、哨兵 1、别名 1、无消费者 2），但两个键在参考配置下**可达且非中性而值不在声明里**：`density_radius`(5.0) 通过无条件的 `std::max` 把 `cell_cutoff` 从 2.5 抬到 5.0，决定串行原地交换的**候选对枚举顺序**（R08/S18 家族）；`culture_dim`(2) 使 IC 装载在缺失 `c*` 列时每粒子多抽 1 个随机数，而同一 RNG 也供初始动量，故**改变其后所有粒子的初始动量** | 审计完成并**机制化**：`tests/test_config_coverage.py`（5 项；用正则取 `config.cpp` 解析键、用驱动本身生成参考 cfg、要求每键恰好落在一个审计类别里；变异检验确认新键会失败）。修复两步：①显式声明两键（不改 C++、不改 binary SHA，但会改变生成的 cfg，故只能对 E1-C4 之后的新实验生效——按 S15，已授权实验的产物必须能由其冻结 `source_commit` 逐字节复现）；②消除 `cell_cutoff` 的隐式耦合（改 C++，需重跑校准） | 审计完成（2026-09-17，静态） | 不改变任何已冻结阈值（参考 binary SHA 与生成的 cfg 均已冻结，结果仍完全确定）；这是**声明完备性**缺口，不是可复现性缺口。详见 `research/config-coverage-audit.md` |
| S10 | P1 | C | 邻域/MPI/重启/完整模型验证不充分 | 邻域 cell 修复 + 配置校验（本轮）；MPI/checkpoint 审计已完成（见 S16/S17/S18 与 §4.7），配置面审计见 S19 | 部分（审计完成，修复待 E1-C4 后） | MPI halo 接入、restart 修复均未实施 |
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
- 冻结声明完整性护栏（2026-09-17，S14 的机制化收尾）：新增
  `tests/test_cycle4_frozen_declarations.py`（8 项），把 Cycle 4 授权链的交叉引用
  变成机器校验——校准文件 ⇄ 归档结果 ⇄ 最终参数锁 ⇄ 实验声明 ⇄ 参考 binary SHA、
  `source_commit`、config/artifacts 哈希，外加"有效阈值 = max(数值上限, SESOI)"
  且 SESOI 必须在四项上严格占优。此前 promotion 测试只对**合成临时目录**做生成器测试，
  没有任何测试钉住真实归档层之间的绑定，因此 S14 那样的错绑可以整体通过测试。本地 200/200 通过。
- 配置键覆盖审计（2026-09-17，S19，静态、无 C++ 改动）：185 个解析键 = 47 个已声明 +
  136 个中性 + 2 个 `effective-undeclared`（`density_radius`、`culture_dim`）。新增
  `tests/test_config_coverage.py`（5 项）：用正则从 `config.cpp` 取解析键、用驱动本身生成
  参考 cfg、要求每个键恰好落在一个审计类别里（变异检验：临时新增键会使该项失败并指名该键），
  并钉住 11 个门控开关为 `false`、两个缺口的默认值与代码锚点不变。本地 205/205 通过。
  详见 `research/config-coverage-audit.md`。

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

**S14 的机制化收尾（2026-09-17）。** S14 能发生，是因为整条授权链只靠文档陈述、没有
任何机器校验：promotion 测试全部对合成临时目录做生成器测试，真实归档层之间的绑定
（校准 ⇄ 结果 ⇄ 锁 ⇄ 声明 ⇄ binary SHA）无人核对。现已新增
`tests/test_cycle4_frozen_declarations.py`（8 项，只读 tracked 文件、不执行模拟器）
把每一处交叉引用钉死，其中包括 S14 的直接判据：
`lock.numerical_calibration.reference_binary_sha256` ==
`lock.simulator_validation.binary_sha256` == 归档结果的 `binary_sha256` ==
实验声明的 `data_checksums.reference_binary`。同时钉住 `source_commit` 三方一致、
config/artifacts 哈希、以及"有效阈值 = max(数值上限, SESOI)"且 SESOI 在四项上严格占优。
任何一层被改动而其余未同步，测试立即失败。

### 4.7 S10 残余：MPI 与 checkpoint/restart 静态审计（2026-09-17，纯读代码）

本节全部结论来自阅读活动源码，**未执行模拟器、未构造任何数值证据**。分类按 §2 的约定，
A=代码可直接确认。

**A1. `nprocs>1` 会静默跑出不同物理（S16）。** `main.cpp` 使用 `SFCDecomposition`，在
启动、每 `compact_interval` 与自动触发时调用 `compute_keys` / `rebalance` / `redistribute` /
`migrate_particles`，并在 `main.cpp:578` 调用 `discover_neighbors`。但**两套分解类的
`exchange_halos` 都没有任何调用点**（`decomposition.cpp`、`sfc_decomposition.cpp` 各定义一处，
`grep` 全仓核实），所以 `discover_neighbors` 算出的邻居 rank 表没有任何消费方。作用域内的
力/密度/交换因此只遍历本 rank 的粒子：**落在 rank 边界另一侧的粒子对被整段丢弃**。
确认性模式已用 `nprocs=1` 硬拒绝这一路径（R10），实验执行器也从不传 rank 数，
但非确认性 `mpirun -np N` 仍可进入。SFC 按 Morton 键范围切分，所以 rank 边界就是空间边界，
丢失的是邻域内真实的相互作用，不是边角噪声。

**A2. 参考配置下数组顺序恒等于 IC 文件行序。** `redistribute` 与 `migrate_particles` 的
函数体首行都是 `if (is_serial()) return;`，而参考构建（`nprocs=1`）恒为 serial。
因此参考配置**在整个运行期间不发生任何 SFC 重排**，粒子数组顺序就是
`load_initial_conditions` 的行序。这一条对参考实现是**正面**的：没有运行中重排，
轨迹对给定 IC 文件完全确定、可复现；但它同时说明"存储顺序"这一轴在参考配置里
只由**初始行序**决定，任何按数组下标消费的随机量都会随之改变（见 A3、S18）。

**A3. 热噪声是有状态 RNG 且按数组下标消费。** `LangevinIntegrator` 持有成员
`std::mt19937_64 rng_`；串行路径逐步调用 `normal_(rng_)`，OpenMP 路径每步先从 `rng_`
抽 `nthreads` 个种子再让每线程各自推进。两条路径都不按粒子身份（GID）取随机量。
这与 S07 修好的交换噪声不同——后者是 `splitmix64(GID 对, seed, step)` 的**无状态**函数，
因此天然与存储顺序无关。§4.5 已记录：`order` 层显式设 `temperature = 0.0`
（配 `initial_temperature = 0.5`），与 `timestep` 层的 `0.5` 不同，两层结论不可互相引用。

**A4. restart 无法复现连续运行，且静默忽略嵌入配置（S17）。** `write_checkpoint` 把运行
配置写入 checkpoint 的 config 块，但 `read_checkpoint` 的签名只回传粒子、
`ckpt_step` 与 `ckpt_time`——**没有回传 config 的通道**，`main.cpp` 用的是命令行/默认加载的
`cfg`。因此 restart 会静默采用与原始运行不同的参数。更根本的是：checkpoint 不含任何 RNG
状态、也不含 `id_seed`（`main.cpp:156` 在读取前用 `rank` 重置），而按 A3 噪声流由
RNG 状态与数组顺序共同决定，所以 restart 在原理上无法复现连续运行的噪声流。
这与台账原先的措辞（"重启 RNG 恢复未验证"）相比更强：不是"没验证"，是**当前实现不具备**。
确认性模式已拒绝 `--restart`（R11），故不影响任何确认性结论。

**S18：存储顺序误差界的覆盖缺口。** V1F 的 `order` 层以 `temperature = 0.0` 运行
（`run_v1_calibration.py:69-75` 强制 `temperature == 0.0` 且 `explicit_phase_state`，
并已从 V1F 受控 cfg 逐条核实），所以该界从未在有热噪声——即 E1-C4/E2-C4 实际使用的
`temperature = 0.5`——时被检验。按 A2/A3，热噪声是参考配置下唯一按数组下标消费的
随机量；`T=0` 恰好把它关掉，因此该层的 0 值不能外推到参考配置。

**更正（2026-09-17，读实测值后）**：台账最初写的"该层实测恰好 0.0"**不准确**。
`numerical_calibration.json` 的 `storage_order_sensitivity` 逐指标为：

| 指标 | dt=0.02 | dt=0.01 | dt=0.005 | 上限 | 判定 |
|---|---|---|---|---|---|
| `resource_density_spearman_rho` | 0.0 | 0.0 | 0.0 | 0.02 | pass |
| `density_morans_i` | 0.0 | 0.0 | 0.0 | 0.02 | pass |
| `occupancy_entropy` | 0.0 | 0.0 | 0.0 | 0.01 | pass |
| `wealth_gini` | 2.20e-4 | 1.18e-4 | 9.38e-5 | 0.01 | pass |

即**wealth_gini 非零且随 dt 收缩**，与前三个指标的"恰好 0.0"形成清晰对照。这个模式
本身是自洽的、并且**支持** R08 而不是与之冲突：参考配置里唯一的成对原地操作是交换，
而交换只改财富；位置类指标之所以逐位不变，是因为 `social_strength = 0.0`，力只剩
单粒子地形力，与行序无关。所以 R08 得到确认，前文"两者至少有一个需要澄清"的措辞
撤回，改为下面这条更窄但更实在的缺口。

**真正的缺口**：该层的 0.0/非 0 结构是在 `T=0` 下取得的，而参考配置用 `T=0.5`。
热噪声按数组下标消费（A3），换行序即换每个粒子拿到的噪声；这一耦合**从未被任何一层
覆盖**，包括 wealth_gini 那 9.4e-5——因为 `T=0` 时该耦合不存在。

**判定已提交运行（2026-09-17，jobctl pid 2149600，128 runs）**：`V1G-ORDER-THERMAL-C4` 就是 V1F 的 order 层
只改一个参数（`T 0.0 → 0.5`），景观/dt/时长/尾窗口/64 个 seed 全部不动，IC 用显式相态
以保证两份输入是同一物理态、只有行序不同。判定规则预先冻结：每指标按 seed 配对
`|mean| + 2·SE ≤ 已冻结 numerical_resolution_limits`，阈值从参数锁读出并重算校准文件
SHA，且只允许跑冻结的参考 binary（S14 检查）。预注册、脚本、配置与 18 项测试见
`research/v1g-order-thermal-design.md`。**E1-C4 结束前不提交、不写结论**；成本约
45.5 CPU-小时（128 runs，`parallel=16` 时约 2.8 墙钟小时）。
若 `bounded`，S18 关闭为"已量化"；若超出，则参考配置的数值误差界缺一条腿，需把热噪声
改为按**稳定 GID** 抽取（与 S07 对交换噪声的做法一致），属 C++ 改动，须重跑校准并重做
授权链。两种结果都不改变任何已冻结阈值，也不改变 E1-C4 的任何结论——它的 IC 文件固定，
存储顺序不是它的误差来源。

**共有的结构成因。** S16、S17、S18 三条都不是"某个函数写错了"，而是同一种模式：
**一个未接入/未验证的通道没有在入口处被拒绝**，于是它可以在没人注意时被打开。
处理方向一致：让入口直接拒绝（MPI 与 restart 的非显式 opt-in 一律失败），而不是
依赖文档警告。这三处的修复都改动 C++，因此都排在 E1-C4 之后；按 S14 的结论，
任何 C++ 改动都会改变参考 binary 的 SHA，必须连带重跑校准。

## 4.8 配置面覆盖审计（S19，2026-09-17，静态）

同一把尺子量到最基础一层：**185 个解析键 vs 47 个已声明键**。逐键定位消费点后，
136 个中性、2 个可达且非中性而值不在声明里（`density_radius` 决定 cell 几何与原地交换的
枚举顺序；`culture_dim` 决定 IC 装载消耗的随机数个数，从而决定其后所有粒子的初始动量）。
完整分类表、代码锚点、影响评估与两步修复方案见 **`research/config-coverage-audit.md`**。
机制落地在 `tests/test_config_coverage.py`：新增配置键若不归类即失败（已做变异检验）。

与 §4.7 的关系：§4.7 是**通道**层（MPI/restart/顺序），§4.8 是**配置面**层——后者是
前者的上游，因为一个未验证通道"能不能被打开"最终由配置面决定。两处的修复都排在
E1-C4 之后：声明补齐会改变生成的 cfg（按 S15 不能追溯应用到已授权实验），
消除 `cell_cutoff` 隐式耦合会改动 C++（需重跑校准）。

## 4.9 E1-C4 完成与归档（2026-09-17）

### 执行结果（实测）

E1-C4 在 umi 完成 **128/128 runs、0 失败**，64 个种子 × {clustered, shuffled} 匹配对。
34.97 CPU 小时 / 18512 秒墙钟（有效并行度 6.8×，parallel=8），单 run 最长 3654.9 秒。
六个分析 Gate 全过：`v1f_numerical_calibration`、`matched_inputs`、`execution_invariants`、
`tail_stationarity`、`adjacent_window_stability`、`independent_replicate_precision`。

paired clustered-minus-shuffled 主效应（10000 次 bootstrap，Holm 族内校正）：

| 指标 | 效应 | 95% CI | Holm p | 冻结 SESOI |
|---|---|---|---|---|
| resource_density_spearman_rho | +0.2297 | (0.2125, 0.2461) | 3.0e-5 | 0.05 |
| density_morans_i | +0.5525 | (0.5330, 0.5705) | 3.0e-5 | 0.05 |
| occupancy_entropy | −0.0818 | (−0.0901, −0.0735) | 3.0e-5 | 0.025 |
| wealth_gini（次要） | +0.00303 | 含 0 | 不拒绝 | 0.025 |

三个必需空间指标全部远超冻结 SESOI 且 Holm 显著，故 C2-LANDSCAPE-C4 的
**证伪条件一条都不成立**——"supported"是预注册逻辑的结论，不是事后判断。
次要的 `wealth_gini` 区间含 0，与 S12 登记的合成效应限定一致（当前参考工作点下
景观效应主要体现在空间结构而非财富尺度）。作用域仅限已校准的参考配置；
尺度/密度/网格/留出景观的泛化仍归 C4-ROBUSTNESS-C4（E3-C4，deferred）。

`temporal_ess_diagnostic_pass` 为 false——按冻结策略该诊断不参与判定，仅登记。

### 流程偏离：归档契约是在跑完之后补写的

Cycle 4 的 promotion 模块（`prepare_cycle4_confirmation.py`）只实现了 `archive-v1f`，
**没有 E1 的归档路径**。后果是：E1-C4 跑完后，其唯一完整副本只存在于 umi 的
`workspace/`（git 忽略），而 `result.json`、`paired_effects.json` 等结论并不在 git 里。
这是一条真实的证据丢失风险，本次补齐。

新增 `archive-e1`。方向安全性论证：

1. **只可能拒绝，不可能放宽。** 归档不重算任何效应、不设任何阈值、不解释任何 Gate；
   判定词逐字节复制（`paired_effects.json` 原样落入 git）。它只能因不一致而失败。
2. **不触及 `change_control`。** 策略禁止的是"结果已知后改动模型/阈值/必需指标/分析"。
   归档既不改模型也不改分析，只是校验并紧凑化，因此不需要新锁或独立数据。
3. **校验强度高于 V1F。** 除 V1F 已有的项外，额外把**每个 completion marker 与其
   `final_snapshot` 的 SHA-256 绑定**：marker 必须对得上真实数值载荷，而不只是一个计数
   （128 × 204 KB 快照，约 26 MB 哈希开销）。并强制
   `analysis_gate_pass == ∧(6 个 gate)`，禁止在 Gate 失败时声称支持。
4. **执行出的设计必须复现预注册。** E1-C4 的 config 不含 `conditions` 键（两条件匹配矩阵
   由 runner 施加），因此归档以最终锁的 `design_contract` 为权威，要求
   `run_specs` 恰好覆盖 64 seeds × 2 条件，而不是从 config 反推。

未申报的 `ensemble_stationarity_report.json` 只作只读一致性输入与 provenance 哈希，
不进入 Gate——不追溯扩写已执行的产物契约。

测试 26 项，含变异检验（丢快照载荷、marker 绑定他 binary、未授权锁、Gate 与其自身声明
不一致、声明契约不符、越界产物、锁冻结了别的设计）。变异检验确认：禁用快照校验或
禁用 Gate 合取校验后，对应测试确实失败。

### 遗留残余

S18（存储顺序界限在 temperature=0.0 标定、参考配置运行在 0.5）仍未关闭，由已冻结的
V1G-ORDER-THERMAL-C4 探针负责判定。定量上看它不威胁本次结论：E1-C4 的最小主效应
（occupancy_entropy，+0.0818）是最小 SESOI（0.025）的 3.3×，而 S18 涉及的是数值误差界限，
需要该界限再增长一个数量级才可能侵入判定。E1-C4 jobctl 台账中的提交时刻（08:10）
与实际不符（run 目录创建于 10:09、结果写于 15:17），属记账瑕疵，不影响证据链。


## 4.10 seeds 互斥台账审计（2026-09-17，纯代码，为 E2-C4 授权前提）

E2-C4 的设计契约要求 seeds 全新且互斥，而**此前并不存在覆盖全部历史 job 的审计**：
`preflight._check_seeds` 只检查 `seeds.txt` 存在与非空、P0 是否 ≥3 个，不跨 job；
`prepare_cycle4_confirmation._assert_e1_seeds_unused` 只单向护住 E1 的 64 个，且只看
`config.json` 的 `seeds` 字段。本次把该审计实现为 `seeds-audit` 子命令。

**三条通道。** 审计扫描每个 job 的
（1）`seeds.txt`；（2）job JSON 的**顶层** `seeds`/`seed` 字段；
（3）`result.json`/`manifest.json` 运行标识里的 `seed-<n>` 子串。
前两条是"我抽了什么"的声明，按**消耗**记账；嵌套块（如 V1P 的 `target_design.seeds`）
命名的是被指向的设计，按**引用**记账。

**更正：运行标识里的 seed 默认是"消耗"，但它可以是"引用"，两者不能混。**
本节初稿曾断言 `V1D`/`V1BD`/`V1CD` 三个 job"实际消耗了 `6101/6203/6301/6407/6503`"——
**此说法错误**。经查证：`V1BD` 与 `V1CD` 的 `result.json` 里 **一个 `seed-<n>` token 都没有**；
`V1D` 有 108 处，但只是**标识它重分析的上游 V1 run**——其 `config.json` 声明了
`source_experiment`/`source_workspace`/`expected_source_runs`，其 `seed_waiver.txt` 亦明写
"确定性重分析…不产生随机数"。因此这 5 个 seed 是 **V1D 的引用，不是它的消耗**。

这个错误有连带后果：初稿把 V1D 的引用当作消耗，于是凭空造出一个 `V1 ↔ V1D` 的
"seed 重叠"，并为此在 `SEED_REUSE_COMPONENTS` 里加了一个"V1 谱系"component 去合法化它
——而**这个重叠根本不存在**，V1P 实际只消耗 `6007`（唯一，无重叠）。这正是"先归纳约定、
再为它的例外编理由"的典型失误。**该 component 已删除**，重叠组由 96 降为 91，component
由 4 个降为 3 个。

处置改为显式声明而非静默推断：

- **默认按消耗记账**，方向刻意选在 fail-closed 一侧：多算只会产生一个**假重叠**（报错逼人
  声明真相），少算则会**静默掩盖**真实复用。
- `SEED_REFERENCE_JOBS` 登记"运行标识是引用"的 job，并**要求其 config 里确有
  `source_experiment`** 与登记值相符——声明必须被 job 自身的记录佐证，而不是凭登记表取信。

**实测台账。** 28 个 job、**211 个不同 seed**（范围 101–12241）、**91 个重叠组**，
归属于 **3 个 component**（B0 谱系、E0/E1/E2 Cycle 1–3 谱系、V1F↔V1G 配对；后两者为
`intended`，E0/E1/E2 为 `grandfathered`）。审计对未登记的跨 job 复用直接报错，而 E2-C4
故意不在 `SEED_REUSE_COMPONENTS` 内，因此它一旦撞用旧 seed 会在提交前失败。
component 的 `status` 字段**纯描述、不参与放行**——放行只看"成员集合是否包含全部消费者"，
有一条测试专门反转标签以锁住这一点。

**另一处缺口：沉默不等于确定性。** 一个既无 seed 证据、又无 `seed_waiver.txt` 的 job，
其 seed 来源不可核验，审计直接报错。同时把"无 seed 证据"的 10 个 job（V0 系列、V1BD、
V1CD、V1ED）显式列进报告，使台账的覆盖范围**可被看见**，而不是被一句"覆盖全部 job"
掩盖——一 job 若什么都没记录，任何审计都看不见它。

**顺带发现的两处历史记账缺陷（仅登记，不追溯修改）。**

| 缺陷 | 事实 | 处置 |
|---|---|---|
| seed 撞用 | `E0-NUMERICS` 与 `E1-MATCHED-LANDSCAPES` 共用 `1103` | 登记为 grandfathered |
| 非素数 seed | `6407`、`6503`（V1）与 `9071`（V1C）不是素数 | 报告而非报错 |

**非素数的问题已查实，不再以"约定"含糊带过。** `cfg.random_seed` 只作为 `mt19937_64`
的初始状态、以及 `random_seed + rank × 1000003` / `+ rank × 999983` 的**派生基点**被使用
（`main.cpp:171/331/537`，`config.hpp:167`，`config.cpp:172`），代码中**没有任何对基点
素性的依赖**。仓库里出现的素数（`1000003`、`999983`、`2^40` 间距，以及
`DEVELOPMENT_PLAN.md:789` 的 `base_seed + rank_id × large_prime`）都是**派生偏移**，被误
沿用到了**基点选取**上。因此唯一能证成的硬要求是**唯一性**（不同 job 必须抽到不同流）；
素数性对基点无功能作用，其选取理由在仓库中**无记载**。三者落在非确认性实验里且已冻结，
故报告而不失败，仅在生成新 seed 时保证素数。

（附带一条**已查实**、对冻结 pool 有用的事实：rank 派生偏移为 `1`、`1000003`、`999983`，
所以多 rank 跑时两个 seed 若相差恰为偏移量的整数倍，会在相邻 rank 上撞到同一流。E2-C4
声明 `nprocs=1`，rank 恒为 0，该别名不可能发生；对将来多 rank 的 job，pool 窗口宽度应远
小于最小偏移量。）

**一个刻意留下的显式决策。** `--pool-min/--pool-max` **没有默认值**：E2 设计文档只写了
"未出现的素数"而未给窗口，把这个边界隐式定下来正是要避免的事。它应与 R 一同写入
E2-C4 的 lock。示例：`12300–13000` 含 77 个未用素数，`--propose 32` 确定性地给出最小的 32 个。

**测试**：`tests/test_prepare_cycle4_confirmation.py` 新增 **21 项**（三条通道各自的抓取、
sentinel 处理、嵌套 `seeds` 判为引用、重分析 job 的重分类与其 `source_experiment` 佐证、
单文件内重复、`seeds.txt` 与 config 不一致、未登记复用报错、已登记复用通过、`status` 标签
不参与放行、无证据且无 waiver 报错、无证据但有 waiver 通过、非素数不报错、池与提议的边界，
以及一项对真实仓库跑全量审计的集成守护，其中显式锁住"V1D 不得被记为消费者"）。
全库 **262 项**测试通过。
