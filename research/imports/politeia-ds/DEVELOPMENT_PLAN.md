# Politeia 开发计划

> **导航**：[[research-proposal]] · [[CODE_GUIDE]] · [[docs/parallel-framework-design]] · [[docs/stochastic-distributions]] · [[docs/llm-knowledge-architecture]]

## 当前焦点（活跃项，每周或阶段切换时更新）

> Agent 与人协作时**优先读本节**，勿通读全文 Phase 列表。归档完成的项移到 `wiki/log.md`。

| 优先级 | 项 | 状态 | 说明 |
|--------|-----|------|------|
| P0 | **v17 全量 100k（层级修复）** | **运行中** | step 3000/20k（15%）；repair~73k/周期；@5k ~1.8h |
| P0 | **v14c 基线** | ✅ | [[query-2026-05-19-v14c-final]] |
| P0 | **v14c 基线** | ✅ 完成 | step 20k：N=59671，H=53，环~21k；[[query-2026-05-19-v14c-final]] |
| P1 | **Phase 31 RiverField** | 代码已合入 | 验证算例 + 更新 `examples/CASES.md`；`discharge` 与真实河网数据管线待扩展 |
| P1 | **主算例长跑与复现** | 待 HPC | v17 后对比 v14c；更大规模 MPI 见 Phase 10 |
| P2 | **科学扫描** | 持续 | 参数扫描、消融（`rule_scan.py` / `param_sweep.py`）；结论写入 `wiki/log.md` query |
| P2 | **wiki 模块索引** | 进行中 | 补齐 `river`、`climate` 等于 `src/` 同步（lint 2026-05-19 已补 river/climate） |

**阻塞**：无外网 UMI 首次构建 → 见 [[docs/build-network-umi-zeus]]（[[wiki/decisions/ADR-002-umi-zeus-build]]）

**上次更新**：2026-05-19

---

## 项目概要

**项目名称**：Politeia — 基于 Langevin-跳跃扩散动力学的人类文明演化模拟器

**技术栈**：

- 语言：C++20
- 并行：MPI（区域分解 + 粒子通信）
- 构建：CMake（target-based）
- 随机数：`<random>`（Mersenne Twister / xoshiro256**）
- I/O：HDF5（大规模快照）+ CSV（时间序列）
- 测试：GoogleTest + CTest
- 数据后处理：Python 脚本（可视化/分析）

**编码规范**：遵循 `docs/modern-cpp-agent-rules.md`

---

## 一、架构设计

### 1.1 数据布局：SoA（Structure of Arrays）

