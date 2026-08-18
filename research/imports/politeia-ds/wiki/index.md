# Politeia Wiki Index

> 全局索引：每个页面一行摘要。LLM 优先读此文件定位相关页面，再深入阅读。
> 按类别组织，每次 ingest / 重大变更时更新。
>
> **`docs/` 与 `wiki/`**：长文参考（随机分布、并行设计、MOC 等）在 **`docs/`** 维护；本索引通过 `[[docs/...]]` 链过去即可，**不要求**把 `docs/` 全文搬进 `wiki/`。分工说明见 [[AGENTS]] 中「docs/ 与 wiki/ 的分工」一节。

---

## 元文档（文档管理本身）

| 页面 | 摘要 |
|------|------|
| [[docs/llm-knowledge-architecture]] | **可推广总览**：五层文档模型（raw / 权威 / docs / wiki / 会话）、操作流程、与 planning-with-files 集成、新项目上线路线图。 |

## 核心文档（research-proposal 为中心，其余围绕其演化）

| 页面 | 摘要 |
|------|------|
| [[research-proposal]] | **项目灵魂**：Langevin-跳跃扩散文明演化模型的完整理论——核心映射、Agent 定义（x,p,w,c⃗,ε）、力场、人口动力学、序参量、可配置实验框架。所有其他文档围绕此文件变动。 |
| [[DEVELOPMENT_PLAN]] | 架构设计（SoA、MPI 2D 区域分解）、Phase 0–27+ 开发阶段、目录结构、时间估算、测试策略。依赖 research-proposal 中的模型定义。 |
| [[CODE_GUIDE]] | 代码模块物理含义与 API 的完整参考。拆分版见下方 wiki/modules/。 |

## 物理与数学（主文档在 `docs/`）

| 页面 | 摘要 |
|------|------|
| [[docs/stochastic-distributions]] | 模拟中全部随机过程的分布类型、公式、控制参数清单。 |
| [[docs/why-humans-not-animals]] | 从 ε 方程推导"文明为何只属于人类"——正反馈环路、Kramers 逃逸、消融实验设计。 |

## 并行与 HPC（主文档在 `docs/`）

| 页面 | 摘要 |
|------|------|
| [[docs/parallel-framework-design]] | 80 亿粒子的大规模并行方案：Morton Z-order SFC 分解、负载均衡、halo 通信优化。 |

## 环境与构建（主文档在 `docs/`）

| 页面 | 摘要 |
|------|------|
| [[docs/build-network-umi-zeus]] | UMI 无外网时通过 Zeus 拉取 googletest / CMake 构建的操作约定。 |
| [[docs/server-config]] | Zeus / UMI 拓扑、SSH、共享文件系统、spack 与 Agent 实验执行流程。 |

## 代码模块（wiki/modules/，拆分自 CODE_GUIDE）

| 页面 | 代码路径 | 摘要 |
|------|----------|------|
| [[wiki/modules/core]] | `src/core/` | SoA 粒子数据容器、类型别名、物理常数、配置解析 |
| [[wiki/modules/domain]] | `src/domain/` | Cell List 邻居搜索、MPI 2D 域分解、Morton SFC |
| [[wiki/modules/force]] | `src/force/` | 人际社会力（LJ 式）、地形外势、真实 DEM 加载 |
| [[wiki/modules/integrator]] | `src/integrator/` | BBK Langevin 积分器（Velocity-Verlet + 随机力） |
| [[wiki/modules/interaction]] | `src/interaction/` | 资源交换、文化动力学、技术演化、忠诚度与征服 |
| [[wiki/modules/population]] | `src/population/` | 繁殖、四重死亡、瘟疫 SIR、密度承载力 |
| [[wiki/modules/analysis]] | `src/analysis/` | 序参量（Gini/Q/H/F/Ψ）、网络分析、政体检测、性能监控 |
| [[wiki/modules/io]] | `src/io/` | CSV 输出、初始条件加载、断点续跑 |
| [[wiki/modules/river]] | `src/river/` | RiverField 河流走廊场、proximity/河道力、与主循环耦合 |
| [[wiki/modules/climate]] | `src/climate/` | ClimateGrid 气候栅格（环境分层扩展） |

## 算例与数据

| 页面 | 摘要 |
|------|------|
| [[examples/CASES]] | 标准算例索引：genesis_hyde_100k（主推）、genesis_hyde_baseline（1:1 人口）、adam_eve 等。 |

## 脚本工具

