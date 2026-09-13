# 模拟器修复后复审：剩余问题、检查方法与修复计划

日期：2026-09-08。性质：工作区静态复审与后续实施计划，不是数值验证通过报告。

## 1. 结论与本次检查范围

本轮修改已解决或改善多处问题：无噪声积分分支的摩擦项已经补齐；交换随机数已经使用稳定 GID 和 seed；零财富端点可以进入交换；稳态指标集合恢复了 Moran's I 和财富方差；cell 尺寸纳入了 exchange_cutoff；interval 归一化前移。

但是，当前版本仍不适合直接启动新的确认性实验。主要阻塞点已经从“缺少基本修复”转为：NaN 没有贯穿分析数据契约、校准的覆盖性与失败语义不完整、no-exchange 对照实际上仍有交换，以及异常财富不能使任务失败。

审查对象是 HEAD `d4373544461bfbb7cf0047086ae83a95eaac4eb1` 上的未提交修改，而不是一个已冻结的 Cycle 4 commit。文件 SHA-256 见 [复审基线](simulator-review-2026-09-08-baseline.json)。后续继续修改时，应重新生成基线，不能仅凭相同 HEAD 认为实现一致。

已执行：

- 阅读改动、相关调用链、测试源码、改进台账及旧校准/参数锁。
- Python 改动文件 AST 语法解析：通过，不导入或执行实验脚本。
- 对改动 C++ 实现及交换/积分器测试执行 `c++ -std=c++20 -fsyntax-only`：非 MPI、非 OpenMP 路径通过。
- `git diff --check`：通过。

未执行：C++ 链接、CTest、pytest、OpenMP/MPI 编译运行、umi 数值实验、旧数据重新分析和服务器任务核实。语法通过不代表测试通过，代码里增加了测试也不代表已经运行过。

本次仅新增复审文档与基线记录，不修改用户正在修复的源代码，不覆盖旧参数锁、结果或台账，不操作服务器任务。

## 2. 上轮 S01–S11 的复审状态

| 上轮问题 | 本轮判断 | 下一步 |
|---|---|---|
| S01 空间缺财富反馈 | 未改变，是当前模型结构 | 修正 E2 解释；不要为了非零效应临时加反馈 |
| S02 零财富吸收 | 原来的提前跳过已修，边界过程尚未验证 | 检查锁定参数、负值、非有限值、边界驻留 |
| S03 稳态指标缺失 | 指标恢复；稳态/精度判定仍未完整恢复 | 处理未定义指标，增加分窗口与精度检查 |
| S04 平坦景观伪零误差 | 底层常数相关改 NaN 正确；上下游未适配 | 先修数据契约，再做非退化校准 |
| S05 温控干预 | 新增累计日志；干预仍存在 | 结构化诊断、实际温度与参考动力学验证 |
| S06 无噪声摩擦遗漏 | 代码修复，测试源码已新增 | umi 上 OpenMP ON/OFF 分别运行回归 |
| S07 seed/GID | 单对随机流定义已改善 | 补多粒子重排、动态状态及重启检查 |
| S08 固定原地顺序 | 未修，仍需测量偏差 | 同物理状态不同存储/遍历顺序对照 |
| S09 source–sink 因子 | 未改变 | 明确组合通道估计对象 |
| S10 邻域/配置/MPI/重启 | 部分修复 | 完整模型半径、非有限参数、MPI 和重启仍有问题 |
| S11 性能 | 未处理，当前不应先优化 | 正确性基线冻结后做 |

## 3. 问题分级

P0：阻塞新确认性结果或使对照解释错误。P1：错误配置、受支持模式或数值可信度的重要缺陷。P2：测量精度、诊断和完整性改进。

“已确认”指代码路径明确，不表示已实测其在当前参数下的效应大小。“待验证”指风险大小或长期行为需要运行。

