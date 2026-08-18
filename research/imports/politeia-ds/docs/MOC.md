# Politeia — Map of Content

> 本页是 Obsidian 知识图谱的**中心节点**。所有文档通过 `[[wikilink]]` 互相关联。
> 在 Obsidian 的 Graph View 中打开本页可以看到完整的文档关系网络。
>
> **Wiki 架构说明**：本项目采用 LLM Wiki 三层架构，详见 [[AGENTS]]。
> - **`raw/`** — 原始资料（不可变，LLM 只读）
> - **`wiki/`** — LLM 维护的知识层（index / log / modules / concepts / entities / decisions）
> - **`AGENTS.md`** — Schema 约定

---

## 核心文档

```
                    ┌─────────────────────┐
                    │   research-proposal  │  ★ 项目灵魂（活文档）
                    │   （研究方案）         │
                    └────────┬────────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
   ┌──────────────┐  ┌─────────────┐  ┌──────────────────────┐
   │ CODE_GUIDE   │  │ DEVELOPMENT │  │ stochastic-          │
   │（代码指南）    │  │ _PLAN       │  │ distributions        │
   │              │  │（开发计划）   │  │（随机分布清单）        │
   └──────┬───────┘  └──────┬──────┘  └──────────┬───────────┘
          │                 │                     │
          └────────┬────────┘                     │
                   ▼                              │
        ┌────────────────────┐                    │
        │ parallel-framework │◄───────────────────┘
        │ -design            │
        │（并行框架设计）      │
        └────────────────────┘
```

---

## 文档索引

### 理论层

| 文档 | 内容 | 关键章节 |
|------|------|----------|
| [[research-proposal]] | 物理模型、哲学推导、Agent 定义、交互规则 | §1 核心思想, §2 Agent 定义, §3 Langevin 框架, §6 序参量, §9.6 可配置实验 |

### 实现层

| 文档 | 内容 | 关键章节 |
|------|------|----------|
| [[DEVELOPMENT_PLAN]] | 架构设计、开发阶段、时间估算、测试策略 | §1 SoA/MPI, §2 Phase 0-27, §6 测试策略 |
| [[CODE_GUIDE]] | 每个代码模块的物理含义和 API 说明（完整版） | core, domain, force, integrator, interaction, population, analysis |
| [[docs/parallel-framework-design]] | 80 亿粒子的 HPC 并行方案（Morton Z-order） | SFC 分解, 负载均衡, 通信优化 |

### Wiki 知识层（wiki/）

| 页面 | 内容 |
|------|------|
| [[wiki/index]] | **全局索引**：所有页面的一行摘要目录 |
| [[wiki/log]] | **变更日志**：按时间倒序记录 ingest/change/decision 等 |
| [[wiki/modules/core]] | core 模块：SoA 数据容器、类型、常数、配置 |
| [[wiki/modules/domain]] | domain 模块：Cell List、MPI 域分解、Morton SFC |
| [[wiki/modules/force]] | force 模块：社会力、地形势、DEM 加载 |
| [[wiki/modules/integrator]] | integrator 模块：BBK Langevin 积分器 |
| [[wiki/modules/interaction]] | interaction 模块：资源交换、文化、技术、忠诚度 |
| [[wiki/modules/population]] | population 模块：繁殖、死亡、瘟疫、承载力 |
| [[wiki/modules/analysis]] | analysis 模块：序参量、网络、政体、性能监控 |
| [[wiki/modules/io]] | io 模块：CSV 输出、IC 加载、checkpoint |

### Schema

| 文档 | 内容 |
|------|------|
| [[AGENTS]] | Wiki 三层架构约定、操作流程（Ingest/Change/Decision/Query/Lint）、页面格式 |

### 参考层

| 文档 | 内容 | 关键章节 |
|------|------|----------|
| [[docs/stochastic-distributions]] | 全部随机过程的分布类型、公式、控制参数 | Langevin 噪声, 死亡/生育, Poisson 跳跃, 社会动力学 |

### 环境与构建

| 文档 | 内容 | 说明 |
|------|------|------|
| [[docs/build-network-umi-zeus]] | UMI 无外网时通过 Zeus 拉取 googletest / 构建 | 共享盘、`cmake` 流程、排查要点 |
| [[docs/server-config]] | Zeus / UMI 拓扑、SSH、项目路径与 GPU 实验流程 | spack、共享文件系统、Agent 标准操作 |