> 设计动机 → [[research-proposal#2.2 个体状态向量]]
> 代码解读 → [[CODE_GUIDE#1. `core/` — 基础数据层]]

HPC 热点路径要求连续内存访问和向量化友好的数据布局。采用 SoA 而非 AoS：

```cpp
// AoS（不采用）：每个 agent 一个 struct，内存不连续
// struct Agent { double x[2], p[2], w; double cv[D]; double eps; ... };
// std::vector<Agent> agents;

// SoA（采用）：每个属性一个连续数组
struct ParticleData {
    // 空间自由度
    std::vector<double> x;    // [N*2] 位置 (x,y) 交错存储
    std::vector<double> p;    // [N*2] 动量 (px,py)

    // 内部自由度
    std::vector<double> w;    // [N] 财富
    std::vector<double> cv;   // [N*D] 文化向量（D 维）
    std::vector<double> eps;  // [N] 能量利用能力

    // 参数与附属属性
    std::vector<double> age;  // [N] 年龄
    std::vector<uint8_t> sex; // [N] 性别（0=女, 1=男）
    std::vector<double> imm;  // [N*M] 免疫向量（M 种病原体）

    // 元数据
    std::vector<int> alive;   // [N] 存活标志
    std::size_t count;        // 当前活跃粒子数
    std::size_t capacity;     // 预分配容量
};
```

### 1.2 MPI 并行策略：2D 区域分解

> 进阶方案（Morton Z-order SFC） → [[docs/parallel-framework-design]]

```
┌──────┬──────┬──────┐
│ Rank │ Rank │ Rank │
│  0   │  1   │  2   │
├──────┼──────┼──────┤
│ Rank │ Rank │ Rank │
│  3   │  4   │  5   │
├──────┼──────┼──────┤
│ Rank │ Rank │ Rank │
│  6   │  7   │  8   │
└──────┴──────┴──────┘
```

- 2D 空间域划分为 Px × Py 个子域
- 每个 rank 负责一个子域内的所有粒子
- 粒子跨域时通过 MPI 通信迁移
- 短程力计算需要 halo 区域（ghost 粒子）交换

### 1.3 目录结构

```
civil/
├── CMakeLists.txt              # 顶层构建
├── DEVELOPMENT_PLAN.md         # 本文件
├── research-proposal.md        # 研究方案
├── src/
│   ├── CMakeLists.txt
│   ├── main.cpp                # 主驱动程序
│   ├── core/
│   │   ├── particle_data.hpp   # SoA 粒子数据结构
│   │   ├── particle_data.cpp
│   │   ├── config.hpp          # 模拟参数配置
│   │   ├── config.cpp
│   │   ├── constants.hpp       # 物理常量和模型参数
│   │   └── types.hpp           # 类型别名和基础定义
│   ├── domain/
│   │   ├── decomposition.hpp   # MPI 区域分解
│   │   ├── decomposition.cpp
│   │   ├── cell_list.hpp       # Cell list 邻居搜索
│   │   ├── cell_list.cpp
│   │   ├── halo_exchange.hpp   # Ghost 粒子交换
│   │   └── halo_exchange.cpp
│   ├── force/
│   │   ├── force_calculator.hpp  # 力计算接口
│   │   ├── lj_force.hpp        # Lennard-Jones 势
│   │   ├── lj_force.cpp
│   │   ├── terrain_force.hpp   # 地形外势
│   │   ├── terrain_force.cpp
│   │   ├── culture_force.hpp   # 文化向量交互力
│   │   └── culture_force.cpp
│   ├── integrator/
│   │   ├── langevin_integrator.hpp   # Langevin 积分器（BBK）
│   │   ├── langevin_integrator.cpp
│   │   ├── jump_process.hpp    # Poisson 跳跃处理
│   │   ├── jump_process.cpp
│   │   ├── rng.hpp             # 随机数生成器封装
│   │   └── rng.cpp
│   ├── interaction/
│   │   ├── resource_exchange.hpp  # 对称资源交换
│   │   ├── resource_exchange.cpp
│   │   ├── culture_dynamics.hpp   # 文化向量演化
│   │   ├── culture_dynamics.cpp
│   │   ├── tech_spread.hpp     # 技术传播
│   │   ├── tech_spread.cpp
│   │   ├── loyalty.hpp         # 忠诚度/叛乱/征服
│   │   └── loyalty.cpp
│   ├── population/
│   │   ├── reproduction.hpp    # 繁殖模型（含性别/婚配）
│   │   ├── reproduction.cpp
│   │   ├── mortality.hpp       # 死亡机制（含寿命派生量）
│   │   ├── mortality.cpp
│   │   ├── inheritance.hpp     # 遗传与变异
│   │   ├── inheritance.cpp
│   │   ├── plague.hpp          # 瘟疫/免疫模型
│   │   └── plague.cpp
│   ├── terrain/
│   │   ├── terrain_loader.hpp  # 地形数据加载
│   │   ├── terrain_loader.cpp
│   │   ├── resource_map.hpp    # 资源产出率 R(x)
│   │   └── resource_map.cpp
│   ├── analysis/
│   │   ├── order_params.hpp    # 序参量计算
│   │   ├── order_params.cpp
│   │   ├── distributions.hpp   # 分布函数（P(w), n(s)等）
│   │   ├── distributions.cpp
│   │   ├── network_analysis.hpp # 交互网络拓扑分析
│   │   ├── network_analysis.cpp
│   │   ├── phase_detector.hpp  # 相变自动检测
│   │   └── phase_detector.cpp
│   └── io/
│       ├── snapshot_writer.hpp # HDF5 快照输出
│       ├── snapshot_writer.cpp
│       ├── timeseries_writer.hpp # 时间序列输出
│       ├── timeseries_writer.cpp
│       ├── ic_loader.hpp      # CSV 初始条件加载器（Phase 28）
│       ├── ic_loader.cpp
│       ├── checkpoint.hpp     # 弹性 checkpoint/restart 系统（Phase 29）
│       └── checkpoint.cpp
├── tests/
│   ├── CMakeLists.txt
│   ├── test_particle_data.cpp
│   ├── test_cell_list.cpp
│   ├── test_lj_force.cpp
│   ├── test_langevin_integrator.cpp
│   ├── test_resource_exchange.cpp
│   ├── test_reproduction.cpp
│   ├── test_order_params.cpp
│   └── test_decomposition.cpp
├── scripts/
│   ├── visualize.py            # 空间可视化
│   ├── plot_timeseries.py      # 序参量时间序列
│   ├── plot_distributions.py   # 分布函数绘图
│   ├── phase_diagram.py        # 相图构建
│   ├── param_scan.py           # 参数空间扫描
│   ├── terrain_compare.py      # 地形对比实验
│   ├── rule_scan.py            # 规则消融扫描（Phase 26）
│   ├── plot_ablation.py        # 消融实验可视化（Phase 26）
│   ├── plot_worldmap.py        # 世界地图可视化（Phase 27）
│   ├── fetch_terrain.py        # 真实地形数据下载/转换（Phase 27）
│   └── generate_genesis.py    # 历史初始条件生成器（Phase 28）
├── data/
│   └── terrain/                # 地形数据存放
└── examples/
    ├── minimal_1k.cfg          # 最小原型配置（1000 agent）
    ├── scan_base.cfg           # 参数扫描基础配置
    ├── adam_eve.csv            # 亚当夏娃初始条件（2 粒子）
    ├── adam_eve.cfg            # 亚当夏娃长期演化配置
    ├── adam_eve_quick.cfg      # 亚当夏娃快速测试配置
    ├── genesis_100k.csv        # 10,000 BCE 历史初始条件（10万 agent）
    └── genesis_100k.cfg        # 创世纪场景完整配置
```

### 1.4 核心类/模块一览


| 模块          | 核心类/函数                    | 职责               | 热点路径？ |
| ----------- | ------------------------- | ---------------- | ----- |
| core        | `ParticleData`            | SoA 数据容器，管理粒子增删  | 否     |
| core        | `Config`                  | 解析配置文件，存储模拟参数    | 否     |
| domain      | `DomainDecomposition`     | MPI 子域划分和粒子迁移    | 否     |
| domain      | `CellList`                | 短程邻居搜索加速         | **是** |
| domain      | `HaloExchange`            | Ghost 粒子 MPI 通信  | 否     |
| force       | `compute_lj_force()`      | LJ 势的力计算         | **是** |
| force       | `compute_terrain_force()` | 地形梯度力            | **是** |
| force       | `compute_culture_force()` | 文化交互力            | **是** |
| integrator  | `LangevinIntegrator`      | BBK 积分 + 随机力     | **是** |
| integrator  | `JumpProcess`             | Poisson 跳跃事件处理   | 否     |
| integrator  | `RNG`                     | 线程/rank 安全的随机数   | **是** |
| interaction | `exchange_resources()`    | 对称资源交换规则         | **是** |
| interaction | `evolve_culture()`        | 文化向量演化           | 中     |
| interaction | `spread_technology()`     | ε 传播             | 中     |
| population  | `try_reproduce()`         | 繁殖条件检查与执行        | 否     |
| population  | `apply_mortality()`       | 四重死亡机制           | 否     |
| population  | `inherit_attributes()`    | 遗传与变异            | 否     |
| interaction | `evolve_loyalty()`        | 忠诚度四项驱动演化        | 中     |
| interaction | `attempt_conquest()`      | 征服（可配置成本/伤亡）     | 否     |
| population  | `compute_lifespan()`      | 寿命派生量 λ_i=h(w,ε) | 否     |
| analysis    | `compute_order_params()`  | Gini, H, F, C 等  | 否     |
| io          | `SnapshotWriter`          | HDF5 输出          | 否     |
| io          | `load_initial_conditions()` | CSV 初始条件加载     | 否     |
| io          | `write_checkpoint()`      | 弹性 checkpoint 写入  | 否     |
| io          | `read_checkpoint()`       | 进程数无关 checkpoint 读取 | 否     |
| io          | `gather_all_particles()`  | 全局粒子收集（快照修复） | 否     |


---

## 二、开发阶段（涌现优先原则）

> 涌现方法论的理论基础 → [[research-proposal#2.6 涌现方法论：对称规则，不对称结果]]

遵循研究方案 §2.6 的"涌现优先"方法论：阶段 1-3 仅使用对称规则，不含任何预设层级机制。

### Phase 0：项目骨架（~1 周）

**目标**：可编译、可运行的空壳项目

- CMakeLists.txt（顶层 + src + tests）
- MPI 初始化/终结
- Config 类：从 TOML/JSON 文件读取参数
- ParticleData 结构：SoA 布局，粒子增删接口
- 基础类型定义（types.hpp, constants.hpp）
- GoogleTest 集成
- 第一个测试：ParticleData 增删粒子
- CI 编译验证

**交付物**：`cmake --build . && ctest` 通过

### Phase 1：空间动力学（~2 周）

**目标**：粒子在 2D 空间中聚集

- CellList：2D cell list 邻居搜索
- LJ 势：短程吸引 + 超短程排斥
- 简单地形势：2D 高斯势阱模拟河谷
- Velocity-Verlet 积分器（无随机力，纯确定性）
- 简单 CSV 输出：每 N 步输出粒子位置
- Python 可视化脚本：画粒子位置
- 测试：LJ 力的对称性、能量守恒、聚集行为

**交付物**：~1000 个粒子在高斯势阱中聚集的动画

### Phase 2：资源交换与不平等涌现（~2 周）

**目标**：验证不平等是否从对称规则中自发涌现

- w_i 自由度：初始均匀分布
- 对称资源交换规则：Δw = η(A_i−A_j)/(A_i+A_j) × min(w_i,w_j)
- 资源消耗：每步 w_i -= consumption
- 资源产出：dw/dt += R(x) × f(ε_i)（ε 固定为常数）
- 生存阈值：w_i < w_survival → 标记死亡
- Gini 系数计算：每步实时计算 G(t)
- 财富分布 P(w) 输出
- 测试：资源守恒（封闭系统）、Gini 单调性

**核心验证**：G(t) 是否从 ~0 自发上升？P(w) 是否从均匀分布变为指数/幂律？

### Phase 3：Langevin 动力学（~2 周）

**目标**：引入耗散和随机力

- BBK 积分器：替换 Velocity-Verlet
- RNG 封装：Mersenne Twister，每个 rank 独立种子
- 高斯白噪声 ξ(t)：施加到位置和财富方程
- 耗散力 −γv：施加到动量方程
- 温度参数 T：可全局、可空间变量
- 涨落-耗散关系验证：⟨ξ²⟩ = 2γkT
- 温度扫描：不同 T 下的 Gini 系数
- 测试：热平衡态的能量分布（Boltzmann 分布）

**核心验证**：温度 T 如何影响不平等的涌现？

### Phase 4：MPI 并行化（~3 周）

**目标**：支持大规模并行计算

- DomainDecomposition：2D 空间域划分
- 粒子-子域映射：粒子属于哪个 rank
- HaloExchange：Ghost 粒子通信（位置、w、ε）
- 粒子迁移：跨域粒子的 MPI_Send/Recv
- CellList 适配：处理 ghost 粒子
- 全局 Gini 计算：MPI_Allreduce
- 全局 P(w) 计算：分布式直方图
- 弱/强扩展性测试
- 测试：并行结果与串行结果一致性（数值容差）

**交付物**：10⁴–10⁵ 粒子的并行模拟

### Phase 5：文化向量与群体涌现（~2 周）

**目标**：验证文化圈边界是否自发涌现

- c⃗_i 自由度：d 维文化向量
- 文化交互力：距离小→吸引，距离大→排斥
- 文化传播：接触时 c⃗ 趋同
- 文化序参量 Q(t)
- 文化空间关联 C_culture(r)
- 可视化：按文化方向着色

**核心验证**：是否自发形成文化圈边界？

### Phase 6：人口动力学（~2 周）

**目标**：引入繁殖、死亡、代际传承

- 生育能力曲线 φ(a)：Beta 分布钟形
- 交配五条件检查
- 妊娠/冷却期状态管理
- 后代属性遗传与变异
- 四重死亡机制：衰老 + 饥饿 + 意外 + 瘟疫（预留）
- 马尔萨斯反馈：人口-资源负反馈
- 人口 N(t) 追踪
- 测试：封闭系统人口稳态、承载力限制

### Phase 7：能量利用与 Poisson 跳跃（~2 周）

**目标**：引入 ε 演化和技术突破

- ε_i 演化：缓慢漂移 + 交互传播
- Poisson 跳跃：ε 的技术突破
- Poisson 跳跃：w 的财富跳跃（正/负）
- ε 的乘性效应：修改生产力、承载力
- 承载力 K(x) = R(x)×f(ε)/consumption
- ⟨ε⟩(t) 追踪
- 测试：ε 跃迁后人口增长加速

### Phase 8：完整分析管线（~2 周）

**目标**：所有序参量的实时计算和输出

- 交互网络构建（事后检测层级）
- 层级深度 H(t)、分支因子 B(t)
- 最大分量比 F(t)、独立实体数 C(t)
- 集群大小分布 n(s)
- 径向分布函数 g(r)
- 阶级流动性 M(t)
- 相变自动检测算法
- HDF5 快照输出
- 完整 Python 后处理脚本集

### Phase 9：高级特性（~3 周）— ✅ 已完成（瘟疫模块）

**目标**：瘟疫、真实地形、层级精细化

- 瘟疫模块：免疫向量 d⃗_i、SIR 传播、差异化打击
- 真实地形加载：SRTM DEM → 势能面
- 层级精细化（仅在涌现确认后）：superior_i + L_ij + Power_i
- 忠诚度演化方程
- 世袭/继承机制
- 相图构建：(T, ε) 参数扫描

### Phase 10：Morton 曲线并行框架（~5 周）

**目标**：用空间填充曲线 (SFC) 替换 Cartesian 分解，支撑 80 亿粒子全球模拟

**设计文档**：`docs/parallel-framework-design.md`

**问题**：全球 80 亿人口分布极不均匀（海洋 0 人，城市 10⁶/km²），Cartesian 均匀切割的负载比可达 500000:1。SFC 将 2D 空间映射到 1D 后均匀切割，每 rank 粒子数严格相等。

**架构**：

```
MPI ranks (64-1024) ← SFC 分解 + 动态重平衡
  └→ CellList (每 rank 局部) ← pair 遍历
      └→ SIMD (力计算内层) ← __restrict__ + 自动向量化
```

#### 10A：SFC 基础设施（~2 周）

- Morton key 2D 编码/解码（bit interleave）
- `SFCDecomposition` 类替换 `DomainDecomposition`
- 粒子按 Morton key 并行排序
- 全局直方图法计算分割点（MPI_Allgather）
- 测试：编码往返正确性、排序后空间局域性

#### 10B：SFC 通信（~2 周）

- 粒子重分配（MPI_Alltoallv）
- 邻居发现（bounding box 扩展法）
- 非结构化 Halo 交换
- 积分器边界条件改为迁移（不反射）
- 并行一致性测试：SFC 结果 vs 串行结果

#### 10C：动态负载均衡 + 性能监控（~1 周） ✅

- PerfMonitor 类：9 阶段分段计时（Dynamics/Exchange/Culture/Technology/Resources/Population/Migration/Analysis/IO）
- 负载监控：step_compute()（排除 IO）+ MPI_Allreduce max/min/avg
- 负载效率指标：efficiency = avg_time / max_time
- LoadReport 结构：needs_rebalance 标志、粒子分布统计
- 自动触发重平衡（efficiency < 50% 时，最小间隔 50 步防止抖动）
- 重平衡后 CellList + SFC 重建
- format_report() + format_breakdown() 格式化输出
- MPI_Initialized 守卫：单元测试无需 MPI_Init
- 8 个单元测试（PerfMonitorTest）全部通过
- MPI 4 进程验证：计算效率 ~97-99%
- weak/strong scaling 测试框架 + 工作站级验证
  - Strong scaling (N=8000, P=1→4): speedup 1.0→1.65x, eff=41-100%
  - Weak scaling (N/P=4000, P=1→4): eff=45-100%
  - 负载均衡效率 97%+，效率瓶颈为小规模下的通信占比
  - 大规模集群验证（10⁵+ 粒子，待 HPC 资源）

### Phase 11：真实地形 + 参数扫描（~2 周） ✅

**目标**：引入真实地理数据，构建制度相图

- TerrainGrid 类：ESRI ASCII Grid (.asc) 加载
- TerrainGrid：raw binary float64 加载
- generate_synthetic() 合成地形（valley/ridge/flat）用于测试
- 双线性插值 elevation(x,y)
- 中心差分梯度 gradient(x,y)
- 高程 → 势能转换 potential() 和 force()
- compute_grid_terrain_forces() 批量力计算
- grid_terrain_potential() 资源产出地形因子
- 配置系统：terrain_file / terrain_format / terrain_scale / terrain_type
- main.cpp 集成：terrain_type="grid" 时用 DEM，否则用 Gaussian wells
- RiverField：独立河流 proximity 场（程序化/ASCII/Binary）
- 河流耦合：资源产出 / 承载力 / 交换 / 技术传播 / 可选瘟疫增强与弱引导力
- 14 个地形加载器单元测试全部通过
- param_scan.py：(T, scale) 参数空间扫描脚本
- plot_phase_diagram.py：相图绘制（6 面板 heatmap）
- scan_base.cfg 扫描基础配置
- 92 个单元测试全部通过

### Phase 12：MPI+OpenMP 混合并行（~3 周） ✅

**目标**：在每个 MPI rank 内部引入 OpenMP 线程级并行，加速热点路径

- CMake：`POLITEIA_USE_OPENMP` 选项 + `find_package(OpenMP)`
- LangevinIntegrator：半步动量更新（线程私有 RNG）、位置更新、边界反射、动能求和
- compute_social_forces()：per-particle 邻居遍历（无 Newton 第三定律，消除写竞争，PE×0.5 修正）
- CellList::for_neighbors_of()：单粒子邻居查找模板（OpenMP 友好）
- compute_terrain_forces()：OpenMP parallel for + reduction
- compute_grid_terrain_forces()：OpenMP parallel for + reduction
- apply_resource_dynamics()：OpenMP parallel for
- apply_survival_threshold()：OpenMP parallel for + reduction
- advance_age()：OpenMP parallel for
- apply_mortality()：线程私有 RNG + reduction
- 非 OpenMP 模式下抑制 `-Wunknown-pragmas`
- 所有 `#pragma omp` 使用 `if(n > 256)` 门槛避免小规模开销
- 92 个单元测试全部通过
- MPI 2-proc + OMP 2-thread 混合模式验证通过

### Phase 13：忠诚度与层级精细化（~2 周） ✅

**目标**：实现研究方案§2.3"阶段4"——在已涌现的层级基础上引入显式依附关系和忠诚度权重

**核心实现**：

1. **ParticleData 扩展**
  - 添加 `superior_i` 依附指针（Id 类型，-1 = 独立根节点）
  - 添加 `loyalty_i` 忠诚度权重（Real ∈ [0,1]）
  - `compact_with_map()` 方法：compact 时生成 old→new 索引映射
  - `repair_superior_after_compact()` 函数：修复 compact 后的悬空指针
2. **依附形成（`form_attachments`）**
  - 从 InteractionNetwork 的支配图（dominance graph）检测稳定单向资源流
  - 仅对无上级的根节点建立新依附（避免循环和自环）
  - 初始忠诚度 = 0.5
3. **忠诚度演化（`evolve_loyalty`）**
  - 四项驱动：保护收益(+α)、税收消耗(-β)、文化距离惩罚(-γ)、随机噪声(η)
  - 死亡上级自动检测并断裂链接
  - L_ij ∈ [0,1] 钳位
4. **忠诚度事件（`process_loyalty_events`）**
  - L < rebel_threshold → 叛乱（断裂依附，成为独立根节点）
  - L < switch_threshold → 投靠（搜索附近更强的根节点并转移依附）
5. **税收与保护（`apply_taxation`）**
  - 上级从下属提取 tax_rate 比例的财富
  - 税收上限 50%（防止单步抽干）
6. **有效权力（`compute_effective_power`）**
  - Power_i = Σ_{j ∈ subtree(i)} w_j × L_path(i,j)
  - 沿依附链向上追溯，累乘忠诚度
  - MAX_DEPTH=100 防止循环引用
7. **征服（`attempt_conquest`）**
  - 仅根节点可发起征服
  - Power_i > 1.5 × Power_j 时有概率征服
  - 被征服者忠诚度初始化为 0.3（低于自愿依附）
8. **主循环集成**
  - 每步执行忠诚度演化、叛乱/投靠、税收
  - 每 network_window 步执行依附形成和征服
  - 输出新指标：⟨L⟩、n_attached、Gini(Power)
  - compact 时使用 compact_with_map + repair_superior_after_compact

**验证**：

- 10 个忠诚度单元测试全部通过（共 102 个测试）
- 1000 粒子集成测试验证：忠诚度 ~0.78-0.90，权力 Gini ~0.93-0.98

### Phase 14：世袭继承与代际传承（~1 周） ✅

**目标**：实现研究方案"阶段5+"中的世袭机制——领主死亡时权力传承、遗产分配、新生儿层级继承

**核心实现**：

1. **世袭继承（`process_succession`）**
  - 领主死亡时收集所有直属下属
  - 选择继承者：(wealth × loyalty) 最高者
  - 继承者接管死者的上级关系（或成为新的独立根节点）
  - 其余下属转移依附到继承者，忠诚度冲击（×0.7）
  - 遗产分配：继承者得 50%，其余下属均分 50%
2. **新生儿层级继承（`inherit_hierarchy`）**
  - 子女继承父母的 superior（同一领主/部落）
  - 若父母是领主（有下属），子女自动依附父母
  - 初始忠诚度继承自父母（×0.9，上限 0.8）
3. **主循环集成**
  - 死亡后、compact 前扫描死者并执行世袭
  - 繁殖时自动调用 `inherit_hierarchy`

**验证**：

- 6 个新单元测试通过（共 108 个测试）
- 集成测试：世袭使忠诚度更稳定（⟨L⟩ 峰值 0.94 vs Phase 13 的 0.90）

### Phase 15：显式层级分析（~0.5 周） ✅

**目标**：修复 H, C, F, Ψ 序参量——从显式 superior_i 拓扑计算，替代旧的推断式分析

**问题**：Phase 13 引入了 superior_i 显式层级，但层级分析指标（H, C, F, Ψ）仍然从 InteractionNetwork 的推断式支配图计算。导致 H=0, C=N，完全无法反映真实层级。

**解决方案**：

- 新增 `build_dominator_from_superior()`：直接从 ParticleData.superior_i 构建 dominator 向量
- 更新 main.cpp 输出：使用显式拓扑替代推断式分析
- 2 个新单元测试（共 110 个），验证层级深度、组件数等

**验证结果**（1000 粒子 / 10000 步）：


| 指标  | 修复前    | 修复后       | 含义                    |
| --- | ------ | --------- | --------------------- |
| H   | 0      | 5-7       | 层级深度：从无到5-7层          |
| C   | =N     | 110-254   | 独立政体数：涌现出110-254个"国家" |
| F   | ~0.001 | 0.03-0.10 | 最大帝国规模：占总人口3-10%      |
| Ψ   | 0      | 0.52-0.69 | 封建化程度：中等封建结构          |


### Phase 17：Scaling 测试框架（~0.5 周） ✅

**目标**：建立自动化的 weak/strong scaling 测试框架，完成工作站级验证

**工具**：

- `scripts/scaling_test.py`：自动化 scaling 测试（配置生成 → 多次运行 → 取中位数 → CSV）
- `scripts/plot_scaling.py`：3面板 scaling 结果可视化（speedup 曲线 + 效率柱状图）

**工作站级测试结果**（MPI+OpenMP, OMP_NUM_THREADS=2）：


| 类型              | P=1         | P=2        | P=4        | 备注         |
| --------------- | ----------- | ---------- | ---------- | ---------- |
| Strong (N=8000) | 2.0s (100%) | 1.5s (66%) | 1.2s (41%) | 小规模通信占比高   |
| Weak (N/P=4000) | 1.1s (100%) | 1.5s (69%) | 2.3s (45%) | 同上         |
| 负载均衡效率          | 100%        | 97%        | 97%        | SFC 分解工作良好 |


**分析**：

- 负载均衡效率 97%+ 表明 Morton Z-curve 分解本身非常有效
- 并行效率受限于小规模下的通信/计算比
- 预期 10⁵+ 粒子规模下效率将显著提升（Amdahl's law: 计算占比增大）

---

## 三、时间估算


| 阶段       | 内容               | 预估时间      | 依赖       | 状态   |
| -------- | ---------------- | --------- | -------- | ---- |
| Phase 0  | 项目骨架             | 1 周       | 无        | ✅ 完成 |
| Phase 1  | 空间动力学 + Langevin | 2 周       | Phase 0  | ✅ 完成 |
| Phase 2  | 资源交换             | 2 周       | Phase 1  | ✅ 完成 |
| Phase 3  | 人口动力学            | 2 周       | Phase 2  | ✅ 完成 |
| Phase 4  | 文化向量             | 2 周       | Phase 3  | ✅ 完成 |
| Phase 5  | ε 与 Poisson 跳跃   | 2 周       | Phase 4  | ✅ 完成 |
| Phase 6  | 交互网络分析           | 2 周       | Phase 5  | ✅ 完成 |
| Phase 7  | MPI 并行化          | 3 周       | Phase 6  | ✅ 完成 |
| Phase 8  | 可视化 + 分析脚本       | 1 周       | Phase 7  | ✅ 完成 |
| Phase 9  | 瘟疫模块             | 2 周       | Phase 8  | ✅ 完成 |
| Phase 10 | Morton 曲线并行框架    | 5 周       | Phase 7  | ✅ 完成 |
| Phase 11 | 真实地形 + 相图        | 2 周       | Phase 9  | ✅ 完成 |
| Phase 12 | MPI+OpenMP 混合并行  | 3 周       | Phase 10 | ✅ 完成 |
| Phase 13 | 忠诚度与层级精细化        | 2 周       | Phase 6  | ✅ 完成 |
| Phase 14 | 世袭继承与代际传承        | 1 周       | Phase 13 | ✅ 完成 |
| Phase 15 | 显式层级分析           | 0.5 周     | Phase 14 | ✅ 完成 |
| Phase 16 | 可视化更新            | 0.5 周     | Phase 15 | ✅ 完成 |
| Phase 17 | Scaling 测试框架     | 0.5 周     | Phase 12 | ✅ 完成 |
| Phase 18 | 数据输出增强           | 0.5 周     | Phase 15 | ✅ 完成 |
| Phase 19 | 合成地形与文明场景        | 1 周       | Phase 11 | ✅ 完成 |
| Phase 20 | 全局 ID 与 MPI 层级修复 | 0.5 周     | Phase 14 | ✅ 完成 |
| Phase 21 | 政体检测与文明统计        | 0.5 周     | Phase 15 | ✅ 完成 |
| Phase 22 | 相图扫描与相变检测        | 0.5 周     | Phase 21 | ✅ 完成 |
| Phase 23 | 密度承载力与马尔萨斯反馈     | 0.5 周     | Phase 22 | ✅ 完成 |
| Phase 24 | 地形对比实验与文明分析      | 0.5 周     | Phase 23 | ✅ 完成 |
| Phase 25 | 中国vs欧洲地形对比       | 0.5 周     | Phase 24 | ✅ 完成 |
| Phase 26 | 可配置实验框架          | 3 周       | Phase 25 | ✅ 完成 |
| Phase 27 | 世界地图可视化与真实地形工具   | 0.5 周     | Phase 26 | ✅ 完成 |
| Phase 28 | 初始条件加载器与创世纪场景   | 0.5 周     | Phase 26 | ✅ 完成 |
| Phase 29 | 弹性 Checkpoint/Restart   | 1 周       | Phase 28 | ✅ 完成 |
| Phase 30 | HYDE 3.3 校准与算例体系    | 0.5 周     | Phase 28 | ✅ 完成 |
| **合计**   |                  | **~44 周** |          |      |


Phase 10 是大规模计算的关键路径，必须在扩大到 10⁵+ 粒子前完成。
Phase 11 可与 Phase 10 并行开发。
Phase 12（OpenMP 线程级并行）在 MPI 框架稳定后实施。
Phase 13 对应研究方案"第二期"：在涌现被确认后引入显式层级机制。
Phase 14 实现"阶段5+"的世袭机制：领主继承、遗产分配、代际层级传承。
Phase 15 修复层级分析：使用显式 superior_i 拓扑替代推断式支配图。
Phase 16 可视化更新：12面板时间序列图 + 9面板相图。
Phase 17 Scaling 测试：weak/strong scaling 框架 + 工作站级验证。
Phase 28 初始条件加载器与创世纪场景：CSV 初始条件加载器（ic_loader.hpp/cpp）、亚当夏娃模式（2 粒子起始）、generate_genesis.py（基于 HYDE 3.3 考古数据的历史人口种子生成，支持 10,000 BCE 和 70,000 BCE 两个纪元，29 个区域聚落）、genesis_100k 全球 10 万 agent 场景。
Phase 18 数据输出增强：全粒子快照 CSV + 序参量时序 CSV + 可视化脚本。
Phase 19 合成地形与文明场景：river/basins/continent 合成地形、可配置参数（base_production/max_fertility/tax_rate）、河谷文明演示。
Phase 20 全局 ID 与 MPI 层级修复：每个粒子添加全局唯一 ID（global_id），superior 改存全局 ID 而非本地索引，MPI 打包/解包包含 gid/superior/loyalty，迁移后重建 gid_map，彻底修复多进程层级崩溃问题。
Phase 21 政体检测与文明统计：自动检测层级树连通分量为"政体"，分类为 band/tribe/chiefdom/state/empire，追踪形成/合并/分裂/崩溃事件，输出 polity_summary.csv + polity_events.csv + 政体快照 + 可视化脚本。
Phase 22 相图扫描与相变检测：序参量相变自动检测（滑动窗口变化率+方差），param_scan.py 升级支持政体统计和 regime 分类，plot_phase_diagram.py 6面板相图，2×2 参数扫描验证通过。
Phase 23 密度承载力与马尔萨斯反馈：局部密度 ρ(x) 估计（CellList 邻居计数）、承载力 K(x) = carrying_capacity_base × max(0, −V(x))、密度抑制因子 max(0, 1−ρ/K) 作用于生育率和人均产出、周期性缓存（每 10 步更新一次避免性能瓶颈）、CellList 初始化使用 max(interaction_range, density_radius) 保证邻居搜索完整性、6 个单元测试通过、2×2 参数扫描验证人口稳态且产生差异化政治体制。
Phase 24 地形对比实验与文明涌现分析：terrain_compare.py 多地形对比脚本（river/basins/continent/gaussian 4 种地形 × 同参数）、plot_terrain_compare.py 4×4 面板综合可视化（地形高程图、人口+政体空间分布、序参量对比柱状图、政体类型分布）、terrain_compare.cfg 对比实验配置。初步科学发现：河谷地形产生最深层级(H=5)和最大HHI集中度(0.08)，高斯单中心产生最多碎片化政体(30个)但最浅层级(H=3)，验证了"地理约束驱动政治集中化"假说。
Phase 25 中国vs欧洲地形对比实验：新增 china（大平原+黄河+长江）和 europe（阿尔卑斯+比利牛斯+喀尔巴阡山脉分割6个盆地）合成地形。6 地形全对比实验验证核心假说：中国地形产生最深层级(H=7)、较少政体(15个)、较高HHI(0.088)；欧洲地形产生最多政体(27个)、较浅层级(H=5)、最低HHI(0.052)。山脉屏障阻止政体扩张→碎裂化，开放平原允许兼并→集中化。Gini不平等在所有地形中恒定(~0.89)——不平等是对称规则的内在结果而非地理决定。
Phase 26 可配置实验框架：全参数配置化（§26A）、模块开关消融（§26B）、寿命派生量（§26C）、性别与婚配制度（§26D）、战争增强模块（§26E）、消融实验脚本（§26F）。对应研究方案 §9.6"可配置实验框架：规则空间的系统搜索"。
Phase 27 世界地图可视化与真实地形工具：plot_worldmap.py（交互式 Plotly 地图 + 静态 Matplotlib 地形地图 + 快照动画）、fetch_terrain.py（ETOPO1 高程数据下载 + 程序化地形生成 + ESRI ASCII Grid 导出 + Politeia 配置生成）。支持 9 个预定义地理区域（全球/中国/欧洲/地中海/美索不达米亚/尼罗河/印度河/东亚/旧大陆）、8 种着色模式（财富/ε/层级/忠诚/年龄/文化/权力/政体）。
Phase 28 初始条件加载器与创世纪场景：ic_loader.hpp/cpp（CSV 初始条件加载器，支持 x,y 必填 + w/eps/age/sex/culture 可选列）、initial_conditions_file 配置参数、亚当夏娃模式（2 粒子起始演化）、generate_genesis.py（基于 HYDE 3.3 考古人口数据生成历史初始条件，支持 10,000 BCE 和 70,000 BCE 两个纪元，29 个区域聚落）、genesis_100k.csv（10 万 agent 全球分布）+ genesis_100k.cfg（5000 年演化配置，含分阶段运行策略）。
Phase 29 弹性 Checkpoint/Restart：进程数无关的二进制 checkpoint 文件格式（128B 固定头 + 配置块 + 粒子数据块），支持 N 进程写 → M 进程读的弹性扩缩容（如 4 进程写 → 400 进程读），Gather-to-Root（≤10M 粒子）和 MPI-IO（>10M 粒子）双策略自动切换写入，`--restart` CLI 参数 + SFC 重分配读取，`gather_all_particles()` 修复快照仅写 rank 0 的 bug。
Phase 30 HYDE 3.3 校准与算例体系：使用 HYDE 3.3 (Klein Goldewijk et al. 2023) 国家级人口数据精确校准 10,000 BCE 区域分布（全球 4,501,152 人），大洲占比精确匹配（北美 26.3%、南美 24.4%、亚洲 26.3%、欧洲 10.7%、大洋洲 7.2%、非洲 5.1%）；建立标准算例体系（CASES.md），定义命名规则 `<scenario>_<calibration>_<scale>`；主算例 genesis_hyde_100k（29 区域 × 100K agent）；更新研究方案 §9.5.1 初始条件与人口校准。
Phase 31 TerrainGrid + RiverField 环境分层：新增 `src/river/river_field.hpp/cpp`，将河流从粗 DEM 中拆出为独立 `RiverField`；支持 procedural / file / binary 三种加载方式（第一版以单波段 proximity 为主，`discharge` 预留接口）；新增 `river_*` 配置项；主循环缓存 `river_proximity_at_particle`；耦合到资源产出、承载力、资源交换、技术传播，并补充可选的近河瘟疫增强与弱河道引导力；新增 `scripts/fetch_rivers.py` 与示例 `riverfield_global_snippet.cfg`；对应研究方案 §5.7.2 与 §9.3 的“河流走廊场”设计。

### Phase 26：可配置实验框架（~3 周）

> 理论基础 → [[research-proposal#9.6 可配置实验框架：规则空间的系统搜索]]
> 全部随机系数 → [[docs/stochastic-distributions]]

**目标**：将所有机制模块化、参数化，支持规则空间的系统搜索（研究方案 §9.6）

**动机**：模型中的每条交互规则本质上是一个可证伪的假说。需要通过消融实验和参数扫描确定哪些规则是文明演化的关键驱动力。

#### 26A：全参数配置化（~1 周）

将当前硬编码在各 `Params` 结构体中的参数暴露到配置文件：

- **资源交换**：`exchange_rate`、`exchange_cutoff`
- **文化动力学**：`assimilation_rate`、`repulsion_threshold`、`repulsion_strength`、`attraction_strength`、`culture_mate_threshold`
- **技术演化**：`drift_rate`、`spread_rate`、`jump_base_rate`、`jump_magnitude`、`wealth_jump_rate_pos/neg`、`wealth_jump_fraction`
- **繁殖**：`peak_fertility_age`、`mate_range`、`wealth_birth_cost`、`min_wealth_to_breed`、`mutation_strength`
- **死亡**：`gompertz_alpha`、`max_age_base`
- **忠诚度**：`protection_gain`、`tax_drain`、`culture_penalty`、`noise_sigma`、`rebel_threshold`、`switch_threshold`、`attachment_threshold`、`initial_loyalty`
- **征服**：`power_ratio_threshold`、`base_probability`、`initial_loyalty`（被征服者）
- **瘟疫**：`n_pathogens`、`trigger_density`、`trigger_rate`、`infection_radius`、`infection_rate`、`base_mortality`、`recovery_time`、`immunity_inheritance`
- **控制**：`random_seed`、`network_window_factor`、`density_update_interval`
- 更新 `config.hpp/cpp`：在 `SimConfig` 中添加所有新字段和 `apply_key_value` 解析

#### 26B：模块开关系统（~0.5 周）

为每个机制模块添加 `enabled` 开关，支持消融实验：

- `culture_enabled`：文化动力学开关
- `technology_enabled`：技术演化开关
- `loyalty_enabled`：忠诚度/层级系统开关
- `conquest_enabled`：征服机制开关
- `plague_enabled`：瘟疫模块开关
- `carrying_capacity_enabled`：承载力限制开关
- `reproduction_enabled`：繁殖开关
- 在 `main.cpp` 中用 `if (cfg.xxx_enabled)` 条件包裹对应调用

#### 26C：寿命派生量（~0.5 周）

实现研究方案 §2.3 的有效寿命 λ_i = h(w_i, ε_local)：

- `lifespan_wealth_coupling`：财富-寿命耦合开关
- `lifespan_tech_coupling`：技术-寿命耦合开关
- `max_age_base`：基础最大年龄（原始社会 ~50）
- `gompertz_beta_base`：原始衰老加速（~0.12）
- `a_max(i) = a_base + k_w·min(w/w_ref, 1) + k_ε·log(1 + ε/ε_ref)`
- `β_eff(i) = β₀ / (1 + α_w·w/w_ref + α_ε·ε/ε_ref)`
- 修改 `apply_mortality()`：Gompertz 参数从全局常数变为个体函数
- 新增涌现观测量：⟨a_death⟩(t)、max(a_death)(t)、G_life(t)
- 单元测试：寿命与财富/ε 的正相关

#### 26D：性别与婚配制度（~1 周）

实现研究方案 §2.3（性别参数）和 §2.5.2-2.5.5（婚配与继承）：

- **ParticleData 扩展**：添加 `sex` 字段（uint8_t），`add_particle()` 时随机赋值
- `**gender.enabled` 开关**：关闭时退回无性别对称模型
- **性别非对称冷却期**：女性 T_cool_f = T_gest + T_nurse，男性 T_cool_m（可配置，默认极短）
- **交配条件 2（性别互补）**：启用性别时要求 g_i ≠ g_j
- **生育窗口性别化**：女性 [puberty, menopause]，男性 [puberty, max_age]
- **多偶制约束**：`max_partners_per_cooldown`（0=无限制，1=一夫一妻，N=有限多偶）
- **多偶财富门槛**：`partner_wealth_factor`（第 k 个配偶需 w > k × factor × w_birth）
- **继承方向模型**：
  - `contribution`：按父母 w×ε 贡献比例加权（母系→父系自然涌现）
  - `matrilineal`/`patrilineal`/`equal`：固定权重
  - `epsilon_switch`：ε 阈值触发转变
- 更新 `inherit_hierarchy()`：继承方向按配置模式决定
- 更新 `reproduction.cpp`：所有繁殖逻辑适配性别
- MPI 打包/解包包含 `sex` 字段
- 单元测试：性别比、冷却期非对称、多偶制约束

#### 26E：战争增强模块（~0.5 周）

实现研究方案 §9.6.2 (M) 征服与战争增强：

- **战争成本**（`war_cost.enabled`）：征服方消耗财富、被征服方损失财富
- **战争伤亡**（`war_casualties.enabled`）：攻守双方子树按比例人口损失
- **掠夺**（`pillage.enabled`）：征服时从被征服方转移财富
- **威慑**（`deterrence.enabled`）：Power 压倒性优势时弱者主动依附
- **联盟**（`alliance.enabled`）：文化距离近 + 共同威胁时 Power 共享（涉及新数据结构，可延后）
- 单元测试：战争成本/伤亡/掠夺的正确性

#### 26F：消融实验脚本（~0.5 周）

- `rule_scan.py`：自动生成不同规则组合的配置文件，批量运行，收集序参量
- `plot_ablation.py`：消融实验热图（规则组合 × 稳态序参量矩阵）
- 示例消融实验配置：A0-A6（模块消融）、B1-B12（增强模块消融）

**验证**：

- 全参数配置化后，所有现有 .cfg 仍能正确运行（向后兼容）
- 模块开关全部关闭 → 最小模型仅含空间动力学+资源交换
- 消融实验至少完成 A0-A6 基准对比
- 寿命涌现：初始 ⟨a_death⟩ ≈ 35，高 ε 后 ⟨a_death⟩ 显著上升
- 性别涌现：gender=true 时一夫多妻从财富分化中自然涌现

---

## 四、技术决策记录

### 4.1 为什么选 SoA 而非 AoS？

- 力计算热点路径中需要遍历所有粒子的位置 → 连续内存访问
- SIMD 向量化要求同类型数据连续存储
- MPI 通信时可以直接发送连续缓冲区

### 4.2 为什么选 Cell List 而非 Verlet List？

- Cell List 更新代价 O(N)，Verlet List 构建 O(N²)
- Cell List 天然适配 MPI 区域分解（每个子域独立维护 cell）
- 对于长时间模拟中粒子大量移动的场景（迁徙），Cell List 不需要 skin 参数

### 4.3 为什么选 BBK 积分器？

- BBK (Brünger-Brooks-Karplus) 是 Langevin 方程标准的二阶积分器
- 严格满足涨落-耗散关系
- 实现简单，与 Velocity-Verlet 结构相似

### 4.4 随机数策略

- 每个 MPI rank 使用独立的 RNG 实例
- 种子 = base_seed + rank_id × large_prime
- 使用 xoshiro256** 或 Mersenne Twister
- Poisson 跳跃使用指数分布生成等待时间

### 4.5 粒子增删策略

- 预分配大容量（capacity >> count）
- 新粒子填入 count 位置，count++
- 死亡粒子标记 alive[i] = 0，定期压缩（移除空洞）
- 压缩频率远低于时间步频率，避免频繁内存操作

---

## 五、热点路径清单

以下函数位于每步时间循环的内层，必须遵循 HPC 内核规则（modern-cpp-agent-rules §7.D）：


| 函数                           | 预估调用频率         | 关键约束                     | OpenMP            |
| ---------------------------- | -------------- | ------------------------ | ----------------- |
| `compute_social_forces()`    | 每步 × 每粒子 × 邻居数 | 无堆分配、无虚调用、`__restrict`__ | ✅ per-particle    |
| `compute_terrain_forces()`   | 每步 × 每粒子       | 查表插值，连续访存                | ✅ parallel for    |
| `exchange_resources()`       | 每步 × 每交互对      | 对称规则，无分支                 | ✅ production loop |
| `LangevinIntegrator::step()` | 每步 × 每粒子       | BBK 公式，RNG 调用            | ✅ 线程私有 RNG        |
| `CellList::build()`          | 每步             | O(N) 桶排序                 | 串行（O(N)）          |
| `evolve_culture()`           | 每步 × 每交互对      | 向量点积，距离计算                | 串行                |
| `advance_age()`              | 每步 × 每粒子       | 确定性 da/dt=1              | ✅ parallel for    |
| `apply_mortality()`          | 每步 × 每粒子       | 4 种死亡机制 + 个体寿命，RNG 调用    | ✅ 线程私有 RNG        |


---

## 六、测试策略

> 物理背景 → [[research-proposal#十、潜在风险与应对]]

### 6.1 单元测试（Phase 0-3 起）


| 测试                         | 验证内容              |
| -------------------------- | ----------------- |
| `test_particle_data`       | SoA 增删、容量管理、压缩正确性 |
| `test_cell_list`           | 邻居搜索完整性和对称性       |
| `test_social_force`        | 人际力的牛顿第三定律、截断距离   |
| `test_langevin_integrator` | 热平衡态 Boltzmann 分布 |
| `test_resource_exchange`   | 规则对称性、资源守恒        |
| `test_reproduction`        | 条件检查、冷却期、遗传正确性    |
| `test_order_params`        | Gini 系数已知分布的解析值   |
| `test_rng`                 | 分布均匀性、rank 间独立性   |
| `test_loyalty`             | 忠诚度演化、叛乱/投靠/征服    |
| `test_config_full`         | 全参数配置化向后兼容        |
| `test_lifespan`            | 寿命派生量与财富/ε正相关     |
| `test_gender_mating`       | 性别比、冷却期非对称、多偶制    |


### 6.2 并行测试（Phase 4 起）


| 测试                          | 验证内容                      |
| --------------------------- | ------------------------- |
| `test_decomposition`        | 域划分无重叠无遗漏                 |
| `test_halo_exchange`        | Ghost 粒子与源粒子一致            |
| `test_parallel_consistency` | 1 rank vs N rank 结果在容差内一致 |


### 6.3 物理验证（贯穿所有阶段）


| 验证            | 预期结果                  |
| ------------- | --------------------- |
| 封闭系统能量守恒（无耗散） | 总能量波动 < 1e-6          |
| 热平衡态动能分布      | 符合 Boltzmann 分布       |
| 封闭系统资源守恒      | Σw_i = const          |
| Gini 系数自发上升   | G(0) ≈ 0 → G(t) > 0.3 |
| 马尔萨斯人口稳态      | N(t) → K(x) 附近波动      |


---

## 七、第一步行动

开发从 Phase 0 开始。首先创建：

1. 顶层 `CMakeLists.txt`
2. `src/CMakeLists.txt` + `tests/CMakeLists.txt`
3. `src/core/types.hpp` — 基础类型定义
4. `src/core/particle_data.hpp/cpp` — SoA 数据容器
5. `tests/test_particle_data.cpp` — 第一个测试
6. `src/main.cpp` — MPI 初始化/终结的空壳

确认 `cmake --build . && ctest` 全部通过后，进入 Phase 1。

---

### Phase 27：世界地图可视化与真实地形工具（~0.5 周）✅ 完成

> 将仿真结果叠加到真实世界地图上，让文明演化的空间分布直观可见。

#### 27A：`plot_worldmap.py` — 世界地图可视化

**三种渲染模式**：

1. **交互式 HTML 地图**（默认）：Plotly Scattergeo，带海岸线/河流/国界底图
2. **静态 PNG 地图**：Matplotlib + 程序化地形背景
3. **动画**：逐帧播放所有快照的 HTML 动画（含播放/暂停/进度条）

**着色模式**：`wealth` / `epsilon` / `hierarchy` / `loyalty` / `age` / `culture` / `power` / `polity`

**地理区域**：`global` / `china` / `europe` / `mediterranean` / `mesopotamia` / `nile` / `indus` / `eastasia` / `oldworld`

**坐标映射**：仿真 `[xmin,xmax]×[ymin,ymax]` 线性映射到地理 `[lon_min,lon_max]×[lat_min,lat_max]`

**政体叠加**：自动检测同目录 `polities_*.csv`，在地图上叠加政体中心（菱形标记，按类型着色，大小 ∝ 人口）

```bash
python plot_worldmap.py output/ --region china --color wealth
python plot_worldmap.py output/ --static --save map.png
python plot_worldmap.py output/ --animate --save civilization.html
```

#### 27B：`fetch_terrain.py` — 真实地形数据获取

**数据源**：NOAA ETOPO1 全球地形数据（公共域，HTTP 下载）

**输出格式**：ESRI ASCII Grid (`.asc`)，可直接被 `TerrainGrid::load_ascii()` 读取

**功能**：

- 从 NOAA ERDDAP 下载指定区域高程数据
- 程序化地形生成（无需网络的备选方案）
- 高程 → 势能转换（低地吸引、山脉排斥、海洋屏障）
- 自动生成对应的 `.cfg` 配置文件
- 支持二进制格式导出（`load_binary()` 兼容）

```bash
python fetch_terrain.py --region china --output terrain_china.asc
python fetch_terrain.py --region europe --procedural --output terrain_europe.asc
python fetch_terrain.py --bbox 73 135 18 54 --resolution 512 --output custom.asc
```

**典型工作流**：

```bash
# 1. 获取中国地形
python scripts/fetch_terrain.py --region china --output data/terrain/china.asc

# 2. 将生成的 terrain_china.cfg 合并到你的仿真配置

# 3. 运行仿真
./politeia china_sim.cfg

# 4. 在世界地图上可视化结果
python scripts/plot_worldmap.py output/ --region china --domain 73 135 18 54
```

#### 27C：`fetch_rivers.py` — 河流走廊场生成

**定位**：把“河流”从粗 DEM 中拆出来，单独生成 `RiverField` 所需的 proximity 栅格。

**当前能力**：

- procedural major-rivers / nile / mesopotamia / china / europe / indus
- 输出 ESRI ASCII 单波段 proximity
- 可选 raw float64 binary
- 自动生成 `river_*` cfg snippet

```bash
python scripts/fetch_rivers.py --region global --output river_global.asc --cfg-snippet
python scripts/fetch_rivers.py --region china --type china --resolution 256 --output river_china.asc
python scripts/fetch_rivers.py --region nile --type nile --output river_nile.asc
```

**典型工作流**：

```bash
# 1. 生成河流 proximity 场
python scripts/fetch_rivers.py --region china --type china --output data/terrain/river_china.asc --cfg-snippet

# 2. 将生成的 river_china.cfg_snippet 合并到你的仿真配置

# 3. 运行仿真（与 terrain/climate 并行使用）
./politeia china_sim.cfg
```

---

### Phase 28：初始条件加载器与创世纪场景（~0.5 周）✅ 完成

> 支持从 CSV 文件加载自定义初始粒子配置，并提供基于考古人口数据的历史场景生成工具。

#### 28A：CSV 初始条件加载器

**核心实现**：

- `io/ic_loader.hpp/cpp`：CSV 初始条件加载器
  - 必填列：`x, y`（空间位置）
  - 可选列：`w`（财富）、`eps`（ε）、`age`（年龄）、`sex`（性别）、`c0, c1, ...`（文化向量分量）
  - 未提供的可选列使用默认值（`SimConfig` 中的初始值或随机分布）
  - 仅 rank 0 执行加载（MPI 兼容）
- `config.hpp/cpp`：新增 `initial_conditions_file` 参数
- `main.cpp`：初始化分支——若配置了 IC 文件则从 CSV 加载，否则使用网格初始化

```ini
initial_conditions_file = examples/adam_eve.csv
initial_particles = 2
```

#### 28B：亚当夏娃模式（最小种群起始）

**目的**：验证模型能否从最小种群（2 个体）通过繁殖演化到大规模人口。

**文件**：

- `examples/adam_eve.csv`：2 个粒子的初始条件（指定位置、财富、ε、年龄、性别、文化向量）
- `examples/adam_eve.cfg`：长期演化配置（500,000 步 = 5,000 年），高生育参数
- `examples/adam_eve_quick.cfg`：快速测试配置（5,000 步 = 50 年）

```csv
x,y,w,eps,age,sex,c0,c1
50.0,50.0,10.0,1.0,20.0,1,1.0,0.0
51.0,50.0,10.0,1.0,18.0,0,0.9,0.1
```

#### 28C：历史创世纪场景（考古人口分布）

**目的**：基于考古人口学数据生成大规模历史初始条件，支持从原始社会开始的千年尺度模拟。

**数据基础**：

- HYDE 3.3 历史人口数据库
- McEvedy & Jones (1978) 区域人口估计
- Biraben (1979) 全球人口估计

**工具**：`scripts/generate_genesis.py`

- 支持两个历史纪元：10,000 BCE（农业革命前夕）和 70,000 BCE（走出非洲）
- 29 个区域聚落中心，每个包含：
  - 地理坐标 (lon, lat)
  - 空间分布标准差 σ
  - 总人口占比 fraction
  - 初始财富和 ε 水平
  - 区域描述文本
- 按高斯分布在各中心周围撒点
- 自动输出空间范围和 Politeia 配置建议

```bash
python scripts/generate_genesis.py --epoch 10000bce --total 100000 --output examples/genesis_100k.csv
python scripts/generate_genesis.py --epoch 70000bce --total 50000 --output examples/genesis_70k.csv
```

**预生成场景**：

- `examples/genesis_100k.csv`：100,000 agent，10,000 BCE 全球分布
- `examples/genesis_100k.cfg`：完整模拟配置
  - 域范围：[-180, 180] × [-85, 85]（全球经纬度）
  - 总步数：500,000（dt=0.01，模拟 5,000 年 → 5,000 BCE）
  - 分阶段运行建议：Phase 1 (10,000→5,000 BCE) → Phase 2 (5,000→1,000 BCE) → Phase 3 (1,000 BCE→today)
  - 含承载力、瘟疫、密度控制等人口增长约束

**计算量估算**：

| 模拟阶段 | 人口规模 | 每步耗时（估计） | 总步数 | 墙钟时间 |
|---------|---------|--------------|-------|---------|
| 10,000→5,000 BCE | 10⁵→10⁶ | 0.1-1s | 500K | ~1-6 天 |
| 5,000→1,000 BCE | 10⁶→10⁷ | 1-10s | 400K | ~5-45 天 |
| 1,000 BCE→今 | 10⁷→10⁹ | MPI 必需 | 300K | HPC 集群 |

**验证**：

- IC 加载器编译通过，`adam_eve_quick.cfg` 运行验证通过
- `generate_genesis.py` 生成 100,000 agent CSV（6.9 MB），区域分布与考古数据一致

---

### Phase 29：弹性 Checkpoint/Restart 系统（~1 周）✅ 完成

> 实现进程数无关的 checkpoint/restart 系统，支持 N 进程写出的 checkpoint 被任意 M 进程读入（如 4 进程写 → 400 进程读），同时修复快照仅写 rank 0 本地粒子的 bug。

#### 29A：二进制文件格式

**设计原则**：进程数无关——checkpoint 文件不编码任何写入时的进程拓扑信息，所有粒子以全局连续数组存储。

**文件结构**：

```
+--------------------------------------------------+
| Header (固定 128 字节)                             |
|   magic:    uint64 = 0x4356534D43484B50           |
|   version:  uint32 = 1                            |
|   N:        uint64  (粒子总数)                     |
|   step:     uint64  (当前步号)                     |
|   time:     float64 (模拟时间 = step × dt)         |
|   culture_dim, immune_dim, record_size             |
+--------------------------------------------------+
| Config 块                                         |
|   cfg_size: uint64 + cfg_text + padding (8B 对齐)  |
+--------------------------------------------------+
| Particle 数据块 (N × record_size 字节)             |
|   每粒子: [x,y,px,py,w,eps,age,sex,last_birth,    |
|           gid,superior,loyalty,c0..cD,imm0..immM]  |
+--------------------------------------------------+
```

- 每粒子 `record_size = (12 + culture_dim + immune_dim) × 8` 字节
- 100K 粒子 ≈ 11 MB，1M ≈ 112 MB，10M ≈ 1.12 GB

#### 29B：写入策略（双策略自动切换）

**策略 A（Gather-to-Root）**：`N_total ≤ 10M`

- 各 rank 序列化本地粒子 → `MPI_Gatherv` 汇聚到 rank 0 → rank 0 `fwrite` 单文件
- 实现简单，无需 MPI-IO

**策略 B（MPI-IO 并行写）**：`N_total > 10M`

- `MPI_Exscan` 计算全局偏移 → rank 0 写 header + config → 所有 rank `MPI_File_write_at_all` 并行写粒子
- 无内存瓶颈，I/O 带宽随进程数线性扩展

```cpp
const uint64_t GATHER_THRESHOLD = 10'000'000;
if (global_count <= GATHER_THRESHOLD)
    write_checkpoint_gather(...)   // 策略 A
else
    write_checkpoint_mpiio(...)    // 策略 B
```

#### 29C：读取策略（进程数无关）

1. 所有 rank 独立读 128 字节 header（获取 N, culture_dim, record_size）
2. 跳过 config 块
3. 每个 rank 计算自己的粒子范围：`[N×rank/P, N×(rank+1)/P)`
4. `fseek` + `fread` 读取对应区间
5. 反序列化到本地 `ParticleData`
6. SFC `rebalance` + `redistribute` 按空间位置重分配

**4 进程写 → 400 进程读无任何问题**：文件中粒子是连续数组，与写入进程数无关。

#### 29D：快照修复

修复多进程时 `write_snapshot` 仅写 rank 0 本地粒子的 bug：

- `gather_all_particles()` 通过 `MPI_Gatherv` 收集所有 rank 的粒子到 rank 0
- rank 0 使用全局粒子数据写 CSV 快照和分析
- 所有 rank 必须共同参与 gather 调用（collective）

#### 29E：配置与 CLI

**新增配置参数**：

```ini
checkpoint_interval = 100000    # 每 N 步写一次 checkpoint（0=不写）
checkpoint_dir = checkpoints    # checkpoint 输出目录
restart_file =                  # 重启文件路径（空=不重启）
```

**CLI 用法**：

```bash
# 首次运行（写 checkpoint）
mpirun -np 4 politeia config.cfg

# 弹性扩容重启（400 进程读取 4 进程写的 checkpoint）
mpirun -np 400 politeia --restart checkpoints/checkpoint_step_500000.bin override.cfg
```

**新增文件**：

- `src/io/checkpoint.hpp` — `CheckpointHeader` 结构 + pack/unpack + 读写函数声明 + `gather_all_particles()`
- `src/io/checkpoint.cpp` — Gather/MPI-IO 写入 + 并行读取 + gather 实现

**验证**：

- 2 进程写 checkpoint (step=100, 101 粒子) → 4 进程重启读取并继续模拟到 step=300，运行正常
- checkpoint 文件大小正确（header 128B + config + 粒子数据）
- 快照修复：`gather_all_particles()` 确保多进程时 CSV 快照包含所有 rank 的粒子

### Phase 30：HYDE 3.3 校准与标准算例体系（~0.5 周）✅ 完成

> 研究方案 → [[research-proposal#9.5.1 初始条件与人口校准]]
> 算例目录 → [[examples/CASES]]

**目标**：使用权威人口史数据精确校准初始条件的区域分布，建立标准化、可复现的算例体系。

#### 30.1 HYDE 3.3 区域人口校准

数据源：HYDE 3.3 (Klein Goldewijk et al. 2023) — 全球 10,000 BCE 基线人口 4,501,152。

`generate_genesis.py` 中的 29 个区域按 HYDE 3.3 国家级数据重新校准，大洲占比精确匹配：

| 大洲 | HYDE 3.3 | 模型 | 差值 |
|------|----------|------|------|
| 北美洲 | 26.3% | 26.3% | 0.0% |
| 南美洲 | 24.4% | 24.4% | 0.0% |
| 亚洲 | 26.3% | 26.3% | 0.0% |
| 欧洲 | 10.7% | 10.7% | 0.0% |
| 大洋洲 | 7.2% | 7.2% | 0.0% |
| 非洲 | 5.1% | 5.1% | 0.0% |

关键调整：
- 美洲从初版的 ~20% 提升至 50.7%（HYDE 3.3 估计）
- 欧洲包含欧洲俄罗斯部分（从 USSR 727K 中拆分）
- 亚洲细分为新月沃地、中亚、南亚、东亚、东南亚、西伯利亚 + 高加索

#### 30.2 标准算例体系

命名规则：`<scenario>_<calibration>_<scale>`

| 算例 | 配置 + 数据 | 说明 |
|------|-----------|------|
| `genesis_hyde_100k` | `.cfg` + `.csv` (7.2MB) | **主算例**：HYDE 校准 10 万 |
| `genesis_hyde_500k` | 由脚本生成 | 高分辨率扩展 |
| `genesis_paleolithic_50k` | 由脚本生成 | 70,000 BCE |
| `adam_eve` | `.cfg` + `.csv` | 最小初始条件 |

生成命令：
```bash
python3 scripts/generate_genesis.py --n 100000 --era 10000bce --output examples/genesis_hyde_100k.csv
```

**新增/修改文件**：

- `scripts/generate_genesis.py` — 完全重构：HYDE 3.3 精确校准，29 区域带 `hyde_pop` 元数据
- `examples/genesis_hyde_100k.csv` — HYDE 校准 10 万 agent 初始条件
- `examples/genesis_hyde_100k.cfg` — 配套配置（含 HYDE 数据源引用）
- `examples/CASES.md` — 标准算例索引与命名规则
- `research-proposal.md` §9.5.1 — 新增"初始条件与人口校准"节