| ID | 优先级 | 状态 | 问题 |
|---|---|---|---|
| R01 | P0 | 已确认，新修改引入的接口断裂 | NaN 进入稳态报告，严格 JSON 写入会失败 |
| R02 | P0 | 已确认，新修改扩大漏检 | E0 把所有非有限指标当退化排除，空收敛集合也能通过 |
| R03 | P0 | 已确认，修复未贯穿 | 缺 Spearman 校准仍可被加载，确认分析稍后 KeyError |
| R04 | P0 | 已确认，遗留 | no-exchange 实际保留均分回复；部分参数被默认值覆盖 |
| R05 | P1 | 已确认，异常运行可被标完成 | 负财富计数不完整，NaN 不拒绝，诊断不接失败 Gate |
| R06 | P1 | 已确认，遗留 | 只检查线性漂移，ESS 不参与结果有效性判断 |
| R07 | P1 | 已确认，部分修复 | validate_config 仍接受 +Inf、缺失 grid 路径及危险参数 |
| R08 | P1 | 待验证 | 零财富回流、交易顺序与随机复现缺代表性测试 |
| R09 | P1 | 已确认/影响待验证 | 温控只记录累计日志，输出能量与状态可能不一致 |
| R10 | P1 | 已确认，特定模式 | 邻域修复未覆盖 mate/plague；MPI 主循环未接 halo |
| R11 | P1 | 已确认，特定模式 | restart 跳过已保存配置，RNG 不恢复 |
| R12 | P2 | 已确认/影响待验证 | CSV 精度、全程财富检查与分层状态报告不足 |

## 4. R01：未定义指标需要状态契约，不能只把 0 改 NaN

**证据。** `landscape_study.py:356` 起，常数 Spearman/Moran 返回 NaN；`run_landscape_study.py:1005` 给所有非 E0 条件使用同一稳态指标集合。E1 在 `default_conditions` 中仍包含 flat 条件，`mean_metrics_for_run` 将其资源—密度 NaN 序列传入 `stationarity_diagnostics`。诊断中 slope、漂移等仍是 NaN。`analyze_runs:1630` 先写 stationarity_report，而 `write_json:674` 使用 `allow_nan=False`。

**后果。** 默认 E1 的 flat 条件可以在最终效应聚合之前触发严格 JSON 序列化失败。这个 flat 是诊断条件，不能因为它不属于确认性对照就认为问题不会发生。E0 的稳态集合仅包含财富，因此不能概括为“E0 必定同样崩溃”。

**检查方法。** 在 umi 的独立测试 workspace 中生成三个以上手工快照，资源矩阵为常数，财富为有限正数，调用与 E1 相同的 mean_metrics → analyze/report 链。当前预期：报告包含非有限量，写入失败。再用非平坦资源、正常密度作为阳性对照。

**修复。** 内部计算允许 NaN 表示未定义，但对外指标应为 `{value: null, status: undefined, reason: constant_resource}`；对数值污染应使用 `status: invalid`。每个“实验×条件×指标”明确必需或诊断属性。诊断 flat 的相关可以 not_applicable；确认性必需指标未定义则应 blocked/inconclusive。禁止 `allow_nan=True`、统一填零或悄悄丢弃。

**验收。** E1 flat 能生成合法 JSON 并保留原因；非平坦确认指标异常时不能判通过；所有报告可用严格 JSON 读取。

## 5. R02：非有限值不能统一排除，空集合不能通过收敛 Gate

**证据。** `aggregate_e0:1198` 对任何非有限值都 `continue`，没有区分常数相关、Inf 和数据损坏；`dt_convergence` 使用 `all(value <= 0.02 for value in convergence.values())`。全部指标被移除时，空集合 all 返回真。财富 Gini 等本应必需的指标异常也会被同样排除。

**检查方法。** 在现有 E0 手工 rows fixture 上分别注入：仅 Spearman 常数退化；一个 Gini=NaN；一个 entropy=+Inf；四个收敛指标全部非有限。保持其他独立检查有限。最后三类必须失败，不能被标记为普通 undefined_degenerate。

**修复。** 上游保留异常原因；为每种校准场景声明 required_metrics / expected_degenerate_metrics；所有必需指标有限且样本完整才评估收敛。空 required 集合、空 convergence、重复种子及不完整配对均应拒绝。明确平坦财富测试与非平坦空间校准是不同证据角色。

**验收。** 坏值注入必失败；已声明的平坦退化允许生成“部分校准结果”，但不得声明覆盖全部确认性指标。

## 6. R03：校准覆盖性必须在运行前验证

**证据。** 新 E0 正确地不再产生退化 Spearman 的 SESOI；`load_e0_calibration:974` 仅检查 SESOI 是非空 dict；`apply_holm_and_sesoi:998` 随后直接索引 `sesoi[metric_for_key[key]]`。