### 工具层

| 文档/脚本 | 内容 | 关键功能 |
|-----------|------|----------|
| `scripts/plot_worldmap.py` | 世界地图可视化（交互式/静态/动画） | Plotly Scattergeo, 8 种着色, 9 个区域, 政体叠加 |
| `scripts/fetch_terrain.py` | 真实地形数据获取与转换 | ETOPO1 下载, 程序化地形, .asc 导出, 配置生成 |
| `scripts/fetch_rivers.py` | RiverField 河流走廊场生成 | Natural Earth/HydroRIVERS 预处理, proximity ASCII 导出, `cfg` 片段生成 |
| `scripts/generate_genesis.py` | 初始条件生成（HYDE 3.3 校准） | 29 区域, 10K/70K BCE, 可变粒子规模 |

### 算例层

| 文档/算例 | 内容 | 说明 |
|-----------|------|------|
| [[examples/CASES]] | 标准算例索引 | 命名规则、运行方式、数据源 |
| `examples/genesis_hyde_100k` | HYDE 创世纪 10 万 | **主算例**，HYDE 3.3 校准 |
| `examples/riverfield_global_snippet.cfg` | RiverField 全局配置片段 | 合并到 `genesis_hyde_baseline.cfg` 等完整算例以启用 major rivers 走廊场 |
| `examples/adam_eve` | 亚当夏娃 | 最小初始条件验证 |

### 思考层

| 文档 | 内容 | 关键章节 |
|------|------|----------|
| [[docs/why-humans-not-animals]] | 从 ε 方程推导"文明为何只属于人类"，附消融实验设计 | 正反馈环路, Kramers 逃逸, 消融矩阵 |

---

## 概念交叉索引

以下是跨文档反复出现的核心概念，以及它们在各文档中的位置。
在 Obsidian 中可以为每个概念创建独立笔记并反向链接。

### 物理框架

