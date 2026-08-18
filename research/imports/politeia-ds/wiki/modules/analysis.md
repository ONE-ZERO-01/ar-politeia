# analysis — 序参量与观测

> 代码路径：`src/analysis/`
> 序参量定义：[[research-proposal#六、观测量与序参量：如何检测阶级和制度的涌现]]
> 分析管线：[[research-proposal#7.8 完整的分析管线]]

## 职责

计算序参量、检测层级涌现与政体结构、性能监控。

## 关键文件

### `order_params.hpp/cpp` — 基础序参量

| 函数 | 物理含义 |
|---|---|
| `compute_gini()` | Gini 系数——不平等程度（G=0 平等，G=1 不平等） |
| `compute_wealth_stats()` | 财富统计：均值、中位数、标准差、极值 |
| `compute_wealth_histogram()` | 财富分布 P(w)：指数→幂律转变 |

### `network_analysis.hpp/cpp` — 交互网络分析

从资源流动模式中**事后检测**层级是否涌现（不预设层级存在）。

| 类/函数 | 物理含义 |
|---|---|
| `InteractionNetwork` | 记录每对粒子间的净资源流动量 |
| `build_dominance_graph()` | 从净流动提取"事实支配关系" |
| `compute_hierarchy_metrics()` | 层级指标：深度 H、分支因子 B、最大分量比 F、实体数 C |

| 指标 | 含义 |
|---|---|
| `H` (max_depth) | 0=无层级，5+=官僚帝国 |
| `C` (n_components) | C=1 天下一统，C=多 诸侯并立 |
| `F` (largest_fraction) | F>0.7 统一帝国 |
| `Ψ` (psi) | Ψ≈1 分封制，Ψ≈0 郡县制 |

### `polity.hpp/cpp` — 政体检测与分类

从层级树连通分量自动检测宏观政治实体：Band(<50) / Tribe(<300) / Chiefdom(<1000) / State(<5000) / Empire(≥5000)。

### `phase_transition.hpp/cpp` — 相变检测

### `perf_monitor.hpp/cpp` — 性能监控与负载均衡

9 个计算阶段分段计时，自动检测负载失衡（效率 < 50% 触发 SFC 重平衡）。

## 依赖关系

- 依赖：`core/`、`interaction/`（交互网络数据）
- 被依赖：`main.cpp`（主循环 Step 9）、Python 脚本（可视化）