**后果。** 缺主指标的校准仍可被加载，昂贵实验完成后才遇到缺键错误。如果直接沿用旧校准又会重新引入旧的 1e-6 退化阈值。单独校验哈希无法证明校准与新核兼容。

**检查方法。** 写一个 pass=true、只有财富阈值的校准 fixture，用正确 SHA-256 调用 loader，再进入主指标效应标注；当前 loader 接受而后续缺键。再检查“阈值齐全但模型版本不符”的 fixture。

**修复。** 在执行前 Gate 检查主指标覆盖、有限阈值、校准场景、模型/积分器/边界/RNG 版本、参数适用范围。新增非平坦场校准，不补人造阈值。不要求编译后二进制必须跨平台逐字节相同，但必须有明确的构建与源码兼容证据。

**验收。** 不完整/不兼容校准在任何生产运行前被拦截；错误明确列出缺失指标或版本。

## 7. R04：no-exchange 对照和参数传递存在确定错误

**证据。** `default_conditions` 的 clustered-no-exchange 只设置 exchange_rate=0、noise=0，没有关闭 reversion；`prepare_inputs:621` 使用 `condition.get("exchange_reversion_rate", 1.0)` 覆盖 common_cpp_config，最终 k=1。交换核即使 eta=0、noise=0，仍执行 `dt*k*(0.5-share)`。

**可手算复现。** 两粒子财富 (10,2)，epsilon=1，dt=0.01、k=1、eta=noise=0，均分回复使第一端减少 0.04、第二端增加 0.04，得到 (9.96,2.04)。这不是关闭交换。E0 的等财富 no-exchange 恰好掩盖此缺陷，因为其回复项为零。

**第二个问题。** 在 B0/E1/E2 等未显式填写 condition reversion 的路径，即使全局配置 k=0.7，也会被覆盖为 1.0。当前全局锁值恰好为 1.0，因此这里不能声称旧锁定运行已经因该覆盖改变 k；但新校准和参数扫描会被破坏。

**检查方法。** 准备 no-exchange 生成配置，断言三项交易速率均为零或模块显式关闭；用不等财富对检查完全不更新。再用全局 k=0.7、无条件覆盖以及显式条件 k=0.2，检查生成 cfg 分别为 0.7/0.2。

**修复。** 首选清晰的 exchange_enabled 开关，并保证诊断/网络记录一致；若仅用参数关闭，必须同时关闭 drift/noise/reversion。默认优先级统一为 condition → global → default。run_specs 和参数锁审计记录实际 reversion，不能只记 eta/noise。

**验收。** no-exchange 在任意合法不等财富上严格不交换；显式覆盖与继承测试通过。旧 clustered-no-exchange 不再用于声称“完全关闭交换”的结论，其余结果的影响单独评估。

## 8. R05：负财富与非法数值仍不能可靠失败

**证据。** `resource_exchange.cpp:129` 先检查 total<=0 再检查负端点。因此 (-2,1)、(-1,-1) 直接退出，负值计数仍为零；(-1,10) 虽计数也只是 return。NaN 比较不触发这些分支，可传播至财富。主程序最后只打印累计诊断并 `return 0`。执行器按退出码和快照标完成，没有将这些诊断接入健康 Gate。

**检查矩阵。** (-1,10)、(-2,1)、(-1,-1)、(NaN,10)、(+Inf,10)、负 epsilon、NaN epsilon；再将非法粒子隔离到没有邻居的位置。必须检查全体粒子状态，而非只检查发生交易的 pair。

**修复。** 在交易前校验有限财富/能力；负值政策先于零总额分支。按模块阶段做全体状态检查，覆盖生产/消费/衰减后以及最后一步。受控研究模式中非法状态生成结构化 failure、非零退出，执行器禁止复用为成功结果。若完整人口模型允许短暂负财富直至死亡，应单独明确阶段不变量，不能统一误报也不能放任 NaN。

**验收。** 非法 fixture 均产生可定位失败；不依赖 diag 指针存在；既无邻居也能检测。现有 `test_negative_wealth_is_declared_not_skipped` 实际只检查计数，需改为验证业务失败语义。

