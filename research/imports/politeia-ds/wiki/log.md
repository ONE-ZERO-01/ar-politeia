# Politeia Wiki Log

> 按时间倒序记录项目的 ingest、变更、query、lint 等事件。
> 格式约定：`## [YYYY-MM-DD] <类型> | <标题>`
> 类型：`ingest`（新资料/新功能摄入）、`change`（代码/文档变更）、`query`（有价值的分析存档）、`lint`（健康检查）、`decision`（设计决策）
>
> 快速查看最近条目：`grep "^## \[" wiki/log.md | tail -10`

---

## [2026-06-12] query | Cycle 4 反思：人口爆炸是自我惩罚—先断繁殖再看征服

- **核心收敛**：三个 Cycle 的共同发现——conquest 正常(cbp=0.02→1.0)→人口仍爆炸(5-8×)→继承碎片化速度超征服合并→state 从不涌现
- **系统诊断**：征服从未触发并非 bug——debug 日志验证 cbp=1.0 时 23K 征服/interval
- **三重矛盾**：征服需要层级但层级放大人口；大政体需时间但每步越来越慢；所有参数互相对抗
- **策略修正**："先阻断人口爆炸，再让征服独自推过 state 门槛"——Phase 1: fertility 摸底(5e-5, 1e-4)→Phase 2: slf 扫描(人口受控)→Phase 3: 中欧对照
- **反思全文**：`reflection-cycle4.md`；状态 → `EXPERIMENT | cycle=4`
- M1.13 fertility 摸底已启动 (Zeus 后台, 2 runs × ~10 min)

- **核心发现**：全模块开启下（M1.10）H=5-6 但 s=0、e=0 — no states, no empires
- **根因分析**：人口膨胀（10K→55.6K）稀释层级——2524 个政体平均仅 22 particle/polity；继承衰减过早碎裂；税收/忠诚参数过于保守
- **方法论问题**：Cycle 1 教训被重复——先验假设过乐观（"50K 粒子+10K 步能产生 state"未经小规模验证）、计划仍过于宏大（M1.10→M2.1 直接串行，中间无分析和参数调整）
- **策略修正**："先找到能工作的参数，再考虑能工作的规模"——先 M1.11 找最优 slf → M1.10-opt 验证 state 形成→ 只有成功后 M2.1
- **行动**：建议终止 M2.1（当前 run ETA 8408s，s=0 概率高），直接进入参数调优
- 反思全文：`research/physics-validation/reflection-cycle2.md`；状态 `state.md` → `REPLAN | cycle=3`

## [2026-06-11] change | M1.10 消融实验完成——层级形成必要条件验证

- **6 种消融配置**（baseline / no_loyalty / no_conquest / no_culture / no_lc / all_off），各 10000 粒子 5000 步
- **Core finding 1**: loyalty 是层级形成的**必要条件**——loyalty=true → H=5-6; loyalty=false → H=0（100% 决定）
- **Core finding 2**: conquest（征服）合并政体——polities 从 2524 降至 582（77% 减少），但不影响 H
- **Core finding 3**: culture（文化同化）在 5000 步尺度上效果微弱（polities 变化 <10%）
- **Core finding 4**: 所有配置均 **s=0, e=0**——无国家/帝国形成（人口不足/步数不足/阈值过高）
- **次要 bug**: `run_all.sh` 中 `\${OUT}` 转义导致消融输出写入同一字面 `${OUT}` 目录，CSV 相互覆盖
- 分析更新至 `analysis-P0.md`；M1.11 继承衰减扫描配置已准备

## [2026-06-11] change | M2.1 China vs Europe 启动 + M1.11 配置就绪

- M2.1: 6 runs (China×3 + Europe×3, 50K×10000 steps)，串行执行中（Phase 2）
- 第一个 run (china_seed42) 进行中：3000/10000, N≈140K, ~0.9 step/s
- M1.11: `m1.11_template.cfg` 就绪，扫描 succession_loyalty_factor ∈ {0.70, 0.75, 0.80, 0.85, 0.90, 0.95}
- 状态更新至 `state.md` → `current_stage = EXPERIMENT`

---

## [2026-06-11] decision | AutoResearcher 引入两阶段写作策略（长文→凝练→审稿）

- 将原 `WRITE` 阶段拆分为两阶段：
  - **WRITE-COMPREHENSIVE**：生成内容丰富的完整长文（`paper/comprehensive/`），作为权威记录和后续凝练的唯一源头。不做审稿。
  - **WRITE-JOURNAL**：从完整长文中凝练 Nature/PRL 等期刊的适配版本（`paper/nature/`、`paper/prl/`），只做减法不做加法。
- 7 个 Stage 流程：`PLAN → EXPERIMENT → ANALYZE → WRITE-COMPREHENSIVE → WRITE-JOURNAL → REVIEW → DECIDE`
- REVIEW 只针对凝练后的期刊版本；发现科学问题 → replan 回循环 A 补实验 → 依次重写长文和期刊版本；仅叙事/格式问题 → revise 回 WRITE-JOURNAL
- 新增 `rules/journal-formats.md`：Nature/PRL 的格式要求、叙事策略、提炼清单和通用提炼原则
- 新增 `project.json` 中的 `journals` 字段，Agent 据此生成对应期刊版本
- 版本号保持 v0.4.0
- 详见 `autoresearcher.md`、`workflow/04-writing-review-and-decision.md`、`rules/journal-formats.md`

## [2026-06-11] decision | AutoResearcher 引入两层论文结构（全量论文→蒸馏投稿）[已废弃，被上述方案替代]

- 弃用：WRITE/DISTILL 命名 → 改用 WRITE-COMPREHENSIVE/WRITE-JOURNAL
- 弃用：`venues/*.json` 独立期刊配置 → 改用 `rules/journal-formats.md` + `project.json` 中 `journals` 字段
- 弃用：`state.md` 中 `distilling_venue` 字段

## [2026-05-19] change | v17 @5k 验收报告脚本

- `scripts/write_v17_5k_query.sh`：checkpoint 就绪后生成 [[query-2026-05-19-v17-5k]] + post_v17_hierarchy_check

## [2026-05-19] query | v17 中期反思 v12（@1900，待 @5k 验收）

- [[reflection-2026-05-19-v7]]：repair 73039 解读框架、五维待验、@5k 写 query 计划

## [2026-05-19] query | 阶段总结与反思 v11

- [[reflection-2026-05-19-v6]]：v14c 终局、v17@900、双目标、MPI 运维债、五维待验

## [2026-05-19] change | v14c 完成 + v17 全量启动

- v14c step 20000：N=59671，H=53，checkpoint 环 20996；[[query-2026-05-19-v14c-final]]
- 修复：MPI 僵死阻塞 → `v14c_is_done.sh` + `cleanup_stale_v14c.sh`
- v17 运行中：step200 N=87111，0.2 step/s，ETA~22h；@5k 待 `post_v17_hierarchy_check`
- `run_full_v17.sh`：mpirun 多路径探测 + `bash` 调用 watcher

## [2026-05-19] change | v17 管道兜底 + 终局报告增强

- `scripts/ensure_v17_pipeline.sh`：v14c 已停且 v17 未跑时自动摘要并启动
- `on_v14c_complete.sh`：含 compare 表与 v17 五维验收对照
- `examples/genesis_100k_v17_output/README.md` 验收说明

## [2026-05-19] query | v14c checkpoint 层级复验 @5k/10k/15k

- v14c @18900 进行中；复跑 `analyze_hierarchy_checkpoint.py`：@15k 环 22077、max_depth=52
- 对照表更新：[[query-2026-05-19-hierarchy-baseline]]

## [2026-05-19] change | v17 启动脚本 flock 防重复

- `wait_and_run_v17.sh` / `run_full_v17.sh` / `watch_v17_milestones.sh`：文件锁 + 已运行检测，避免多 waiter 重复启 v17
- v14c @18500：N≈59k，ETA ~1h

## [2026-05-19] query | 终局前夜反思：双目标验收矩阵 (v10)

- [[reflection-2026-05-19-v5]]：v14c @17900 快照；人口 step18k 正增长；v17 五维验收矩阵；帝国为瞬态→改用 largest_pop 标准

## [2026-05-19] change | v17 里程碑自动验收监视器

- `scripts/watch_v17_milestones.sh`：checkpoint @5k/10k/15k/20k 自动 `post_v17_hierarchy_check`
- `run_full_v17.sh` 启动 v17 时一并拉起 watcher

## [2026-05-19] change | v14c 终局脚本 + CASES 验证算例表

- `scripts/on_v14c_complete.sh` → `wiki/query-2026-05-19-v14c-final.md`
- waiter 在 v14c 结束后先跑基线摘要再启 v17
- `examples/CASES.md` 增加 quick_v16 / v17 / v14b 对照

## [2026-05-19] query | 双目标张力反思 (v9)

- [[reflection-2026-05-19-v4]]：层级修复 vs 帝国涌现；v17 验收双标准；hierarchy 改动检查清单

## [2026-05-19] change | v14c 政体时间序列 + v17 验收脚本

- v14c step 10000：1 帝国、H=48；checkpoint 层级分析已补入 [[query-2026-05-19-hierarchy-baseline]]
- `scripts/post_v17_hierarchy_check.sh`：v17 各 milestone 一键验收

## [2026-05-19] change | v17b repair 降频 + 基线 query

- `hierarchy_repair_interval=500`（附着仍每 100 step）；v17 cfg 已更新
- [[query-2026-05-19-hierarchy-baseline]]：v14c@15000 max_depth=52、环 22077；v16 H=4、零环

## [2026-05-19] change | v17 自动排队 + v14c/v16 对比工具

- `scripts/wait_and_run_v17.sh`：v14c 结束后自动 `run_full_v17.sh`
- `scripts/compare_hierarchy_runs.py`：横向对比 order_params 末行
- v14c @ step 15000：H=40（仍无 max_depth 限制），v16：H=4

## [2026-05-19] change | v16 层级修复验收通过

- step 3000 / 10k→26k 粒子：**H=4**, 环=0, 政体 depth max=4
- checkpoint 与 `order_params` 一致；v15 的 depth=212 误报已消除
- 下一步：v17 全量 100k（`max_hierarchy_depth=10`）

## [2026-05-19] query | 层级修复三代迭代反思 (v8)

- 文档：[[reflection-2026-05-19-v3]]
- 要点：指标分裂 (H vs polity depth)、v15 半修复、验证规模与性能 regression
- v16 改用 10k IC + `is_ancestor_of` 限步；快速验收 H≤10、零环

## [2026-05-19] change | v16 层级图修复：防环 + 全路径深度限制

