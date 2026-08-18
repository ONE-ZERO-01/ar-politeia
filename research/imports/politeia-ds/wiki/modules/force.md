# force — 力计算

> 代码路径：`src/force/`
> 势函数理论：[[research-proposal#9.2 势函数设计（核心难点）]]

## 职责

计算作用在每个粒子上的确定性力：人际社会力 + 地形外势力。

## 关键文件

### `social_force.hpp/cpp` — 人际空间交互力

借鉴 Lennard-Jones 势的数学形式，模拟人际吸引和排斥。

```
V(r) = 4ε [(σ/r)¹² − (σ/r)⁶]
F(r) = 24ε [2(σ/r)¹² − (σ/r)⁶] / r
```

| 代码符号 | 数学 | 社会类比 |
|---|---|---|
| `epsilon` | ε | 人际吸引强度——决定聚集的紧密程度 |
| `sigma` | σ | 人际"舒适距离"——聚居但不拥挤的平衡点 |
| `cutoff` | r_cut | 社交视野半径——超过此距离的人互不可见 |
| 排斥项 (σ/r)¹² | | 两人不能占同一位置，过近导致资源竞争 |
| 吸引项 (σ/r)⁶ | | 人是社会动物，倾向聚居合作 |

使用 Newton 第三定律 `F_i = -F_j`，每对只计算一次。力封顶 `F_MAX=100` 防止数值不稳定。

### `terrain_force.hpp/cpp` — 地形外势

模拟自然地理对人类活动的吸引——河谷/平原是势能低谷，山脉/沙漠是势能高地。

```
V(x,y) = -depth × exp(−((x−cx)²+(y−cy)²) / (2×width²))
```

多个势阱 = 多条河谷 = 多个文明发源地。

### `terrain_loader.hpp/cpp` — 真实地形数据加载器

用真实 DEM（数字高程模型）替代理想化的高斯势阱。

| 组件 | 作用 |
|---|---|
| `load_ascii()` | ESRI ASCII Grid (.asc) 加载 |
| `load_binary()` | Raw binary float64 加载 |
| `generate_synthetic()` | 合成地形（valley/ridge/river/basins/continent） |
| `elevation(x,y)` | 双线性插值查询 |
| `gradient(x,y)` | 中心差分梯度 |
| `force(x,y,s)` | F = -s × ∇h，指向低洼处 |

配置：`terrain_type=grid` + `terrain_file=xxx.asc` + `terrain_scale=1.0`

## 依赖关系

- 依赖：`core/`（粒子数据）、`domain/`（cell_list 用于邻居遍历）
- 被依赖：`integrator/`（Step 4 重新计算力）