## 9. R06：恢复指标列表不等于恢复稳态证据

**证据。** `stationarity_diagnostics:654` 仍为 `passed = drift_pass`；ess_pass 仅记录。一个对称先升后降的序列可以拟合出零斜率，却明显不是稳定平台。现有 `test_stationarity_drift_decides_over_ess` 正在固化旧政策。

**检查方法。** 比较常数平台、平稳噪声、单调漂移、U 型轨迹 `[0,1,2,3,2,1,0]`、缓慢振荡和高自相关平台。明确区分“检测不到趋势”和“均值估计足够精确”。用固定 synthetic fixtures 验证判定，不在确认结果上选择阈值。

**修复。** 输出 stationarity_pass 与 precision_pass 两层；ESS 不是稳态的数学定义，但不足的有效样本不能自动支撑高精度效应结论。增加前后子窗口和多个相邻窗口比较，报告时间相关的不确定性；保留固定延长上限与失败处理。E0 的 zero_wealth_fraction 目前未纳入稳态集合，应根据边界校准角色补上。

**验收。** 不能只凭单条线性斜率或 Gini 平台宣称整体稳态；确认性分析同时具备观测量稳定与目标精度证据。低 ESS 可以继续诊断，不能通过删除字段关闭问题。

## 10. R07：配置 fail-fast 仍不完整

**证据。** `validate_config:303/306/317` 使用 isnan 而不是 isfinite，+Inf 温度、摩擦和速率仍通过；domain 只检查大小；grid 的检查要求路径非空才生效，因此 terrain_type=grid 且空路径会落入主程序其他地形分支。未知键和 malformed line 仍只 warning；parse_bool 的未知字符串会变 false。

**检查方法。** 使用表驱动配置 fixture：dt=0/NaN/Inf，temperature/friction/rate=Inf，非有限边界，grid 缺路径/目录/损坏文件，零或负 interaction_range，terrain_barrier_scale=0，density interval 边界，非法布尔和拼错键。测试“配置解析→validate→资源加载”完整链，不只调用 validate。

**修复。** 对所有需要有限的实数用 isfinite；检查正半径、合法枚举/整数范围和模块依赖；grid 必须有可读取且解析成功的文件。确认性模式严格拒绝未知键/非法布尔，兼容模式若保留必须显式标记。更新间隔默认化须记录原值与解析后值，禁止静默改变锁定参数。

**验收。** 错误在分配网格、计算噪声和启动时间循环前被拒绝，报错包含字段和值。

## 11. R08：边界和随机数修复需要代表性测试

现有零财富回流测试采用 eta=0.003、noise=0；旧锁定参数却是 k=1、eta=0.5、noise=0.05。单零端点 D=-1 时，确定性漂移 k/2-eta=0，回流依赖噪声和截断。这是参数性质，不应误报为删跳过条件仍无效。

现有重排测试仅有两个粒子，并交换了 GID 对应的位置；在无地形单对测试中距离相同，因此可测试标签方向，但不能证明一般存储重排不变。固定顺序原地交易也尚未改变。

**检查方法。** 补锁定参数下正反边界、噪声开关、多个 seed、dt/dt2/dt4、零质量和边界驻留。构造至少三粒子共享邻居，保持每个 GID 的位置、财富、epsilon 全部不变，只置换存储数组；分别检查单对随机符号与最终多对统计。

**修复原则。** 先测再决定是否改变更新顺序；不要求随机模型每个 seed 的边界都立即恢复。若顺序偏差超数值容差，用固定规范顺序或经过验证的随机交易顺序；不可直接回退到可超额扣款的同步 dw 累加。

**验收。** 相同 seed/模式可重放；不同 seed 重采样；单对随机定义不依赖存储；多对顺序差异有收敛界。新 `active_pairs` 实际表示进入更新的 pair，包括 dw=0，不能直接作为活跃交易数；另记 nonzero_transfer_pairs。

## 12. R09：温控可观测性与状态输出

新增 trigger_count/max_correction 是有用的诊断，但仍仅在结束时打印 rank 0 累计值，没有时序、动能移除量、结构化文件和 Gate。崩溃运行可能没有最终统计。

`integrator.step` 返回的 `state.kinetic_energy` 计算在后续 river、climate、主温控之前；随后 health diagnostics 使用旧 state。因此至少在这些修正触发时，报告能量不是当前动量能量。不能据此断言所有输出场景都有问题。