- **v15 验证结论**：全局 H=31 已下降，但政体 depth 虚高 (212)；checkpoint 发现 **22191 个 superior 环**
- **v16**：`would_create_cycle`、`repair_hierarchy_graph`、繁殖/投靠/世袭深度检查；`polity::get_depth` 环安全
- 快速验证：`examples/quick_v16_output/`（3000 step）
- **perf**：`repair_hierarchy_graph` 去除每粒子 `unordered_set` 分配；`chain_depth_of` 改用 stamp 数组
- 详见 [[wiki/troubleshooting#问题-19-层级深度异常--h209-链式增长无限制]]

## [2026-05-19] change | 推广文档补充 Git 执行层（§12）

- `docs/llm-knowledge-architecture.md` v3：Git / branch / commit / PR 与 wiki/log、L4 的分工
- `AGENTS.md` Change 流程明确先 commit 再写 log

## [2026-05-19] lint | 文档体系健康检查（首轮结构化）

- **ADR**：自 log 后补 ADR-001（docs/wiki）、ADR-002（UMI/Zeus）、ADR-003（知识架构）；`wiki/decisions/` 不再为空
- **模块**：`src/river`、`src/climate` 已补 `wiki/modules/river.md`、`climate.md`；index 已登记
- **当前焦点**：`DEVELOPMENT_PLAN.md` 顶部新增活跃项表
- **索引**：`wiki/index.md` 增加 decisions 表、反思专表；修复错误表格行
- **推广文档**：`docs/llm-knowledge-architecture.md` v2 — 成熟度模型、任务管理、反模式
- **待办**：L4 三文件尚未在真实复杂任务中跑通归档闭环；发版前重复 lint

## [2026-05-19] change | 项目管理短板改进 + 推广文档 v2

- ADR-001–003、`DEVELOPMENT_PLAN` 当前焦点、`AGENTS.md` decision/lint/反思约定
- 见 [[docs/llm-knowledge-architecture#17 Politeia 实例快照（2026-05-19）]]

## [2026-05-19] change | 撰写可推广的 LLM 文档管理架构总览

- 新增 `docs/llm-knowledge-architecture.md`（五层模型、docs/wiki 分工、工作流、上线路线图）
- `AGENTS.md`、`wiki/index.md` 增加交叉链接

## [2026-05-19] change | 安装 planning-with-files Cursor skill

- 添加 `.cursor/skills/planning-with-files/`（SKILL.md + 模板）
- 添加 `.cursor/hooks.json` 与 hooks 脚本（计划注入、进度提醒、阶段完成检查）
- `AGENTS.md` 增补「会话级规划」与 wiki 归档约定
- 根目录 `task_plan.md` / `findings.md` / `progress.md` 默认 gitignore（会话级工作记忆）

## [2026-05-09] bugfix | 代码审计发现并修复 4 个 Bug

### Bug 1 (严重): OpenMP RNG 数据竞争 — `langevin_integrator.cpp`

**现象**：多线程 OpenMP 模式下，BBK 积分器的随机力计算存在未定义行为。

**根因**：`#pragma omp parallel` 区域内，所有线程同时调用 `rng_()` 生成种子，但 `std::mt19937_64` 不是线程安全的。并发写入同一 RNG 对象是 C++ 标准禁止的 UB。

**影响**：模拟结果不可复现，可能导致随机数相关性和数值异常。

**修复**：在 `#pragma omp parallel` 区域**外**（主线程中）预生成每线程种子数组，各线程用自己的种子初始化独立 RNG。两处半步动量更新均已修复。

**文件**：`src/integrator/langevin_integrator.cpp` L116-L132, L157-L175

### Bug 2 (中等): `output_interval=0` 导致除零崩溃

**现象**：若配置文件中 `output_interval=0`，主循环中 `step % output_interval` 触发除零异常。

**修复**：`main.cpp` 循环开始前添加安全检查：`output_interval`、`compact_interval`、`density_update_interval` 若为 0 则强制修正为安全默认值。同时确保 `network_window = max(output_interval * network_window_factor, 1)`。

**文件**：`src/main.cpp` L533-L535, L417

### Bug 3 (中等): MPI 模式下 energy.csv 仅写 rank-0 本地能量

**现象**：多进程 MPI 运行时，`energy.csv` 中的动能、社会势能、地形势能只是 rank-0 上本地粒子的能量，而非全局系统能量。

**修复**：在 `write_energy()` 之前，对三个能量分量执行 `MPI_Allreduce(MPI_SUM)` 汇总全局值。仅在 `do_output` 步才执行归约，不增加每步通信开销。

**文件**：`src/main.cpp` L889-L897

### Bug 4 (低): MPI 进度报告显示本地粒子数而非全局总数

**现象**：进度行 `N=xxx` 在 MPI 模式下只显示 rank-0 的本地粒子数。

**修复**：使用缓存的全局粒子总数 `cached_global_N`（从 `compute_load_stats` 获取），在每次 rebalance 后自动更新。

**文件**：`src/main.cpp` L539, L556, L875

### 改进: 配置文件未知键警告

**现象**：配置文件中的键名拼写错误会被静默忽略，导致参数使用默认值而不自知。

**修复**：`apply_key_value()` 改为返回 `bool`，`load_config()` 对未匹配的键输出 `Warning: unknown config key 'xxx' at line N`。同时添加 `try/catch` 包裹值解析，报告解析失败的具体行号。

**文件**：`src/core/config.cpp` L23, L240-L260

---

## [2026-05-08] change | 补全单元测试覆盖 + 修复 bug

### Bug 1: `ClimateGrid::load_ascii()` 双波段 ASCII 文件降水数据全为零

**现象**：加载包含温度和降水两个波段的 ESRI ASCII 气候文件时，温度正常读取，但降水数据全部为 0。

**根因**：温度数据用 `file >>` 逐值读取后，文件游标停在最后一个数值之后、换行符之前。紧接着 `read_header()` 调用 `std::getline()` 读 6 行头部，第一次 `getline` 消耗了残留的换行符（得到空字符串），导致只实际读到 5 行头部，`NODATA_value` 行被当作降水数据解析，`file >>` 尝试解析字符串 `"NODATA_value"` 为 `Real` 失败，流进入错误状态，后续所有读取返回 0。

**修复**：在温度数据读取循环后、第二次 `read_header()` 调用前，插入一行 `std::getline(file, skip)` 消耗残留换行符，确保后续 `getline` 对齐到正确的头部行。

**文件**：`src/climate/climate_grid.cpp` L200

---

### Bug 2: `test_loyalty.cpp` 编译 warning — `[[nodiscard]]` 返回值未使用

**现象**：编译时 `test_loyalty.cpp` 中 3 处调用 `process_succession()` 产生 `-Wunused-result` 警告。

**修复**：对不需要检查返回值的调用添加 `(void)` 显式丢弃。

**文件**：`tests/test_loyalty.cpp` L167, L185, L198

---

### 新增测试覆盖（125 → 158 个测试）

| 模块 | 测试文件 | 测试数 | 覆盖要点 |
|------|---------|:------:|---------|
| 气候系统 | `test_climate_grid.cpp` | 12 | 程序化生成、纬度温度梯度、海拔递减率、耦合因子、Static/Drift/Seasonal 时变、漂移计划、ASCII I/O |
| 河流系统 | `test_river_field.cpp` | 10 | 合成河流（major_rivers/nile/china）、proximity 范围、河流力方向、走廊加成、ASCII/binary I/O |
| Checkpoint | `test_checkpoint.cpp` | 6 | Header 结构、记录大小、pack/unpack 往返、write/read 往返、文化向量保留 |
| IC 加载器 | `test_ic_loader.cpp` | 5 | 基本 XY 加载、全列加载（含 sex/culture）、缺失列默认值、非 rank 0 过滤、adam_eve 兼容 |

---

## [2026-05-08] change | 项目推送 GitHub + 分支管理

- 初始化 Git 仓库并推送至 `https://github.com/ONE-ZERO-01/Politeia`
- 建立分支策略：`main`（代码 + README，推送到 GitHub）/ `dev`（全部文件，仅本地）
- 移除 `env.sh`（含服务器路径敏感信息）和非代码文件，合并为单一 Initial commit
- 创建 `push.sh` 自动化脚本：从 `dev` 同步代码到 `main` 并推送
- 作者信息更正为 The One <wan-wb@qq.com>

---

## [2026-04-19] decision | 保留 `docs/`，与 `wiki/` 并列
- ADR：[[wiki/decisions/ADR-001-docs-wiki-split]]
- 约定：**不**把 `docs/` 全文整合进 `wiki/`；`wiki/` 负责 index、log、模块拆分；通过链接指向 `docs/`

## [2026-04-19] change | 输出目录整理到 examples/ 下
- 将根目录的 output_adam_eve, output_genesis, output_genesis_quicktest, output_historical 移入 examples/*_output/
- 删除无用的 output_demo_run 和 build/ 下的 6 个过期输出目录（含 ~750MB output_river*）
- 删除失败的 build-fresh/ 目录
- 更新全部 11 个 .cfg 文件的 output_dir 和 checkpoint_dir 路径
- .gitignore 改为统一通配 examples/*_output/

## [2026-04-19] change | 构建完整 LLM Wiki 三层架构
- 创建 `raw/`（papers/, datasets/, notes/）原始资料层
- 创建 `wiki/` 子目录：concepts/, entities/, modules/, decisions/
- 编写 `AGENTS.md`：Schema 约定（三层架构、Ingest/Change/Decision/Query/Lint 流程、页面格式）
- 拆分 `CODE_GUIDE.md` → `wiki/modules/` 下 8 个独立模块页（core, domain, force, integrator, interaction, population, analysis, io）
- 更新 `wiki/index.md` 反映完整新结构
- 更新 `docs/MOC.md` 增加 wiki 层索引
- `research-proposal.md` 确认为项目**活核心**，保留根目录，不移入 raw/

## [2026-04-19] ingest | 建立 wiki/index.md 与 wiki/log.md
- 参考 Karpathy LLM Wiki 模式，为 Politeia 建立持久知识层
- `wiki/index.md`：基于现有文档自动生成全局索引
- `wiki/log.md`：本文件，从今日起记录项目演化时间线
- 确认 `research-proposal.md` 为项目**活核心**，其余文档围绕其变动

## [2026-04-19] change | 新增 genesis_hyde_baseline 算例（1:1 人口）
- 新增 `examples/genesis_hyde_baseline.cfg`：4,501,152 agent = HYDE 3.3 全球基线人口
- 修改 `src/main.cpp`：IC 加载时用 `initial_particles` 预分配容量，避免反复 grow_to
- 更新 `examples/CASES.md`：增加 §1b genesis_hyde_baseline 说明
- 更新 `.gitignore`：排除大体积 baseline CSV 和输出目录
- 更新 `scripts/generate_genesis.py` Usage：补充 4501152 示例命令

## [2026-04-19] decision | UMI/Zeus 构建流程
- ADR：[[wiki/decisions/ADR-002-umi-zeus-build]]
- 操作文档：[[docs/build-network-umi-zeus]]

## [2026-05-08] change | 启用 OpenMP 并行 + genesis_hyde_100k 首次完整模拟
- **OpenMP 启用**: `POLITEIA_USE_OPENMP=ON` + Release 模式重新编译
  - 48 线程 Xeon Gold 6248R，完全利用多核
- **genesis_hyde_baseline 尝试**: 4,501,152 agents 单线程跑了 2.5h 未完成
  - 原因：OpenMP 默认 OFF，单线程处理 450 万粒子每步需数分钟
  - 结论：baseline 需 MPI 多节点或极长运行时间
- **genesis_hyde_100k 成功完成**: 100,000 agents，10,000 步 ≈ 100 年
  - 运行时间：约 2 小时（48 线程 OpenMP）
  - 涌现结果：
    - 人口：100K → 46,662（初始淘汰 53%）→ 47,569（稳定回升）
    - Gini = 0.98（极端不平等涌现）
    - 层级深度 H = 5 → 6（政治层级自发加深）
    - 政体数 1,841 → 1,410（政治整合趋势）
    - 文化序参量 Q = 0.25 → 0.30（文化边界形成中）
    - 政治类型：bands 609→428, tribes 918→674, chiefdoms 314→311
    - 尚无 states/empires — 符合新石器时代预期
  - 输出：10 个 snapshot + energy/order_params/polity CSV

## [2026-05-09] bugfix | Social potential 能量数值爆炸

- **问题**: energy.csv 中 social potential 高达 ~1e30-1e36
  - 原因：LJ 势虽有 F_MAX=100 的力封顶，但势能 V(r) ∝ (σ/r)^12 未做保护
  - 当粒子因初始化重叠导致 r → 0 时，sr12 = (σ/r)^12 → ∞
- **修复**: `src/force/social_force.cpp` 添加 soft-core 最小距离
  - 第一版 `r_min_sq = 0.01 * sigma2`（r_min = 0.1σ）→ 能量仍达 ~1e17
  - 第二版 `r_min_sq = 0.25 * sigma2`（r_min = 0.5σ）→ 每对势能上界 ~48ε
  - OpenMP 和非 OpenMP 路径均已修复
  - 所有 LJ 计算中用 `r2_eff = max(r2, r_min_sq)` 代替 r2
  - 力和能量都通过同一距离下界约束，消除 singularity
- **新增测试**: `OverlappingParticlesFiniteEnergy` + `ExactOverlapSkipped`
  - 验证近距离重叠粒子的能量有限（< 1e15）
  - 验证精确重叠（r=0）被 CellList r2>0 过滤器正确跳过
  - CTest 日志确认 6/6 SocialForce 测试通过（含新增 2 个）

**文件**：`src/force/social_force.cpp`

## [2026-05-09] change | 主循环添加轻量级进度报告

- **问题**: 大规模模拟数小时无任何控制台输出（Step 信息只在 network_window 间隔打印）
- **修复**: `src/main.cpp` 在 compact_interval 间隔打印进度行
  - 格式：`[step/total] pct% N=count wall=Xs rate=Y step/s ETA=Zs`
  - 使用 `std::flush` 确保即时输出
  - 不影响正式 output_interval 的完整输出
- **建议**：管道/重定向时使用 `stdbuf -oL` 强制行缓冲

**文件**：`src/main.cpp`

## [2026-05-09] change | 新增结果分析脚本

- `scripts/analyze_run.py`：一体化结果分析脚本
  - 5 张可视化图：order_params, energy, snapshot distributions, polity evolution, polity map
  - 支持命令行指定输出目录
- `scripts/validate_and_run.sh`：一键构建+测试+模拟+诊断脚本
  - 完全干净重建（rm -rf build + cmake + make）
  - 社会力测试 + 关键测试套件
  - 小规模模拟 + 自动能量诊断

## [2026-05-10] critical-bugfix | 人口爆炸：Carrying Capacity 归一化缺失

- **问题**: 100K 粒子 × 3000 步后人口爆炸到 454K（4.5 倍增长）
  - density_suppression ≈ 0.9998（完全无效）
  - 根因：`K = carrying_capacity_base × max(0, -V)` 中 V 未归一化
  - 地形势能 V ∈ [-138, 0]，导致 K = 50 × 138 = 6923
  - 需要 54 万粒子在 r=5 范围内才能触发抑制 — 物理上不可能
  - 每步预期出生 ~11,550 vs 死亡 ~1 → 不受控的指数增长
- **修复**: `src/population/carrying_capacity.cpp`
  - 在 `compute_carrying_capacity` 中先计算 `max_neg_V = max(-V[i])`
  - 归一化: `quality = max(0, -V[i]) / max_neg_V`，使 quality ∈ [0, 1]
  - K 现在 ∈ [0, carrying_capacity_base]，密度抑制正确生效
- **测试**: 更新 `CarryingCapacityProportionalToTerrain` 测试预期值
  - 6/6 CarryingCapacity 测试通过

**文件**：`src/population/carrying_capacity.cpp`, `tests/test_carrying_capacity.cpp`

## [2026-05-10] bugfix | 层级系统完全失效 (leaders=1)

- **问题**: 所有粒子 superior=-1, loyalty=0 → 政治层级从未形成
  - `form_attachments` 和 `attempt_conquest` 被绑定到 `network_window`
  - `network_window = output_interval × network_window_factor = 1000 × 5 = 5000 步`
  - 在 5000 步之前，层级系统无法启动
- **修复**: `src/main.cpp`
  - 将 `form_attachments` 和 `attempt_conquest` 的触发条件从 `step % network_window`
    改为 `step % cfg.compact_interval`
  - 层级动态现在每 compact_interval 步执行（默认 100-250 步）

**文件**：`src/main.cpp`

## [2026-05-10] bugfix | OpenMP mortality RNG 数据竞争

- **问题**: `mortality.cpp` 中 `rng()` 在 `#pragma omp parallel` 内被多线程并发调用
  - 与 integrator 同样的模式：共享 RNG 无同步
- **修复**: `src/population/mortality.cpp`
  - 在 parallel 区域外预生成 per-thread seeds
  - 每个线程用独立 seed 初始化本地 RNG
  - 模式与 `langevin_integrator.cpp` 的修复完全一致

**文件**：`src/population/mortality.cpp`

## [2026-05-10] feature | 税收行政损耗机制 (tax_efficiency)

- **问题**: 税收 100% 高效传递，14 层层级导致 Gini=0.97 极端不平等
  - 现实中的行政摩擦、地方截留在模型中完全缺失
  - 忠诚度单调增长（protection_gain >> tax_drain × tax_rate），几乎不叛乱
- **修复**:
  - `LoyaltyParams` 新增 `tax_efficiency=0.5`（上级仅收到 50% 税款）
  - 降低 `tax_rate`: 0.1 → 0.05
  - 降低 `protection_gain`: 0.1 → 0.03
  - 提高 `tax_drain`: 0.05 → 0.1
  - 新增 config key `tax_efficiency`
- **效果**: 校准测试中 Gini 从 0.97 降至 0.92（500 步时），层级 H=9（无帝国涌现）

**文件**：`src/interaction/loyalty.hpp`, `src/interaction/loyalty.cpp`, `src/core/config.hpp`, `src/core/config.cpp`, `src/main.cpp`

## [2026-05-10] feature | 模拟健康指标实时预警

- **问题**: 关键指标异常（Gini 暴涨、KE 失控、势能爆炸）缺乏提示
  - 需要人工分析 CSV 才能发现问题
- **修复**: `src/main.cpp` 在 output_interval 步添加自动检查：
  - Gini > 0.85 → 极端不平等警告
  - mean_loyalty > 0.95 且 attached > 50% → 忠诚度饱和警告
  - KE/NkT > 3.0 或 < 0.2 → 热力学失衡警告
  - |V_social| > 1e12 → 势能发散警告

**文件**：`src/main.cpp`

## [2026-05-10] feature | 参数扫描脚本

- 新增 `scripts/param_sweep.py`：自动化参数扫描
  - 扫描变量：`tax_rate`, `tax_efficiency`, `loyalty_protection_gain`
  - 自动生成 config、运行模拟、收集 Gini/H/polity 等指标
  - 输出 `sweep_results/summary.csv` 供分析

**文件**：`scripts/param_sweep.py`

## [2026-05-10] bugfix | 人口老龄化死亡螺旋

- **问题**: v3 模拟中人口从 100K 崩溃到 62K (step 4000)
  - 平均年龄从 37.3 飙升到 60.8
  - 年轻人 (age<5) 从 3.0% 暴跌到 0.2%
  - 不是贫穷致死（无人财富 < threshold）— 是生育不足
- **根因**: `max_fertility=5e-5` 仅产出 ~2.9 孩子/女性
  - 考虑 cooldown(2.75年)、文化距离、密度抑制后实际 < 2
  - 低于置换率 → 人口在第一代女性绝经后加速衰减
- **修复**: `max_fertility` 默认值调整为 `2e-4`
  - 理论估算: ~5.2 孩子/女性（前工业社会合理水平）
  - v5 校准验证: 1000 步人口 10K→11.8K (+18%)，持续增长

**文件**：`src/core/config.hpp`, `src/population/reproduction.hpp`

## [2026-05-10] feature | 财富衰减机制 (wealth_decay_rate)

- **问题**: 参数扫描（36 组）证明 Gini ~0.89 不受税收参数影响
  - 不平等的主要来源是对称交换规则 `Δw = η(A_i-A_j)/(A_i+A_j)·min(w_i,w_j)`
  - 这是 research-proposal 预言的核心涌现——对称规则产生不平等
- **修复**: 新增 `wealth_decay_rate`（资产折旧）
  - `dw -= wealth_decay_rate × w × dt`（财富按比例衰减）
  - 富人损失更多（绝对值），创建自然天花板
  - 同时降低 `exchange_rate`: 0.01 → 0.003
- **效果** (v7 校准):
  - Gini@200步: 0.80 → **0.53**（历史合理范围！）
  - Gini@1000步: 0.95 → **0.88**（有天花板效应）
  - 人口 +18.5%，H=13，194 polities（所有指标健康）

**文件**：`src/core/config.hpp`, `src/core/config.cpp`, `src/interaction/resource_exchange.hpp`, `src/interaction/resource_exchange.cpp`, `src/main.cpp`

## [2026-05-10] analysis | 参数扫描证明不平等来源

- **方法**: 36 组参数组合 (tax_rate × tax_efficiency × protection_gain)
- **结论**: 所有组合 Gini ∈ [0.886, 0.893] — 税收参数几乎无影响
- **意义**: 验证了 research-proposal 的核心假设——不平等从对称交换规则涌现

**文件**：`scripts/param_sweep.py`, `sweep_results/summary.csv`

## [2026-05-10] analysis | 社会势能 V_social=+2.8e9 诊断

- **调查**: 独立 Python 计算验证 → 估算值 3.12e9 与报告值 2.80e9 吻合 (0.9x)
- **根因**: 2.5% 粒子对处于排斥区间 (r < σ)，每对贡献 ~48000 势能
  - 地形力将粒子集中到河谷 → LJ 排斥平衡 → 动态平衡
  - 物理解释：**人口拥挤压力** — 宜居区域人满为患
- **结论**: 非 bug，是正确的物理行为。已记录到 `wiki/reflection-2026-05-10.md`

## [2026-05-10] milestone | v3 模拟完成 — 人口崩溃的教训

- **最终结果**: 100K → 35,643 (-64.4%) in 5000 步
  - 人口: 阶段 1 稳定 → 阶段 2 缓慢衰减 → 阶段 3 加速崩溃
  - Gini: 0.97 → 0.98 → 持续上升
  - 政治: 6 帝国 → 2 帝国 → 0 帝国 → 2265 个碎片化小政体
  - 忠诚度: 0.987 → 0.895 → 社会凝聚力瓦解
- **教训**: `max_fertility=5e-5` 导致 TFR ≈ 2.9 → 低于考虑损耗后的置换率
- **分析**: 6 个 PNG 可视化图表已生成
  - `order_params.png`, `energy.png`, `snapshot_00005000.png`
  - `distributions_00005000.png`, `polity_evolution.png`, `polity_map_00005000.png`

## [2026-05-10] launch | v8 模拟启动（校准后参数）

- 100,000 粒子 × 5,000 步
- 关键参数变更（vs v3）:
  - `max_fertility`: 5e-5 → 2e-4 (人口可持续)
  - `exchange_rate`: 0.01 → 0.003 (减缓财富集中)
  - `wealth_decay_rate`: 0 → 0.1 (资产折旧)
  - `tax_rate`: 0.1 → 0.05 + `tax_efficiency`: 0.5 (行政损耗)
- 预期: Gini ~0.88, 人口稳定增长, 多级政治层级

## [2026-05-10] performance | 并行化 exchange/culture/tech 串行瓶颈

- **问题**: 100K 粒子模拟仅用 1.3 核（134% CPU），ETA 20h
- **根因**: `exchange_resources`, `evolve_culture`, `evolve_technology` 使用串行 `for_each_pair`
- **修复**: 改用 OpenMP `parallel for` + `for_neighbors_of`（per-particle 循环）
  - `culture_dynamics.cpp`: 中间缓冲区 `dcv[i]` 收集变化
  - `tech_spread.cpp`: 中间缓冲区 `d_eps[i]` 收集变化
  - `resource_exchange.cpp`: 中间缓冲区 `dw_buf[i]` 收集变化
- **效果**: CPU 134% → 249%，Step 100 时间 1500s → 1029s (-31%)
- 全部 159 个单元测试通过

## [2026-05-10] bugfix | carrying_capacity_base 密度缩放不匹配

- **问题**: v8 模拟 100K 粒子在 200 步内从 100K 暴跌到 85.9K (-14%)
- **根因**: `carrying_capacity_base=5.0` 远低于实际密度 10/unit²
  - density_suppression = max(0, 1 - 10/5) = 0 → 繁殖完全被抑制
  - 加上 wealth_decay_rate=0.1 → 无生产 + 持续消耗 → 饥饿死亡螺旋
- **修复**: `carrying_capacity_base`: 5 → 50, `wealth_decay_rate`: 0.1 → 0.02
- **教训**: 用 10K 粒子校准的参数不能直接用于 100K — 密度假设不同

**文件变更**:
- `src/interaction/culture_dynamics.cpp` — OpenMP 并行化
- `src/interaction/tech_spread.cpp` — OpenMP 并行化
- `src/interaction/resource_exchange.cpp` — OpenMP 并行化
- `/tmp/genesis_100k_v8.cfg` — 更新 carrying_capacity_base, wealth_decay_rate
- `scripts/run_v8.sh` — 新增重启脚本

## [2026-05-10] milestone | v8 模拟完成（并行化版本）

- 100K 粒子 × 5,000 步，wall time = 9,000s（2.5h）
- 使用旧配置 (K=5, decay=0.1) 但新并行化 binary
- **最终结果**:
  - 人口: 100K → 22,413 (-78%)，人口仍然崩溃
  - Gini: 0.976 → **0.943** (改善 vs v3 的 0.982)
  - H: 13 → 7
  - 帝国最大规模: **26,222** (v3 最大仅 9,818)
  - 文化 Q: 0.35 → **0.48** (v3 仅 0.14)
- **改善**: Gini 降低 4%，文化分化增强 3.4x，帝国规模提升 2.7x

## [2026-05-10] milestone | v8b 模拟启动（修正承载力）

- 100K 粒子 × 5,000 步
- **修正参数**: carrying_capacity_base=50, wealth_decay_rate=0.02
- 初步结果 (Step 600): 
  - **N=135,491** (+35.5%) — 人口增长成功!
  - H=17, 最大政体 **105,914**（78% 人口！）— 大帝国涌现!
  - 但 KE/NkT=145 — 高密度下热能严重超标
  - exchange 占 19.9% 步骤时间（高密度邻居搜索开销）
- **待解决**: KE/NkT 热失衡需要增强温控或限制人口密度

## [2026-05-10] bugfix | KE/NkT 热爆炸修复（粒子总力封顶 + Berendsen 温控）

- **问题**: v8b 高密度下 KE/NkT=145，动能超标 290 倍
- **根因**: F_MAX=100 仅限制单对力，42 邻居的累积力达 ~4200 → v_terminal=4200
- **修复**:
  1. `social_force.cpp`: 添加 F_TOTAL_MAX=200 粒子总力封顶
  2. `main.cpp`: 每 10 步 Berendsen 速度重标（KE/NkT > 2 时激活）
- **效果**: KE/NkT 从 **145 降到 3.55** ✅
- 全部 159 个单元测试通过

## [2026-05-10] launch | v8c 模拟（完全校准版）

- 100K 粒子 × 5,000 步
- 关键参数: K=20, decay=0.02, F_TOTAL_MAX=200, Berendsen 温控
- 初步结果 (Step 1200):
  - 人口: 100K → 86.9K（-13% 初始调整）→ **90.7K（回升！）**
  - KE/NkT=3.55（vs v8b 的 145）✅
  - H=12, 27 邦国, 1 帝国, 239 酋邦
  - 人口接近动态平衡，政治结构丰富
- v8c 最终状态 (Step 2500，手动终止):
  - 人口稳定在 90,353 ✅
  - Gini=0.991 ❌ 极端不平等未改善
  - I/O 占比 90% — 性能严重瓶颈

## [2026-05-10] fix | I/O 瓶颈根因：serial network recording

- **根因**: `exchange_resources` 的 OpenMP 路径中，每步调用 serial `for_each_pair` 记录网络流
  - 90K 粒子 ~35M 对评估/步 × `unordered_map` 插入 → ~3.5 秒/步
  - 500 步积累 → 每个 output_interval ~30 分钟纯网络记录
- **修复**: `main.cpp` 中仅在 `compact_interval` 时传入网络指针 (99% 步数跳过)
- **效果**: 预期速率从 0.2 → 0.4+ step/s (2x 提升)

## [2026-05-10] fix | Gini=0.99 根因：马太效应正反馈

- **根因**: 交换公式 `A_i = w_i × ε_i` 中财富是能力的乘数
  - 更富 → A_i 更大 → 从穷人提取更多 → 更富 (正反馈环)
  - 10 个富邻居每步从穷人提取 ~6% 财富 vs 生产 ~0.5%
- **修复**: 引入能力饱和函数 `A_i = ε_i × w_i / (w_i + w_ref)` (Michaelis-Menten 型)
  - `w_ref=5.0` (初始财富): w=5→A=0.5ε, w=25→A=0.83ε, w=100→A=0.95ε
  - 能力差距被约束在 ε 差异范围内，打破正反馈
- **额外优化**: `detect_polities` 中 `compute_depth` 使用记忆化缓存
- 全部 160 个测试通过

## [2026-05-10] launch | v9 模拟（能力饱和 + I/O 优化）

- 100K 粒子 × 5,000 步
- 新增参数: `ability_saturation_w=5.0`, `output_interval=1000`
- Step 1000 结果:
  - **Gini = 0.759** ✅ (v8c=0.986 → -23%, 历史合理范围!)
  - 人口 N=90,710 ✅ 稳定
  - H=6 (v8c=12) — 层级变浅，无帝国/国家，1871 酋邦
  - 速率 0.4-0.5 step/s ✅ (v8c=0.2, 性能翻倍)
  - I/O 占比 84% (v8c=92%, 改善但仍高)
- **物理发现**: 财富平等化→政治碎片化符合史实（前农业社会以小规模政体为主）
- **v9 完成** (9000 秒, 2.8x 加速 vs v8c):
  - Gini 稳定在 0.76-0.80 ✅ (历史合理范围，全程无 Gini 警告!)
  - 人口: step 1000-3000 稳定 ~91K → step 3000+ 崩溃至 71.5K ❌
  - **崩溃根因**: 初始队列老化 (age 15-40 → 45-70+ at step 3000)
  - 政治结构全程碎片化: 最大政体 <520, 零帝国/国家 ❌

## [2026-05-10] analysis | 深度反思 v2

- 核心矛盾: Gini 平等 vs 政治复杂度的**不可调和张力**
- I/O 优化引入耦合故障: 网络记录窗口 100→2 步，attachment flow 暴降 99%
- **修复**: 窗口 2→20 步, attachment_threshold 0.3→0.05 (已提交代码)
- 提出 "Gini-Hierarchy 相图" 假设: 存在临界 Gini ~0.85 触发层级爆发
- 人口崩溃是所有版本的共性问题, 暴露时间不同
- 详见 `wiki/reflection-2026-05-10-v2.md`

## [2026-05-10] fix | 人口动力学修复 + 人口统计诊断系统

- **人口崩溃修复**:
  - `nursing_time`: 2.0→1.5 (有效 cooldown 从 275 步降至 225 步, +22% 生育机会)
  - `max_fertility`: 2e-4→5e-4 (per-pair-per-step, 有效 TFR 提升 2.5x)
  - 预期效果: TFR 从 ~3.9 提升至 ~12+ (远超替代水平 2.1)
- **人口统计诊断系统** (`demographics.csv`):
  - 新增输出: step, time, N, births, deaths, mean_age, median_age
  - 年龄结构分析: frac_fertile (15-45岁), frac_children (<15), frac_elderly (>60)
  - 增长率追踪: growth_rate = (births - deaths) / N
  - 健康预警: fertile_fraction < 20% 时输出 `[WARN] population aging crisis`
- **Gini-H 相图扫描脚本** (`scripts/sweep_gini_h.py`):
  - 自动扫描 ability_saturation_w × attachment_threshold 参数空间
  - 8×3 = 24 组合, 收集 Gini/H/polity/demographic 指标
  - 自动生成相图可视化 (matplotlib)
- v9b 配置已更新: `max_fertility=5e-4`, `nursing_time=1.5`
- 所有测试代码保持兼容（默认值更改不影响显式参数化测试）

## [2026-05-11] perf | 网络记录并行化优化

- **根因**: `exchange_resources` 中网络记录使用独立的 serial `for_each_pair`，
  每步 ~3.5 秒 (100K 粒子, ~35M 对)，20 步窗口 = 每 compact_interval 70 秒串行
- **修复**: 将流量记录集成到并行 `for_neighbors_of` 循环:
  - per-thread `FlowRecord` 缓冲区（无锁竞争）
  - `i < j` 条件避免重复记录
  - 合并阶段仅遍历实际发生的显著流量
- **预期效果**: 网络记录步 ~3.5s → ~0.1s，v9b 整体速率预计 0.2→0.5+ step/s
- 此优化适用于下一次构建（v9b 当前运行不受影响）

## [2026-05-11] milestone | v9b Step 1000 突破性结果

- N=95,627 (增长中! v9=91K 开始下降)
- Gini=0.80 (历史合理范围, 与 v9 一致)
- H=20 (v9=6, 首次达到 20 层深度!)
- 2 帝国 + 6 国家 + 241 酋邦 (v9 全程零帝国/国家)
- 最大政体 30,766 (占人口 32%, v9<520)
- demographics.csv 首次输出: births=16.9K, deaths=21.3K, frac_children=17.7%
- 关键发现: Gini=0.80 + H=20 + 帝国涌现, 证伪了 Gini>0.85 才有帝国的假设
- 真正关键: attachment_threshold 与实际流量的匹配, 而非 Gini 本身
- **v9b 完成** (12,800s wall time):
  - 最终 N=92,839 (峰值 103,812 at step 3500)
  - Gini 全程稳定 0.77→0.80 (历史合理范围)
  - **H: 20→22→23→26→28** (层级持续深化!)
  - **2 帝国 + 14 国家 + 156 酋邦** at step 5000
  - 最大政体从 30K→38K 峰值→10.9K (可能是帝国分裂)
  - Q 文化序参量 0.41→0.56 (文化边界持续锐化)
  - mean_loyalty 0.60→0.89→0.73 (忠诚度先升后降, 有叛乱动态)
  - 人口先降后升超过初始值 (峰值 103.8K > 100K!), 然后再次下降
  - frac_children 从 17.7%→27.0% (第二代壮大中, v9 未见此现象)
  - 综合评价: **所有版本中最成功的模拟** — 同时实现合理 Gini + 深层级 + 帝国涌现

## [2026-05-11] reflection | 深度反思 v3 — 架构瓶颈与方向修正

- **误判瓶颈**: v10 并行 FlowRecord 优化无效 (速度 0.3≈v9b, 内存↑2.6x)
  - 真正瓶颈不是 serial for_each_pair, 而是分析计算 (detect_polities, hierarchy_metrics)
- **compute_effective_power 重复调用**: main.cpp 和 compute_hierarchy_metrics 各调一次
- **Gini-Hierarchy 假设被证伪**: v9b (Gini=0.80, H=28) 证明层级深度不依赖极端不平等
  - 核心决定因素: attachment_threshold 匹配度 + 网络记录窗口长度
- 详见 `wiki/reflection-2026-05-11.md`

## [2026-05-11] change | 创建经验教训文档 lessons-learned.md

- 从三份反思 (reflection-2026-05-10, v2, 2026-05-11) 和 troubleshooting.md 中提炼高层原则
- 十大主题：性能优化、耦合陷阱、pair-wise 参数、尺度不变性、测试策略、物理量数值、并行编程、开发方法论、被证伪假设、开发 checklist
- 每条教训标注来源，便于追溯
- 目标：后续开发避坑指南

## [2026-05-11] perf | v11 性能优化四项

### 1. detect_polities: Union-Find 路径压缩
- **旧**: `find_root()` 对每个粒子做 O(depth=28) 链式查找 + gid_to_local hash lookup
- **新**: Union-Find with path halving, 均摊 O(α(N)) ≈ O(1) 每次查找
- **预期**: detect_polities 从 ~120s 降至 <5s
- **文件**: `src/analysis/polity.cpp`

### 2. 消除冗余 power_gini 计算
- **旧**: compute_hierarchy_metrics 内部调用 compute_effective_power (拓扑排序 O(N)) 计算 power_gini, 但结果从未被 main.cpp 使用
- **新**: 移除内部调用, 仅保留 main.cpp 的 loyalty 版本
- **文件**: `src/analysis/network_analysis.cpp`

### 3. 分级输出架构
- **旧**: 健康诊断只在 network_window 步执行, 非分析步无输出
- **新**: 轻量健康检查 (Gini, KE, V_social, frac_fertile) 每 output_interval 执行
  - 重分析 (polity, hierarchy, power) 仅在 network_window 步
  - 非分析步也输出 "Step N Gini=x (light output)" 摘要
- **文件**: `src/main.cpp`

### 4. 年龄金字塔初始化 (age_pyramid=true)
- **问题**: 原始 IC 年龄分布 15-40 (窄带) → 代际同步老化 → 周期性人口波动
- **方案**: 新增 `age_pyramid` 配置项, 使用指数分布 S(a)=exp(-0.03a) 采样 0-70 岁
  - λ=0.03 对应前工业社会粗死亡率 ~30‰
  - 逆 CDF 采样: a = -ln(1 - U×(1-exp(-λ×70))) / λ
  - 预期年龄分布: ~34% < 15岁, ~53% 15-45岁, ~13% > 45岁
- **文件**: `src/io/ic_loader.cpp`, `src/main.cpp`, `src/core/config.hpp`, `src/core/config.cpp`

## [2026-05-11] launch | v11 配置

- 100K 粒子 × 10,000 步 (同 v10)
- 关键变更 vs v9b/v10:
  - `age_pyramid = true` (年龄金字塔, 消除代际断层)
  - `network_window_factor = 5` (重分析频率降低 5x)
  - Union-Find + 去冗余 + 分级输出 (性能优化)
- 脚本: `scripts/run_v11.sh`
- v11 PID=3783105, 与 v10 并行运行

## [2026-05-11] milestone | v10 Step 6000 — 文明周期涌现

- **人口触底回升**: growth_rate 从 -5.8% (step 5000) 反转为 **+0.2%** (step 6000)
  - frac_elderly: 33.6% → **6.1%** (初始队列基本死亡殆尽!)
  - frac_children: 26.9% → **30.0%** (第三代开始产生)
  - frac_fertile: 39.0% → **44.3%** (第二代成为主力)
- **帝国崩溃 & 政治碎片化**:
  - H: 25 → 14, 帝国: 1 → **0**, 最大政体: 33,829 → **2,971**
  - HHI: 0.12 → **0.008** (高度碎片化)
  - 国家: 11 → **19** (但无大帝国, 类似中世纪小国林立)
- **文化加速分化**: Q: 0.53 → **0.66** (帝国崩溃→地方文化复兴, 历史吻合)
- **Gini 略降**: 0.809 → **0.793** (财富重新分配)
- **物理解读**: 建国者一代大规模死亡→社会网络断裂→帝国失去人力→瓦解为小国
  - 这是模型自发涌现的**文明兴衰周期**, 非手动编程的结果!
  - 类比: 青铜时代晚期崩溃 (~1200 BC), 西罗马帝国衰亡 (476 AD)
- **预期**: step 7000-10000 第二代成熟, 可能出现新一轮帝国涌现
- **Step 6900 后续**: N=98,315 — 人口强劲反弹! 从触底 93K 已回升 +5.3%

## [2026-05-11] milestone | v11 Step 1000 — 年龄金字塔+性能验证

- **年龄金字塔效果**: mean_age=28.7 (v10=33.8), frac_children=27.8% (v10=17.8%)
  - 初期衰退更大 (100K→90K) 因为老年人直接进入高死亡率
  - 但 frac_children 大幅增加 → 预期不会出现代际断层
- **分级输出验证**: "light output, full analysis at step 5000" 正确打印
  - **I/O 占比: 91.44%** (v10=96.09%, 降低 4.65%)
  - order_params.csv 为空 (network_window_factor=5, 首次分析在 step 5000)
- **人口轨迹对比**:
  | Step | v10 N | v11 N | 差异 |
  |------|-------|-------|------|
  | 0 | 100K | 100K | 0% |
  | 100 | 100K | 100K | 0% |
  | 200 | 90.9K | 89.1K | -2.0% |
  | 400 | 88.4K | 84.8K | -4.1% |
  | 700 | 91.7K | 86.4K | -5.8% |
  | 1000 | 95.6K | 90.1K | -5.8% |
- v11 初期人口更低, 但增长趋势稳定 (84.8K→90.1K, +6.3%)
- v11 关键优势: frac_children=27.8% 远高于 v10=17.8%, 不会出现代际真空

## [2026-05-11] milestone | v10 Step 7000 — 文明重建! 完整兴衰周期涌现

- **核心发现**: 模型自发涌现了完整的**文明兴衰-重建周期**
  ```
  Step 0-3000:    建国期 → 人口增长 (100K→104K), 帝国涌现 (H=25, 2 empires)
  Step 3000-5000: 衰亡期 → 建国者老化死亡, 帝国崩溃 (H=14→20, 1→0 empires)
  Step 5000-6000: 黑暗期 → 碎片化, 小国林立 (largest=2971, HHI=0.008)
  Step 6000-7000: 重建期 → 第二代接班, 新帝国涌现 (H=21, 1 empire!)
  ```
- **人口**: N=**100,056** — 重新超过初始 100K! (触底 93K 后 +7%)
- **层级**: H=21 (从 14 恢复), 1 帝国 + 21 国家
- **人口统计**: growth=+6.1%, frac_fertile=50.2%, frac_elderly=12.3%
- **文化**: Q=0.70 — 文化分化持续加深 (帝国崩溃→地方文化复兴→保留下来)
- **Gini**: 0.788 — 持续稳定在历史合理范围
- **物理解读**: 这是 research-proposal 预言的核心涌现之一 —
  对称交换规则 + Langevin 动力学 + 人口更替 自发产生了类似人类历史的文明周期

## [2026-05-11] milestone | v10 Step 8000 — 人口历史新高

- **N = 106,605** — 超过第一轮高峰 104.4K, 创历史新高!
- growth_rate = +6.1%, births=13.8K vs deaths=7.2K (出生是死亡的近 2x)
- 国家 24 个 (从 step 6000 的 19 个持续增长), 1 帝国
- Q=0.72 (文化分化继续, 政治碎片化但每个碎片文化独立)
- step 8200 出现微降 (106.6K→106.3K), 可能是第二代老化的早期信号

## [2026-05-11] milestone | v11 Step 2700 — 年龄金字塔效果验证

- **核心对比** (step 2000):
  | 指标 | v10 | v11 | 差异 |
  |------|-----|-----|------|
  | N | 97,952 | **98,090** | v11 追平 |
  | growth | +2.4% | **+8.2%** | 3.4x 更快 |
  | frac_fertile | 36.7% | **54.1%** | +47% |
  | mean_age | 40.4 | **31.3** | 年轻 9 岁 |
  | frac_children | 14.6% | **22.2%** | +52% |
- v11 step 2700: N=**102,971**, 持续健康增长
- **关键验证**: 年龄金字塔消除了 v10 的人口"先升后降"模式
  - v10 轨迹: 100K → 104K → 93K → 106K (剧烈振荡)
  - v11 轨迹: 100K → 85K → 103K (单次调整后稳定增长)
- I/O 占比: 92.11% (v10=96%), 分级输出优化生效

## [2026-05-11] milestone | v10 完成! 10,000 步 — 文明周期与人口持续增长

- **总运行时间**: 30,000 秒 (8.3 小时), 0.4 step/s
- **最终状态**: N=**113,130** (+13.1%), Gini=0.799, Q=0.745, H=11
- **完整文明演化周期** (100 时间单位 ≈ 3 代人):
  ```
  Step 0-3000:     建国期 → 3 empires, H=23, N→104K  (第一代)
  Step 3000-5000:  衰亡期 → 0 empires, H=14, N→94K   (第一代老化)
  Step 5000-6000:  黑暗期 → HHI=0.008, 碎片化         (代际断层)
  Step 6000-8000:  复兴期 → 1 empire, H=21, N→107K    (第二代接班)
  Step 8000-9000:  二次衰退 → 0 empires, H=11         (周期变短!)
  Step 9000-10000: 人口持续增长 N→113K                 (第三代即将)
  ```
- **人口统计全程记录**:
  | Step | N | growth | frac_fertile | frac_elderly | mean_age |
  |------|---|--------|-------------|-------------|----------|
  | 1000 | 95.6K | -4.6% | 55.4% | 0% | 33.8 |
  | 3000 | 103.6K | +5.5% | 20.1% | 27.0% | 42.4 |
  | 6000 | 93.9K | +0.2% | 44.3% | 6.1% | 30.1 |
  | 8000 | 106.6K | +6.1% | 48.5% | 12.5% | 34.8 |
  | 10000 | 113.1K | +3.3% | 40.8% | 17.0% | 36.8 |
- **KE/NkT=3.03 轻微警告**: 人口增加至 113K 导致密度略高
- **v11 同步进展**: step 4700, N=111,695, I/O=89.5% (性能改善明显)

## [2026-05-11] milestone | v11 Step 5000 — 第一次完整分析, 年龄金字塔优势确认

- **v11 Step 5000**: N=**112,438**, Gini=0.814, Q=0.545, **H=19, 1 帝国, 17 国家**
- **最大政体 = 40,711** (占 36% 人口!) — v10 同期仅 10K
- **核心对比** (step 5000):
  | 指标 | v10 | v11 | 解读 |
  |------|-----|-----|------|
  | N | 93.8K (-5.8%) | **112.4K (+2.3%)** | v11 人口多 20% |
  | largest | 10,081 | **40,711** | v11 帝国 4x 大 |
  | mean_loyalty | 0.744 | **0.870** | 社会网络更稳定 |
  | frac_elderly | 24.3% | **17.5%** | 无老龄化危机 |
- **物理解读**: 年龄金字塔 → 连续的年轻劳动力 → 社会网络不断裂 → 帝国存活更久
- **分级输出效果**: 非分析步 I/O=89-92%, 分析步 95.9%
- **order_params.csv 首次有数据** — 分级输出正确地仅在 network_window 步写入

## [2026-05-11] milestone | v11 完成! 10,000 步 — 年龄金字塔 A/B 测试完成

- **总运行时间**: 30,000 秒 (8.3 小时), 与 v10 相同
- **最终状态**: N=**118,730** (+18.7%), Gini=0.798, Q=0.858, H=9
- **核心 A/B 测试结果 (v10 vs v11, 唯一差异: age_pyramid)**:
  | 指标 | v10 (uniform age) | v11 (age pyramid) | 效果 |
  |------|-------------------|-------------------|------|
  | 最终人口 | 113,130 | **118,730** | +5% |
  | 人口振荡幅度 | ±10% | **±1.6%** | 降低 6x |
  | 最大人口下降 | -10.4% (step 5000) | **-1.6%** (step 8000) | 平滑 |
  | 文化分化 Q | 0.745 | **0.858** | 更高 |
  | 人口年龄 | 36.8 | **34.5** | 更年轻 |
  | step 5000 largest | 10,081 | **40,711** | 4x 更大帝国 |
  | I/O (非分析步) | 96% | **89-92%** | 改善 4-7% |
- **v11 人口轨迹**: 100K → 85K → 113K → 111K → **119K** (单次调整→缓慢均衡振荡)
- **v10 人口轨迹**: 100K → 104K → 94K → 107K → 109K → **113K** (多次剧烈振荡)
- **科学结论**: 年龄金字塔初始化不仅消除人口振荡, 还有两个意外效果:
  1. **帝国更大更稳定** (step 5000 largest=40K vs 10K) — 连续人口补充维持社会网络
  2. **文化分化更深** (Q=0.86 vs 0.75) — 更平滑的社会演化允许文化自然分化
- **分级输出验证**: 仅在 step 5000 和 10000 输出完整分析, order_params.csv 只有 2 行
- **待解决**: 两个版本最终都碎片化 (H≤11, 0 帝国) — 见下方根因分析

## [2026-05-11] analysis | 长期碎片化根因 and v12 方向

### 碎片化根因 (v10 and v11 共同)

1. **文化发散导致忠诚度侵蚀** (主因):
   Q 从 0.41 增长到 0.86, loyalty.cpp 中 culture_penalty * c_dist 每步消耗忠诚
   跨文化圈的层级关系不可维持, 帝国瓦解是长期必然
2. **继承忠诚衰减**: 每次领导死亡 loyalty *= 0.7, 多代累积衰减
3. **征服概率过低**: base_prob=0.01, 碎片化后重建缓慢
4. **缺少文化同化**: 无帝国官方文化机制, 文化纯粹自由漂移

### v12 可能方向 (优先级排序)

1. **文化同化机制** (高优先):
   上下级文化趋同 c_subordinate -> c_superior, 速率 assimilation_rate * L_ij
   效果: 帝国内部文化趋同, 减缓文化发散导致的忠诚度消耗
2. **异步分析减少 I/O 瓶颈** (高优先):
   将 detect_polities 移到后台线程, 快照输出使用异步 I/O
3. **更长模拟** (中等): 20K-50K 步观察更多文明周期
4. **自适应分析频率** (低优先): 事件驱动的分析密度

## [2026-05-12] feature | v12 — 文化同化 + 征服增强

### 代码变更

1. **文化同化机制** (`culture_dynamics.hpp/cpp`):
   - 新增 `apply_hierarchy_assimilation(particles, rate, dt)`
   - 公式: `c⃗_i += rate × L_ij × (c⃗_superior − c⃗_i) × dt`
   - 效果: 下级文化向上级趋同, 速率∝忠诚度
   - 物理类比: 帝国文化同化 (如罗马化, 汉化)

2. **配置参数** (`config.hpp/cpp`):
   - 新增 `hierarchy_assimilation_rate = 0.05` (默认值)
   - 修改 `conquest_base_prob` 默认值 0.01 → **0.02** (征服概率翻倍)

3. **主循环集成** (`main.cpp`):
   - 在 `apply_taxation` 之后调用 `apply_hierarchy_assimilation`
   - 仅当 `hierarchy_assimilation_rate > 0` 时激活

### v12 配置 (vs v11)

| 参数 | v11 | v12 | 变更原因 |
|------|-----|-----|---------|
| hierarchy_assimilation_rate | 0 (不存在) | **0.05** | 解决文化发散→帝国碎片化 |
| conquest_base_prob | 0.01 | **0.02** | 加速碎片后重建 |
| total_steps | 10000 | **20000** | 观察更多文明周期 |
| checkpoint_interval | 2500 | **5000** | 匹配更长模拟 |

### 预期效果

- Q 不再单调增长 → 帝国内部文化趋同抑制发散
- 帝国存活更久 → H 和 largest_pop 在 step 10000+ 仍保持较高值
- 碎片化后更快重建 → conquest_base_prob 翻倍

### 运行

```bash
bash scripts/run_v12.sh
```

## [2026-05-12] milestone | v12 Step 5000 — 文化同化初步验证

- **Q = 0.501** (v11=0.545, **降低 8.1%**) — 文化同化正在抑制发散!
- **帝国 = 2** (v11=1) — 帝国更稳定, 数量翻倍
- **largest = 44,505** (v11=40,711, +9%) — 帝国规模更大
- **政体总数 = 5,717** (v11=7,123, **减少 20%**) — 碎片化程度降低
- **国家 = 10** (v11=17, -41%) — 更集中的政治格局
- H=19, Gini=0.811, N=111,687 — 其他指标与 v11 一致
- **关键验证点**: step 10000 时 Q 和帝国数量是否仍健康

## [2026-05-12] milestone | v12 Step 10000 — 文化同化效果有限

- **Q = 0.764** (v11=0.858, **降低 11%**) — 同化有效但不足
- **帝国 = 0** — 与 v11 相同, 同化未能阻止长期碎片化
- **H = 12** (v11=9, v10=11) — 略好于其他版本
- **largest = 3,340** (v11=2,001, v10=2,309) — 最佳
- **三版本 step 10000 对比**:
  | 指标 | v10 | v11 | v12 |
  |------|-----|-----|-----|
  | Q | 0.745 | 0.858 | **0.764** |
  | H | 11 | 9 | **12** |
  | 帝国 | 0 | 0 | 0 |
  | largest | 2,309 | 2,001 | **3,340** |
- **根因分析**: 邻居文化漂移(始终在线, ~0.1-0.3/步) vs 同化(条件在线, ~0.04/步) → 数值上同化必输
- **深度反思**: wiki/reflection-2026-05-12.md

## [2026-05-12] feature | v12b — 强化文化同化 A/B 测试

### 反思驱动的改进 (见 wiki/reflection-2026-05-12.md)

**核心诊断**: v12 文化同化不足是因为"条件在线 vs 始终在线"的结构不对称
- 邻居漂移力: 0.01 × 20 neighbors = **0.20**/步 (始终在线)
- v12 同化力: 0.05 × 0.8 loyalty = **0.04**/步 (仅在 superior 存续时)
- 比值: 5:1, 漂移必胜

### v12b 三重修复

1. **hierarchy_assimilation_rate: 0.05→0.3** (6x): 同化力 0.3×0.8 = **0.24**/步
2. **assimilation_rate: 0.01→0.005** (半): 邻居漂移 0.005×20 = **0.10**/步
3. **双向同化**: superior 也吸收 subordinate 文化 (20% 反向速率)

**新力平衡**: 同化 0.24 vs 漂移 0.10 → **同化胜出 2.4:1**

### 运行

- v12b PID=4143715, 与 v12 并行运行 (20K 步对照实验)
- 预期: Q 在 step 10000 保持 <0.5, 帝国存活时间显著延长

## [2026-05-13] change | v13: 异步分析架构 + 二进制 Snapshot

### v12/v12b 完整结果 (20K 步)

两个模拟均完成:

| 指标 | v12 (20K) | v12b (20K) |
|------|-----------|------------|
| N | 130,696 | 129,849 |
| Gini | 0.795 | 0.797 |
| Q | 0.928 | 0.946 |
| H | 8 | 8 |
| empires | 0 | 0 |
| largest | 1,748 | 1,560 |
| io% | 95.1% | 96.1% |
| wall | 60,000s | 60,000s |

**关键发现**: v12b 的文化更均匀 (Q=0.946 vs 0.928), 但帝国数仍为 0。
**结论**: 政治碎片化的根本原因不是文化分歧, 而是 leader 死亡导致的
继承-忠诚衰减链 (succession → loyalty×0.7 → rebel)。

### 性能瓶颈深度分析

用户要求分析 A100 GPU 加速可行性。分析结果:

- GPU 加速物理计算收益 <1% (物理仅占 0.2-3.2% 时间)
- 真正瓶颈: "io" 阶段 (96%) 包含分析计算 + CSV 写入
- 分析算法 (Union-Find, BFS, 链式遍历) 不适合 GPU

详见 `wiki/gpu-acceleration-analysis.md`。

### v13 实现内容

1. **异步分析线程** (`src/analysis/async_analyzer.hpp`):
   - 在 `network_window` 步, 深拷贝 ParticleData snapshot 到后台线程
   - 后台执行: detect_polities, hierarchy_metrics, power, Gini_power, CSV 写入
   - 主循环立即继续下一步物理计算
   - 分析步的 io 从 95% 降至 11.5%

2. **二进制 Snapshot** (`csv_writer.cpp`):
   - 新增 `write_snapshot_binary()` 方法
   - 通过 `snapshot_binary = true` 启用
   - 130K 粒子: CSV ~26MB (50s) → Binary ~20MB (<2s)
   - 自定义格式: magic "POLI" + header + packed per-particle data

3. **A100 迁移工具**:
   - `scripts/deploy_a100.sh`: 一键部署到 A100 服务器
   - `examples/genesis_100k_fast.cfg`: HPC 优化配置

4. **配置系统**:
   - `config.hpp`: 新增 `snapshot_binary` 参数
   - `config.cpp`: 新增解析逻辑

### 正确性验证

2000 步快速验证通过:
- `order_params.csv`: 2 行完整数据 ✓
- `polity_summary.csv`: 2 行完整数据 ✓
- `demographics.csv`: 4 行完整数据 ✓
- 异步输出与控制台打印一致 ✓
- 158/160 单元测试通过 (2 个超时为历史已知)

### 预期加速

| 方案 | 预期加速 | 状态 |
|------|---------|------|
| 异步分析 | 3-5x | ✅ 已实现 |
| 二进制 snapshot | 1.5-2x (I/O) | ✅ 已实现 |
| A100 服务器 CPU (128核) | 1.3-2.7x | 就绪 |
| **组合** | **4-10x** | **预期** |

## [2026-05-15] change | v14: 继承机制修复 — 帝国碎片化根因

### 根因分析

v12/v12b 在 20K 步后均出现 0 帝国，尽管 Q→0.95（高文化统一）。

数学推导表明碎片化**不是文化问题**，而是继承-忠诚衰减链:

```
旧参数: succession_loyalty_factor = 0.7, heir_cap = 0.6
假设 L₀ = 0.9, rebel_threshold = 0.1:
  1 次继承: 0.9 × 0.7 = 0.63
  2 次继承: 0.63 × 0.7 = 0.44
  3 次继承: 0.44 × 0.7 = 0.31
  4 次继承: 0.31 × 0.7 = 0.22
  5 次继承: 0.22 × 0.7 = 0.15 → 接近反叛！

领导寿命 ~40年 = ~4000步 → 帝国最多存活 5×4000 = 20K 步
```

这完美解释了 v12b 在 20K 步后 0 帝国的现象。

### v14 修复

```
新参数: succession_loyalty_factor = 0.85, heir_cap = 0.8
假设 L₀ = 0.9:
  1 次继承: 0.9 × 0.85 = 0.765
  3 次继承: 0.9 × 0.85³ = 0.55
  5 次继承: 0.9 × 0.85⁵ = 0.40
  8 次继承: 0.9 × 0.85⁸ = 0.25
  11 次继承: 0.9 × 0.85¹¹ = 0.15

帝国可存活 ~11 次继承 = ~44K 步 (vs 旧 ~5 次 = ~20K 步)
```

### 代码变更

- `loyalty.hpp`: 新增 `succession_loyalty_factor`, `succession_heir_loyalty_cap` 到 LoyaltyParams
- `loyalty.cpp`: `process_succession()` 使用参数化值替代硬编码 0.7/0.6
- `config.hpp/cpp`: 新增配置解析
- `main.cpp`: 传递 loyalty_params 到 process_succession

### v14 运行配置

- 20K 步, 130K 粒子
- 异步分析 + 二进制 snapshot (v13 性能优化)
- succession_loyalty_factor = 0.85
- succession_heir_loyalty_cap = 0.8
- v12b 文化同化参数延续
- PID=661524

---

## [2026-05-18] change | v14 结果分析与 v14b 修正

### v14 结果（失败）

| 指标 | v12b (20K步) | v14 (20K步) |
|------|-------------|-------------|
| N | 129,849 | 3,293 |
| mean_loyalty | 0.673 | **0.856** ✓ |
| H (max depth) | 8 | 3 |
| empires | 0 | 0 |
| Q (cultural) | 0.94 | 0.79 |

**关键发现**: 继承修复验证成功 (loyalty 0.67→0.86), 但人口崩溃 (100K→3K) 使结果无意义。

### 根因: 错误的初始条件文件

v14 配置使用了 `genesis_100k.csv`（随机均匀分布），而 v12b 使用的是
`genesis_hyde_100k.csv`（基于 HYDE 历史人口密度生成，地形适配）。

错误的 IC 文件配合 `carrying_capacity_base=80` 和 `max_fertility=0.003` 产生了
过度人口增长 → 密度远超承载力 → 大规模死亡的恶性循环。

步骤 1000 对比:
- v12b: deaths=22,129 (22%), N=90,395
- v14:  deaths=91,033 (91%), N=12,888

### v14b 修正

使用 v12b **完全相同的物理参数和 IC 文件** + v14 继承修复:
- `initial_conditions_file = examples/genesis_hyde_100k.csv`
- `terrain_type = continent`
- `carrying_capacity_base = 20.0`
- `max_fertility = 5e-4`
- `culture_dim = 4`
- `succession_loyalty_factor = 0.85`
- `succession_heir_loyalty_cap = 0.8`
- `snapshot_binary = true`

配置文件: `examples/genesis_100k_v14b.cfg`
PID: 3302563

### 预期

v14b 应展现:
1. 人口稳定在 ~130K (与 v12b 相同)
2. mean_loyalty ≥ 0.85 (继承修复效果)
3. 帝国存续时间 >> v12b (loyalty 衰减更缓慢)

---

## [2026-05-18] change | InteractionNetwork O(N²) 性能修复

### 问题

v14b 模拟在 step 100 卡死 (18+ 分钟无输出)，GDB 确认:
- 47/48 OpenMP 线程空闲
- 主线程串行执行巨型 hash map 操作

### 两个 O(N²) 级瓶颈

1. `build_dominance_graph` cycle detection: per-particle `vector<bool>(N)` → O(N²)
2. `flows_` 全局 `unordered_map<PairKey, Real>` (40M+ 条目): 串行插入 280M 次

### 修复

| 组件 | 旧实现 | 新实现 | 加速比 |
|------|--------|--------|--------|
| Cycle detection | O(N²) per-iteration vector | O(N) generation-stamp | ~1000x |
| Flow storage | 1 × 40M-entry global map | N × 800-entry per-particle maps | ~10x |
| Record window | 20 steps | 5 steps | 4x |

### 效果

- Step 100: 18+ min (卡死) → 14 seconds
- 模拟正常运行: `[100/20000] 0.5% N=100000 wall=289s rate=0.3 step/s`
- ETA: ~16 小时 (与 v12b 基线一致)

### 代码变更

- `src/analysis/network_analysis.hpp`: 重构 InteractionNetwork 为 per-particle map 架构
- `src/analysis/network_analysis.cpp`: O(N) cycle detection + per-particle accumulator
- `src/main.cpp`: `network.resize()` 调用 + NETWORK_RECORD_WINDOW 20→5

### v14b 初步结果 (step 1000)

人口动力学完美复现 v12b:
- v14b: N=90,260, deaths=22,305, births=12,565
- v12b: N=90,395, deaths=22,129, births=12,524
- 差异 <1% — 物理等价性已验证

性能分布 (step 1000):
- population=52.66% (新主导瓶颈: mortality/reproduction)
- io=23.87% (snapshot CSV)
- dynamics=6.17%, exchange=3.45%, culture=5.61%
- analysis=0.23% ← 网络修复后几乎为零

运行速率: 0.5 step/s (vs 旧代码 0.3), ETA ~11 小时

### v14b Step 5000 完整分析 — 关键突破

| 指标 | v12b (step 5000) | v14b (step 5000) | 变化 |
|------|-----------------|-----------------|------|
| N | 111,801 | 110,839 | ≈ 相同 |
| H (max depth) | 16 | **28** | **+75%** |
| mean_loyalty | 0.865 | 0.832 | -3.8% |
| Ψ (feudalism) | 0.597 | **0.717** | +20% |
| empires | 1 | 1 | ✓ |
| states | 15 | **19** | +27% |
| largest_pop | 40,837 | 7,051 | ↓ |

**核心发现**: 继承修复使层级深度从 16 → 28，更加封建化。

**科学验证的关键对照**:
- v12b: step 5000 有 40K 人帝国 → step 10000 崩溃至 2.6K (0 帝国)
- v14b: step 5000 有 7K 人帝国 → step 10000 **未能到达** (step 8000 终止)

v12b 的帝国更大但更脆弱（忠诚快速衰减导致崩溃）。
v14b 的帝国更小但可能更持久（忠诚衰减缓慢）。

---

### v14b 模拟终止 — step 8000 KE 发散 (2026-05-18 晚)

**结果**: v14b 在 step 8000 后进程终止。最后输出:
```
Step 8000/20000  N=108817  Gini=0.8
[WARN] KE/NkT=3.73198 — thermal equilibrium violation
```

**动能发散轨迹**:

| Step | KE | KE/NkT | V_social (×10⁹) |
|------|-----|--------|-----------------|
| 5000 | 71,736 | 2.16 | 55.2 |
| 6000 | 82,439 | 2.48 | 59.0 |
| 7000 | 94,838 | 2.88 | 64.6 |
| 8000 | 121,831 | 3.73 | 68.4 |

**分析**: KE 在 step 5000-8000 增长 70%，明显超线性增长。
社交势能也持续增长 (+24%)，指示深层级 (H=28) 的力链
持续向系统注入动能，Berendsen 恒温器无法耗散。

**根因**: 继承修复产生的深层级 (H=28) 导致:
1. 长力链 (leader←follower...×28层) 累积大梯度力
2. 粒子被拉向层级中心时获得大动能
3. Berendsen 恒温器 (τ~10步) 来不及耗散

**人口动力学对比** (step 8000):
- v14b: N=108,817 (稳定), growth_rate=-0.75%
- 人口结构: children=24.7%, elderly=16.0%, fertile=41.3%
- 模拟在人口学意义上是健康的，纯粹是力学不稳定

**结论**: 需要修复恒温器/力模型后重跑。
详见 `wiki/reflection-2026-05-18.md` 中的修复方案讨论。

---

### v14c: KE 发散修复 — 验证成功 (2026-05-19)

**修复内容**:
1. `F_MAX` per-pair: 100 → 30
2. `F_TOTAL_MAX` per-particle: 200 → 50 (`dp_max=0.5 ≈ v_thermal=0.55`)
3. Berendsen 恒温器: 每10步→每步, target = N×T (正确2D), 梯度耦合 τ=0.1

**快速验证结果** (10K particles × 5000 steps, 67 min):

| Step | N | KE/(N×T) | H | 状态 |
|------|------|---------|---|------|
| 500 | 10,760 | 1.99 | - | ✓ |
| 1000 | 12,629 | 1.71 | - | ✓ |
| 2500 | 20,896 | 1.45 | 3 | ✓ |
| 5000 | 55,665 | 1.40 | 11 | ✓ |

**关键验证**: KE/(N×T) 从 1.99 收敛到 1.40，**无发散趋势**。
对比 v14b 的 2.16→3.73→崩溃，修复完全有效。

**科学指标** (step 5000, 55K particles):
- Gini = 0.71, Q = 0.27, H = 11
- 662 polities (647 bands, 10 tribes, 59 chiefdoms, 18 states)
- mean_loyalty = 0.94, n_attached = 55003/55665 (99%)

**全量 v14c 运行**: 100K×20K 已启动 (PID 3408945, step 700, ETA ~18h)
- Step 700: N=80,914, rate=0.3 step/s, 无 KE 警告
- 人口从 100K→81K 的初始调整符合预期 (不利地形粒子死亡)

---

## [2026-06-11] change | P0 物理机制验证实验完成

- 编译: Zeus (A100, OpenMP 48线程, `build-pv/`, 无 MPI)
- 实验配置: `research/physics-validation/jobs/M1.*/`
- 分析报告: `research/physics-validation/analysis-P0.md`
- 状态: `research/physics-validation/state.md` → current_stage=ANALYZE

### M1.1 LJ热力学
- γ=0: 总能下降 62%（-4226→-10416），KE≈1100-1200 稳定
- γ=1: 总能下降 21%（-3997→-6064），KE≈1000 匹配 T=1.0
- **诊断(M1.1-d)**：平坦+无LJ+γ=0，总能仍下降 → 问题在积分器/约束势，非 LJ 截断

### M1.2 地形力
- 平坦: Gini=0.71（自发聚类）；大陆: Gini=0.03（扩散）
- ✅ 大陆实验中 PE_terrain 从 +86490→+98 沉降，能量转换正确

### M1.4 封闭交换
- ✅ Gini=0 全程，N=1000 保持，财富均匀分布
- 验证对称交换收敛到 Boltzmann-Gibbs 平衡

### M1.8 涨落-耗散定理（16 T×γ 组合）
- ✅ 高 γ(≥1.0) 时 KE/N≈T，偏差 <3%
- 低 γ(0.1) 时 KE/N 偏高 17-20%（未充分热化，预期内）
- KE/N 不依赖 γ，验证 Langevin 核心不变性

### M1.5 Gini 参数扫描（48 组合: exchange_rate×aw×wd）
- ℹ️ 所有组合 Gini≈0.0045（零结果，但预期内）
- 对称系统中 exchange_rate/aw/wd 不产生 Gini 差异
- 需不对称机制（消费/生产/死亡/征服）才能产生不平等

---

## [2026-06-11] fix | terrain_type=flat 未被识别→能量「丢失」根因修复

- **问题**：P0 实验 M1.1-d 发现平坦地形上 γ=0 能量仍「丢失」6200 单位
- **诊断**：阅读 `src/main.cpp` → `terrain_type=flat` 不在 `use_synthetic_grid` 列表或 `"grid"` 分支中
- **根因**：`flat` 落入 `else` 默认高斯势阱分支（depth=10+6），所有「平坦」实验实际跑在两阱上
- **修复**：`src/main.cpp` L252 增加 `else if (cfg.terrain_type == "flat")` 分支（空 wells）
- **验证**：修复后平坦+无LJ+γ=0，total=960.32 完美守恒（零漂移）；平坦+LJ+γ=0，波动 ~6%（LJ 截断非 shift-force）
- **影响**：原判定「积分器 bug」←实为配置分支遗漏。BBK 积分器物理正确

---

## [2026-06-12] query | 🎉 STATE 涌现！f=1e-4×12500步 产生 6 个 state（Cycle 5 里程碑）

- **历史性时刻**：Politeia 首次涌现 state（pop ≥ 1000）
- **参数配方**：cbp=1.0, pr=0.8, deter=on, slf=0.95, fertility=1e-4, 12500步
- **生长轨迹**：N=12.8K→46.5K，polities=249→215，max=313→1515
- **征服持续有效**：~20K-25K conquests / 500步，层级 H=12
- **教训链 4 深坑→突破**：flat bug → cbp=0.02 过低 → 人口爆炸淹没 conquest → 先切 fertility 再放 conquest → STATE
- **下一步**：M2.1-reduced China vs Europe 对照（锁死全套参数，12 runs）
- 反思: reflection-cycle5.md

---

## [2026-06-12] change | M2.1-reduced 6/6完成：China vs Europe 地形对照

- **实验**：10K粒子 × 5000步 × 3 seeds × 2 地形 = 6 runs，全部成功
- **参数锁死** M1.16 STATE 配方 (cbp=1.0, pr=0.8, deter=on, slf=0.95, f=1e-4)
- **反直觉发现**：
  - China 地形 → 293 政权（更少），max=303，HHI=0.00785（更均匀）
  - Europe 地形 → 327 政权（更多），max=345，HHI=0.00920（更集中）
- **假说修正**：不是"封闭地形→更大政体"，而是"破碎地形→更不均衡发展"
- **解释**：Europe 的半岛/海湾将人口分隔→局部密集 conquest→少数大政体+大量小碎片
- **5000步未达 state 门檻**（M1.16 需 12500 步），建议延长至 10000 步
- commit: analysis-P0.md 追加 M2.1 分析
- 对比 20K×10000步 失败：人口爆炸 (10K→75K in 9K步)，20K 过高—确认 10K 是最优规模
- 反思: reflection-cycle5.md

---

## [2026-06-12] change | Cycle 5 收关：M2.1 10K步三种地形完整对比

- **M2.1 10K步 6/6成功** (China × Europe, 10K×10000步×3 seeds)
- **三种地形系统对比 @ 10000步**:
  - Continent (M1.16): N=31283, max=983, HHI=0.01119, chiefdoms=142 — **人口承载力 2×**
  - Europe (M2.1): N=16045, max=707, HHI=**0.01440** (最高), chiefdoms=105 — **最快合并**
  - China (M2.1): N=16154, max=485, HHI=0.01136 (最低), chiefdoms=113 — **最均匀**
- **四大发现**:
  1. 人口承载力因地形而异 (Continent 2× Europe/China)
  2. Europe 破碎地形催生最高集中度 (HHI 0.0144)
  3. Europe 合并最快 (↓42.6%), Continent 最稳定 (↓13.3%)
  4. 原始假说"China封闭→更大政体"被彻底推翻
- **修正**：政体规模 = 人口承载力 × 空间破碎度
- **5K→10K 差距扩大**: Europe advantage 从 14% → 46%
- **10000步均未达 state** — 需延长至 12500 步验证 state 级差异
- 下一步: Phase 2 — 三种地形×12500步 (6 new runs, ~2h)
- 反思: reflection-cycle5.md (更新为最终版)

---

## [2026-06-15] change | Cycle 6: 五轮迭代总结 + Phase 2 china_s42 完成

- **Phase 2 china_s42 12500步完成**: N=24423, max=733, **0 states** — China 远不如 Continent
- **Continent vs China @12500步**: Continent 6 states + 1515 max vs China 0 states + 733 max
- **五轮迭代教训文档化**（reflection-cycle6.md）:
  1. 极端值诊断："bug"其实是默认参数太小
  2. 源头阻断：先 cap fertility 再调 conquest
  3. 单变量验证：不要同时调两个对抗参数
  4. 10K 上限：20K → 人口爆炸 → 白跑
  5. 实验推翻假说："China封闭→更大政体"被证伪
- **修正**: 政体规模 = 人口承载力 × 空间破碎度
- **Phase 2 剩余**: china_s123/456 + europe_s42/123/456 串行运行中 (~50min)
- **下一步**: Phase 2 完成 → WRITE 论文阶段
- 反思: reflection-cycle6.md