| 脚本 | 用途 |
|------|------|
| `scripts/generate_genesis.py` | HYDE 3.3 校准初始条件生成 |
| `scripts/plot_worldmap.py` | 世界地图可视化（Plotly Scattergeo） |
| `scripts/fetch_terrain.py` | 真实地形数据获取（ETOPO1） |
| `scripts/plot_order_params.py` | 序参量时间序列 |
| `scripts/plot_polities.py` | 政体可视化 |
| `scripts/plot_timeseries.py` | 通用时间序列 |
| `scripts/plot_snapshot.py` | 单帧快照6面板 |
| `scripts/plot_distributions.py` | 属性分布直方图 |
| `scripts/plot_phase_diagram.py` | 相图绘制 |
| `scripts/plot_terrain.py` | 地形可视化 |
| `scripts/plot_terrain_compare.py` | 多地形方案对比 |
| `scripts/terrain_compare.py` | 地形方案比较 |
| `scripts/param_scan.py` | 参数扫描驱动 |
| `scripts/param_sweep.py` | 自动化参数网格扫描（tax_rate × tax_efficiency × protection_gain） |
| `scripts/sweep_gini_h.py` | Gini-H 相图扫描：ability_saturation_w × attachment_threshold 参数空间 |
| `scripts/analyze_run.py` | 单次模拟的综合分析与可视化（7 步骤） |
| `scripts/rule_scan.py` | 规则空间扫描 |
| `scripts/scaling_test.py` | 弱/强扩展性测试 |
| `scripts/plot_scaling.py` | 扩展性结果绘图 |
| `scripts/plot_ablation.py` | 消融实验可视化 |
| `scripts/visualize.py` | 通用可视化入口 |

## 设计决策（wiki/decisions/）

| ADR | 摘要 |
|-----|------|
| [[wiki/decisions/ADR-001-docs-wiki-split]] | 保留 `docs/` 与 `wiki/` 并列，wiki 不复制长文 |
| [[wiki/decisions/ADR-002-umi-zeus-build]] | UMI 无外网时经 Zeus 完成首次 CMake 依赖拉取 |
| [[wiki/decisions/ADR-003-llm-knowledge-architecture]] | 五层知识架构 + planning-with-files + 当前焦点 |

## Schema 与导航

| 页面 | 摘要 |
|------|------|
| [[AGENTS]] | Wiki Schema：三层架构、操作流程（Ingest/Change/Decision/Query/Lint）、页面格式约定。 |
| [[docs/MOC]] | Obsidian 知识图谱中心节点：文档关系图、概念交叉索引。 |
| `wiki/index.md` | 本文件。 |
| `wiki/log.md` | 按时间顺序的变更日志。 |
| `wiki/troubleshooting.md` | 问题排查与解决方案总结：按模块分类的所有 bug、根因分析、修复方案和经验法则。 |
| `wiki/lessons-learned.md` | **经验教训提炼**：从 v3→v11 六代模拟中提取的开发原则、反模式、被证伪的假设、开发 checklist。后续开发必读。 |

## 反思与教训

| 日期 | 主题 | 文件 |
|------|------|------|
| 2026-05-19 | 层级修复三代迭代与验证方法论 | [[reflection-2026-05-19-v3]] |
| 2026-05-19 | v14c 全量基线终局摘要 (step 20k) | [[query-2026-05-19-v14c-final]] |
| 2026-05-19 | v14c@15000 vs v16 层级基线对比 | [[query-2026-05-19-hierarchy-baseline]] |
| 2026-05-19 | 双目标张力：物理约束 vs 文明涌现 | [[reflection-2026-05-19-v4]] |
| 2026-05-19 | 终局前夜：v17 五维验收矩阵与 v14c 快照 | [[reflection-2026-05-19-v5]] |
| 2026-05-19 | 阶段总结：v14c 完成、v17 长跑、运维与双目标 | [[reflection-2026-05-19-v6]] |
| 2026-05-19 | v17 中期：repair 解读、@5k 验收计划 | [[reflection-2026-05-19-v7]] |

| 页面 | 摘要 |
|------|------|
| [[wiki/simulation-comparison]] | 模拟版本综合对比：v3→v8→v8c→v9 指标演进 |
| [[wiki/reflection-2026-05-10]] | v3 诊断、Gini/KE/势能、财富集中根因 |
| [[wiki/reflection-2026-05-10-v2]] | Gini-Hierarchy 耦合、网络窗口、人口崩溃 |
| [[wiki/reflection-2026-05-11]] | 性能瓶颈误判、Union-Find、计算流图审计 |
| [[wiki/reflection-2026-05-12]] | （见文件内标题） |
| [[wiki/reflection-2026-05-18]] | （见文件内标题） |
| [[wiki/reflection-2026-05-19]] | （见文件内标题） |
| [[wiki/reflection-2026-05-19-v2]] | （见文件内标题） |

## 原始资料（raw/，LLM 只读）

| 目录 | 用途 |
|------|------|
| `raw/papers/` | 引用的论文 PDF / 摘要 |
| `raw/datasets/` | HYDE 3.3 等数据源说明 |
| `raw/notes/` | 手写笔记、会议记录 |

---

*最近更新：2026-05-19*