**检查方法。** 人工设置高初始动能触发温控，在同一步比较 state、温控后重新求和动能及快照动量；检查无修正条件下保持一致。对参考 Langevin 做开关温控、同物理时长、三级步长的分布对照。

**修复。** 分别定义并记录 pre/post 动能，健康诊断采用明确的实际时刻；分窗口输出结构化 health.json。温控和力截断暂时保留 legacy 对照，在新模式中选择并验证清楚的目标过程；没有统计验证前不把计数新增视为 S05 完成。

**验收。** 快照状态与对应报告能量一致；所有修正可追溯，触发率及效果可分析。

## 13. R10–R11：完整模型、MPI 与重启

### 13.1 邻域覆盖

cell 尺寸已纳入 exchange_cutoff，这是有效修复。但 reproduction 使用 mate_range、plague 使用 infection_radius，它们仍可超过 cell 尺寸。固定邻格遍历会漏掉实际半径内跨多格的粒子。

检查：人工构造相距两格、距离小于 mate/infection 半径的 pair，与 O(N²) 暴力枚举对照。修复可统一所有启用模块的最大半径，或按 query radius 动态决定扫描格数。确认性模式这些模块关闭，不能将其混同于当前受控实验缺陷。

### 13.2 MPI

当前 main.cpp 调用 discover_neighbors/redistribute，但没有将 halo 交换接入每步力/交换计算；integrator 的 cells 基于本 rank 粒子。跨 rank 近邻可能缺失，稳定 GID 不能解决缺交互。

检查：两个 rank 各放一个相互作用半径内的粒子，对比单 rank 的力和交易量；随后检查全局守恒、密度和输出。修复前在确认性模式拒绝 nprocs>1。完整修复需定义 ghost 更新、跨 rank pair 所有权、财富归还和全局指标，不能只插入一个 halo 函数调用。

### 13.3 Restart

`checkpoint.cpp:380` 读取后直接跳过 config block；main 默认/override cfg 用来初始化新的 RNG，未恢复 integrator/pop_rng 随机状态。于是无 override 重启可能改参数；即使传相同 cfg，随机轨迹也会重置。

检查：固定 seed 连跑 T 与 T/2 保存后再跑到 T，对比每个 GID 状态；另测无 override、允许/禁止 override 和损坏 checkpoint。先要求同 rank/线程数可恢复，跨 rank 改变属于独立能力。

修复：恢复有效配置和所有必要状态，包括 RNG/分布缓存、ID 分配器、人口模块内部状态；或者在支持矩阵中明确禁止该模式承担确认性证据。读文件检查版本、尺寸、完整性和读取成功状态。

## 14. R12：观测精度与健康 Gate

CSV 快照仍为 `setprecision(8)`，而财富守恒容差达到 1e-8。当前财富误差由初始 CSV 与末尾快照重新求和，可能混入输出舍入。defaultfloat 的八位有效数字并不意味着小正财富必然被舍入到零，不能以此否定已记录的零财富事实。

检查：多种尺度财富与接近网格边界位置做写入读取往返，比较内存总量、CSV 总量及密度分箱。使用 double 的 max_digits10 或无损二进制作为权威数据；显示精度可单独降低。

mean_metrics_for_run 只在末尾所选快照中取 minimum_wealth，漏掉早期短暂负值；全程不变量应在模拟器内部按模块阶段累计并输出。结果至少拆为 execution_completed、numerics_valid、stationarity_valid、precision_valid、claim_supported，旧 pass 字段只能是清楚声明的合成规则。

## 15. 检查矩阵与推荐顺序

以下是待实施/待运行的用例，不是已通过清单。所有会执行研究脚本或模拟器的检查均在 umi 上进行；新增数值研究任务先经过代码对齐、preflight，完成后 reconcile。测试输入和构建/输出放项目内独立 workspace，不覆盖当前任务目录。

