# Politeia 大规模并行框架设计

> **导航**：[[research-proposal]] · [[DEVELOPMENT_PLAN]] · [[CODE_GUIDE]] · [[stochastic-distributions]]

> 当前 MPI 实现 → [[CODE_GUIDE#2. `domain/` — 空间管理]]
> 开发路线 → [[DEVELOPMENT_PLAN#1.2 MPI 并行策略：2D 区域分解]]
> 计算方案理论 → [[research-proposal#9.5 计算方案]]

## 一、目标规模

- **粒子数**：8 × 10⁹（80亿人，全球模拟）
- **内存**：~1 TB（120 bytes/粒子 × 80亿）
- **节点数**：8-64 个 HPC 节点（128-256 GB/节点）
- **MPI ranks**：64-1024
- **每 rank 粒子数**：~10⁷（千万级）

## 二、为什么必须用空间填充曲线

### 2D Cartesian 分解的致命缺陷

```
均匀 Cartesian 16×16 = 256 ranks：
  太平洋 rank：0 个粒子（纯海洋）
  撒哈拉 rank：100 个粒子（沙漠）
  长三角 rank：5 × 10⁷ 个粒子（人口密集区）

→ 负载比 500000:1，并行效率 < 0.01%
```

### 空间填充曲线的优势

1. **任意分布均匀负载**：1D 排序后均匀切割，每 rank 粒子数严格相等
2. **空间局域性**：曲线保持空间邻近性，相邻 rank 管理的空间区域大致相邻
3. **动态重平衡 O(N)**：只需重新切割 1D 序列，无需全局数据重分配
4. **通信量可控**：邻居通信量 ∝ 表面积 / 体积比，曲线保证表面积小

## 三、Morton (Z-order) 曲线方案

### 3.1 为什么选 Morton 而非 Hilbert

| | Morton (Z-order) | Hilbert |
|---|---|---|
| 编码 | bit interleave，极快 | 查表/递归，较慢 |
| 空间局域性 | 好（偶有跳跃） | 更好（无跳跃） |
| 实现复杂度 | 低（位操作） | 中等 |
| 解码 | 简单 | 需要状态机 |

对于我们的场景，Morton 的空间局域性已经足够好，且编码/解码速度更快（热点路径中需要频繁计算 key）。

### 3.2 算法概述

```
1. 将全球域 [xmin,xmax] × [ymin,ymax] 离散化为 2^L × 2^L 网格（L=20 → ~1m 分辨率）
2. 每个粒子计算 Morton key = interleave(grid_x, grid_y)，得到 64-bit 整数
3. 对所有粒子按 Morton key 排序（并行基数排序）
4. 将排序后的粒子序列均匀切割为 P 段（P = MPI rank 数）
5. 每个 rank 管理一段连续的 Morton key 范围
6. 邻居通信：rank 的邻居是 Morton key 范围相邻或空间相邻的 ranks
```

### 3.3 数据结构变更

```cpp
/// 空间填充曲线并行框架
class SFCDecomposition {
public:
    using MortonKey = std::uint64_t;

    /// 初始化：定义全局域和 Morton 网格分辨率
    void init(Real xmin, Real xmax, Real ymin, Real ymax,
              int level, int rank, int nprocs);

    /// 计算一个点的 Morton key
    MortonKey compute_key(Real x, Real y) const;

    /// 负载均衡：重新划分 key 范围使每 rank 粒子数均匀
    /// 返回 [P+1] 的分割点数组：rank r 管理 [splits[r], splits[r+1])
    std::vector<MortonKey> rebalance(
        const std::vector<MortonKey>& local_keys,
        MPI_Comm comm
    );

    /// 根据新的分割点迁移粒子
    void redistribute(ParticleData& particles,
                      const std::vector<MortonKey>& splits,
                      MPI_Comm comm);

    /// 确定需要通信的邻居 ranks（key 范围相邻 + 空间相邻）
    std::vector<int> find_neighbor_ranks(
        const std::vector<MortonKey>& splits,
        Real cutoff
    ) const;

    /// Halo 交换：发送 cutoff 范围内的粒子到邻居 ranks
    void exchange_halos(
        const ParticleData& particles,
        const std::vector<int>& neighbors,
        Real cutoff,
        ParticleData& ghost_particles,
        MPI_Comm comm
    );
};
```

### 3.4 Morton Key 编码

```cpp
// 2D Morton 编码：将 (x, y) 网格坐标交错为 64-bit key
// 示例：x=0b1010, y=0b0011 → key=0b01001101
MortonKey encode_morton_2d(uint32_t x, uint32_t y) {
    auto expand = [](uint32_t v) -> uint64_t {
        uint64_t u = v;
        u = (u | (u << 16)) & 0x0000FFFF0000FFFF;
        u = (u | (u <<  8)) & 0x00FF00FF00FF00FF;
        u = (u | (u <<  4)) & 0x0F0F0F0F0F0F0F0F;
        u = (u | (u <<  2)) & 0x3333333333333333;
        u = (u | (u <<  1)) & 0x5555555555555555;
        return u;
    };
    return expand(x) | (expand(y) << 1);
}
```

### 3.5 负载均衡算法

```
1. 每个 rank 计算本地粒子的 Morton key 并局部排序
2. MPI_Allgather 收集每个 rank 的粒子数 → 全局直方图
3. 计算全局前缀和，确定理想分割点（每段 N/P 个粒子）
4. 通过并行采样排序（sample sort）或全局直方图确定精确分割点
5. 每个 rank 根据新分割点将粒子发送到目标 rank
6. 更新本地 CellList 和力计算结构
```

### 3.6 邻居发现

Morton 曲线的非结构化邻居关系使得邻居发现比 Cartesian 更复杂：

```
方案 A（保守）：
  rank r 的空间范围 = 其所有粒子的 bounding box
  邻居 = bounding box 扩展 cutoff 后与之重叠的所有 ranks
  通过 MPI_Allgather bounding box 然后本地判断

方案 B（精确）：
  遍历 key 范围边界的 Morton cell，找到空间上 cutoff 内的所有 cell
  映射回 rank → 邻居列表
```

## 四、分层架构

80 亿粒子需要分层设计：

```
Layer 3: MPI ranks (64-1024 个进程)
  ↓ SFC 分解 + 粒子迁移
Layer 2: 节点内 OpenMP/线程 (每 rank 16-64 线程)
  ↓ CellList 的并行遍历
Layer 1: SIMD 向量化 (AVX-512: 8 doubles/cycle)
  ↓ 力计算内层循环
Layer 0: 单粒子操作
```

### 4.1 MPI 层（进程间）

- SFC 分解 + 负载均衡
- 粒子迁移（跨 rank）
- Halo 交换（ghost 粒子）
- 全局归约（序参量）

### 4.2 OpenMP 层（进程内，未来实现）

```cpp
// CellList pair 遍历的 OpenMP 并行化
#pragma omp parallel for schedule(dynamic) reduction(+:total_pe)
for (int cy = 0; cy < ny; ++cy) {
    for (int cx = 0; cx < nx; ++cx) {
        // cell (cx,cy) 内的 pair 计算
        // 需要原子操作或线程私有力缓冲区
    }
}
```

### 4.3 SIMD 层（循环内）

力计算内层循环用 `__restrict__` + 编译器自动向量化：

```cpp
// 力计算内层已经是 SIMD 友好的：
// - 连续内存访问（SoA 布局）
// - 无分支（力封顶用 min/max 而非 if）
// - __restrict__ 标注（无别名）
```

## 五、通信模式对比

| | 当前 Cartesian | SFC 方案 |
|---|---|---|
| 邻居数 | 固定 8 个 | 动态（通常 10-30 个） |
| 负载均衡 | 无（静态均匀） | 动态（O(N) 重分配） |
| 通信量 | 与粒子密度无关 | 与密度有关（高密度区通信少） |
| 实现复杂度 | 低 | 中-高 |
| 扩展性极限 | ~10⁴ 粒子 | ~10¹⁰ 粒子 |

## 六、实施路线

### 6.1 Phase 10A：SFC 基础设施（~2 周）

- [ ] Morton key 编码/解码
- [ ] `SFCDecomposition` 类框架
- [ ] 粒子按 Morton key 排序
- [ ] 分割点计算（全局直方图法）
- [ ] 单元测试：编码/解码正确性、排序后的空间局域性

### 6.2 Phase 10B：SFC 通信（~2 周）

- [ ] 粒子重分配（MPI_Alltoallv）
- [ ] 邻居发现（bounding box 方法）
- [ ] Halo 交换（非结构化邻居）
- [ ] 替换现有 `DomainDecomposition`
- [ ] 并行一致性测试：SFC 结果 vs 串行结果

### 6.3 Phase 10C：动态负载均衡（~1 周）

- [ ] 负载监控（计时 + 粒子数统计）
- [ ] 自动触发重平衡（失衡度 > 阈值时）
- [ ] 重平衡后的 CellList 重建
- [ ] 扩展性测试（weak/strong scaling）

### 6.4 Phase 10D：MPI+OpenMP 混合并行（未来）

- [ ] CellList 遍历的 OpenMP 并行化
- [ ] 线程私有力缓冲区 → 归约
- [ ] OpenMP 感知的内存分配

## 七、对现有代码的影响

替换 `domain/decomposition.hpp/cpp`，其他模块基本不变：

| 模块 | 影响 |
|---|---|
| `domain/decomposition.*` | **完全重写** → `domain/sfc_decomposition.*` |
| `domain/cell_list.*` | 不变（仍在每个 rank 的局部域上工作） |
| `main.cpp` | 修改初始化和时间步中的通信调用 |
| `force/*` | 不变 |
| `integrator/*` | 边界条件需改为"对 rank 边界不反射，而是迁移" |
| `interaction/*` | 不变 |
| `population/*` | 不变 |
| `analysis/*` | 全局归约需要适配 |