| 概念 | research-proposal | CODE_GUIDE | DEVELOPMENT_PLAN | stochastic-distributions |
|------|-------------------|------------|------------------|--------------------------|
| Langevin 方程 | [[research-proposal#三、物理框架：Langevin-跳跃扩散社会动力学\|§3]] | [[CODE_GUIDE#4. `integrator/` — 时间积分\|integrator]] | — | [[docs/stochastic-distributions#1. 运动方程 — Langevin 噪声\|§1]] |
| BBK 积分器 | [[research-proposal#3.1 为什么选择 Langevin 动力学而非纯 Hamilton 力学\|§3.1]] | [[CODE_GUIDE#4. `integrator/` — 时间积分\|integrator]] | — | [[docs/stochastic-distributions#1. 运动方程 — Langevin 噪声\|§1]] |
| Poisson 跳跃 | [[research-proposal#2.4 能量利用能力 ε_i：文明演化的核心驱动力\|§2.4]] | [[CODE_GUIDE#5. `interaction/` — 个体间交互\|interaction]] | — | [[docs/stochastic-distributions#5. 技术演化 — Lévy-type Jump-Diffusion\|§5]] |
| Kramers 逃逸 | [[research-proposal#3.6 Kramers 逃逸理论 → 制度变迁的概率\|§3.6]] | — | — | [[docs/why-humans-not-animals#四、用 Kramers 逃逸理论的语言\|人 vs 动物]] |
| 正反馈环路 | [[research-proposal#2.4 能量利用能力 ε_i：文明演化的核心驱动力\|§2.4]] | — | — | [[docs/why-humans-not-animals#三、正反馈环路——文明的自催化\|自催化]] |

### 个体属性

| 概念 | research-proposal | CODE_GUIDE | stochastic-distributions |
|------|-------------------|------------|--------------------------|
| 状态向量 (x, p, w, c⃗, ε) | [[research-proposal#2.2 个体状态向量\|§2.2]] | [[CODE_GUIDE#1. `core/` — 基础数据层\|core]] | — |
| 财富 w | [[research-proposal#2.3 参数、派生量与约束\|§2.3]] | [[CODE_GUIDE#5. `interaction/` — 个体间交互\|interaction]] | [[docs/stochastic-distributions#5. 技术演化 — Lévy-type Jump-Diffusion\|§5 跳跃]] |
| 文化向量 c⃗ | [[research-proposal#2.2 个体状态向量\|§2.2]] | [[CODE_GUIDE#5. `interaction/` — 个体间交互\|interaction]] | [[docs/stochastic-distributions#4. 生育\|§4 变异]] |
| 技术 ε | [[research-proposal#2.4 能量利用能力 ε_i：文明演化的核心驱动力\|§2.4]] | [[CODE_GUIDE#5. `interaction/` — 个体间交互\|interaction]] | [[docs/stochastic-distributions#5. 技术演化 — Lévy-type Jump-Diffusion\|§5]] |

### 人口动力学

| 概念 | research-proposal | CODE_GUIDE | stochastic-distributions |
|------|-------------------|------------|--------------------------|
| Gompertz 死亡 | [[research-proposal#2.5 人口动力学：繁殖模型\|§2.5]] | [[CODE_GUIDE#6. `population/` — 人口动力学\|population]] | [[docs/stochastic-distributions#3. 死亡机制\|§3]] |
| 生育率 φ(a) | [[research-proposal#2.5 人口动力学：繁殖模型\|§2.5]] | [[CODE_GUIDE#6. `population/` — 人口动力学\|population]] | [[docs/stochastic-distributions#4. 生育\|§4]] |
| 瘟疫 SIR | [[research-proposal#2.5 人口动力学：繁殖模型\|§2.5]] | [[CODE_GUIDE#6. `population/` — 人口动力学\|population]] | [[docs/stochastic-distributions#6. 社会动力学\|§6]] |
| 寿命派生量 λ_i | [[research-proposal#9.6 可配置实验框架：规则空间的系统搜索\|§9.6]] | [[CODE_GUIDE#6. `population/` — 人口动力学\|population]] | [[docs/stochastic-distributions#3. 死亡机制\|§3]] |

### 社会结构

| 概念 | research-proposal | CODE_GUIDE | stochastic-distributions |
|------|-------------------|------------|--------------------------|
| 忠诚度/依附 | [[research-proposal#6.2 第二层：层级结构的形态——依附网络分析\|§6.2]] | [[CODE_GUIDE#9b. `interaction/loyalty.hpp/cpp` — 依附关系与忠诚度系统\|loyalty]] | [[docs/stochastic-distributions#6. 社会动力学\|§6]] |
| 征服 | [[research-proposal#9.6 可配置实验框架：规则空间的系统搜索\|§9.6]] | [[CODE_GUIDE#9b. `interaction/loyalty.hpp/cpp` — 依附关系与忠诚度系统\|loyalty]] | [[docs/stochastic-distributions#6. 社会动力学\|§6]] |
| 序参量 (Gini, Q, H) | [[research-proposal#6.1 第一层：阶级是否涌现——不平等度量\|§6.1-6.3]] | [[CODE_GUIDE#7. `analysis/` — 序参量与观测\|analysis]] | — |

### 并行计算

| 概念 | DEVELOPMENT_PLAN | CODE_GUIDE | parallel-framework-design |
|------|------------------|------------|---------------------------|
| SoA 数据布局 | [[DEVELOPMENT_PLAN#1.1 数据布局：SoA（Structure of Arrays）\|§1.1]] | [[CODE_GUIDE#1. `core/` — 基础数据层\|core]] | — |
| MPI 域分解 | [[DEVELOPMENT_PLAN#1.2 MPI 并行策略：2D 区域分解\|§1.2]] | [[CODE_GUIDE#2. `domain/` — 空间管理\|domain]] | [[docs/parallel-framework-design#二、为什么必须用空间填充曲线\|§2]] |
| Morton Z-order | — | — | [[docs/parallel-framework-design#三、Morton (Z-order) 曲线方案\|§3]] |

---

## Obsidian 使用建议

1. **将 `civil/` 目录作为 Obsidian Vault 打开**
2. **启用 Graph View**：可以看到所有文档的关系拓扑
3. **标签建议**：可以在各文档中添加 `#tag` 进一步分类
   - `#physics` — 物理模型相关
   - `#code` — 代码实现相关
   - `#hpc` — 高性能计算相关
   - `#emergence` — 涌现现象相关
   - `#experiment` — 实验设计相关
4. **反向链接面板**：点击任何 `[[链接]]`，Obsidian 会自动显示所有引用该文档的其他文档
5. **Outline 面板**：本项目的文档都有清晰的 `##`/`###` 层级，Outline 面板可快速导航