| 批次 | 拟定用例 | 层次 | 预期 |
|---|---|---|---|
| A | flat_metric_report_roundtrip | Python 端到端 fixture | undefined 明确，JSON 合法 |
| A | e0_nonfinite_required_metric_rejected | Python 聚合 fixture | NaN/Inf/空覆盖失败 |
| A | incomplete_calibration_rejected_before_run | 加载/执行边界 | 缺项和错版本提前阻断 |
| A | no_exchange_unequal_wealth_noop | C++ + cfg 生成 | 全关闭后不更新 |
| A | reversion_config_precedence | cfg 生成 | global 与 condition 正确传递 |
| B | invalid_particle_state_fails | C++ + 执行器 | 非法全状态失败且不得复用 |
| B | invalid_config_matrix | 解析/加载链 | 提前报错 |
| B | integrator_no_noise_omp_on_off | C++ CTest | 两模式摩擦回归通过 |
| B | stationarity_shape_precision | Python fixture | 非线性漂移与精度不足被区分 |
| C | locked_boundary_and_order | umi 小数值实验 | 边界/顺序误差可量化 |
| C | nonflat_dt_calibration | umi 校准 | 主指标覆盖且参数适用 |
| C | post_thermostat_energy_consistency | 主程序集成 | 报告与实际状态一致 |
| D | full_radius_oracle | C++ 小规模 | 与暴力枚举一致 |
| D | mpi_cross_boundary_pair | umi MPI | 通过后才能启用 |
| D | checkpoint_continuation_equivalence | umi 集成 | 支持范围内恢复正确 |
| D | snapshot_precision_and_health_gate | I/O + 执行器 | 精度与失败状态可追溯 |

现有 CMake 的 OpenMP 默认 OFF；只跑一次默认 CTest 无法覆盖原摩擦 bug。需建立 ON/OFF 两套构建，均开启 POLITEIA_BUILD_TESTS；先链接，再分别运行新增 integrator/exchange 及受影响旧测试。测试支持代码自身也应检查，不能只改断言让测试通过。

## 16. 修复工作包、交付与停止条件

### 阶段 A：先接通分析和对照语义

顺序：R01 → R02/R03 → R04。交付指标状态契约、校准覆盖检查、真实 no-exchange 配置和集成 fixture。进入下一阶段条件：默认设计的手工数据可以完成合法报告；坏数据不能通过；对照实际执行与名称一致。

### 阶段 B：让程序知道什么时候失败

处理 R05/R07/R09/R12；产出全程健康摘要和执行器失败传播。回归 R06 的统计判定，冻结 stationarity/precision 区别。进入下一阶段条件：注入异常从内核一直传到 result/completion，均不会成功复用。

### 阶段 C：小规模数值验证

验证 R08、积分器与非平坦 dt 校准；三步长保持相同物理总时长，不能把相同 seed 误当相同 Brownian 路径。记录边界质量、真实非零交易比例、温控影响、主指标误差和多窗口稳态。

预算先由小样本 umi benchmark 估计；没有实测不承诺运行时长，也不复用旧 E3 大规模预算作为新周期授权。若边界/稳态持续不满足要求，回到模型定义，不删指标、不把异常重新归类为退化。

### 阶段 D：冻结新确认性版本

完成 R01–R09 中适用的阻塞项后，冻结新 model/analysis/config 版本与 Cycle 4 参数锁，重写 E2 的结构隔离与 source–sink 解释。单 rank、明确线程数作为参考；MPI/restart/完整人口模型若尚未通过，显式排除，不要求先修完所有模式才开展受控研究。

旧 E0–E3 保留原版本身份；修复后数据必须进入新实验 ID。旧 no-exchange 证据标明其实际为“关闭能力漂移和噪声、保留回复”。不追改历史原始结果；更新解释和支持状态必须有审计记录。

## 17. 本轮关闭问题的证据要求

每个 R 项关闭必须包含：复现输入、修复前行为、修复 commit、修复后输出/测试报告、执行环境、残余限制。推荐在现有 remediation 台账追加复审 ID 映射；本文不替用户将“本轮”自动改为“已完成”。

可以先关闭已明确修复并在 umi 回归通过的 S06，以及完成契约测试后的 R01/R03/R04。长期稳态、顺序影响和数值分布问题必须有独立实验；不能用一次编译或两个 seed 的单对测试替代。

最终判断：本轮修改方向有效，但尚处于代码修复阶段。最值得立即处理的是 NaN/校准接口和 no-exchange 语义，其次是异常失败链与稳态精度；扩大模拟规模应排在这些检查之后。
