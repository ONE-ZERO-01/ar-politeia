# population — 人口动力学

> 代码路径：`src/population/`
> 理论模型：[[research-proposal#2.5 人口动力学：繁殖模型]]
> 生育/死亡分布：[[docs/stochastic-distributions#3. 死亡机制]] · [[docs/stochastic-distributions#4. 生育]]

## 职责

模拟人口的生育、死亡、瘟疫和密度承载力反馈。

## 关键文件

### `reproduction.hpp/cpp` — 繁殖

生育能力曲线：`φ(a) = φ_max × Beta(t; α, β)`，15 岁性成熟→25 岁达峰→45 岁绝育。

五个交配条件：空间距离 < mate_range、双方存活可育、冷却期已过、文化兼容、财富 > 门槛。

后代遗传：位置=父母中点+扰动、文化=父母均值+变异、技术=取父母较高者、财富=从父母扣除。

### `mortality.hpp/cpp` — 死亡

| 机制 | 公式 | 含义 |
|---|---|---|
| 衰老 | `P = α·exp(β·age)·dt` | Gompertz 法则 |
| 饥饿 | `P = sigmoid(w, threshold)·dt` | 资源低于阈值 |
| 意外 | `P = λ_accident·dt` | 常数概率 |
| 年龄上限 | `age > max_age → 死亡` | 硬性寿命上限 |

### `carrying_capacity.hpp/cpp` — 密度承载力

马尔萨斯反馈——人口密度不能无限增长：

| 函数 | 说明 |
|---|---|
| `compute_local_density()` | CellList 邻居计数 → ρ(x_i) |
| `compute_carrying_capacity()` | K(x) = base × max(0, −V(x)) |
| `density_suppression()` | max(0, 1−ρ/K)，ρ≥K 时归零 |

作用：生育抑制、资源竞争；ε 突破打破承载力天花板 → 新一轮增长。

### `plague.hpp/cpp` — 瘟疫

SIR 模型：密度触发 → 空间传播 → 死亡 → 恢复 → 免疫遗传。

## 依赖关系

- 依赖：`core/`、`domain/`（cell_list）、`force/`（地形用于承载力）
- 被依赖：`main.cpp`（主循环 Step 6）
