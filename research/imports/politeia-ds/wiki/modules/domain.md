# domain — 空间管理

> 代码路径：`src/domain/`
> MPI 并行设计：[[DEVELOPMENT_PLAN#1.2 MPI 并行策略：2D 区域分解]]
> 大规模 SFC 方案：[[docs/parallel-framework-design]]

## 职责

管理二维空间域的划分、邻居搜索、MPI 区域分解与粒子迁移。

## 关键文件

### `cell_list.hpp/cpp` — Cell List 邻居搜索

将二维空间划分为网格，只需检查相邻格子中的人对，将 O(N²) 降为 O(N)。

| 方法 | 作用 |
|---|---|
| `init()` | 按截断距离将域划分为网格 |
| `build()` | 将所有粒子按位置分配到格子（计数排序，每步重建） |
| `for_each_pair()` | 遍历所有距离小于截断的粒子对，对每对执行回调 |

**热点路径**：`for_each_pair` 是整个模拟中调用最频繁的函数。

### `decomposition.hpp/cpp` — MPI 2D 域分解

将全局"世界地图"切割为 px×py 个子区域，每个 MPI 进程负责一个子区域。

| 方法 | 作用 |
|---|---|
| `init()` | 计算本 rank 的子域边界 |
| `owns()` | 判断一个位置是否在本 rank 的管辖范围 |
| `migrate_particles()` | 检测越界粒子 → pack → MPI_Sendrecv → unpack |
| `exchange_halos()` | 将边界附近的粒子副本发给邻居（用于跨域力计算） |
| `global_sum()` | MPI_Allreduce 求全局标量和 |

### `sfc_decomposition.hpp/cpp` — Morton Z-order SFC 分解

基于 Morton Z-curve 的空间填充曲线分解，支持动态负载均衡。

### `morton.hpp` — Morton 编码

2D 坐标到 Morton key 的编码/解码。

## 依赖关系

- 依赖：`core/`（粒子数据）
- 被依赖：`force/`、`interaction/`、`population/`（通过 cell_list 做邻居遍历）
