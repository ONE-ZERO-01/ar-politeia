# interaction — 个体间交互

> 代码路径：`src/interaction/`
> 涌现方法论：[[research-proposal#2.6 涌现方法论：对称规则，不对称结果]]
> 技术演化分布：[[docs/stochastic-distributions#5. 技术演化 — Lévy-type Jump-Diffusion]]
> 忠诚度/征服分布：[[docs/stochastic-distributions#6. 社会动力学]]

## 职责

模拟人与人之间的经济、文化、技术、政治交互。

## 关键文件

### `resource_exchange.hpp/cpp` — 资源交换

规则对称，结果不对称（研究方案 §2.6.2）：

```
A_i = w_i × ε_i              （能力 = 财富 × 技术）
Δw = η × (A_i−A_j)/(A_i+A_j) × min(w_i,w_j)
```

标签互换时 Δw 变号——规则完全对称，但强者获益，不平等自然放大。

`apply_resource_dynamics()`：每步每人消耗固定量 + 地形产出（受 ε 调制）。

### `culture_dynamics.hpp/cpp` — 文化动力学

```
Δc⃗_i = rate × exp(−|c⃗_i−c⃗_j|²/(2σ²)) × (c⃗_j − c⃗_i) × dt
```

| 函数 | 物理含义 |
|---|---|
| `culture_distance()` | 两人文化差异 ‖c⃗_i−c⃗_j‖ |
| `culture_force_modifier()` | 文化对空间交互的调制：相似→吸引，不同→排斥 |
| `evolve_culture()` | 文化同化：近邻文化向量互相趋同 |
| `compute_culture_order_param()` | 文化序参量 Q = ‖⟨ĉ_i⟩‖ |

### `tech_spread.hpp/cpp` — 技术演化

ε 的三重演化机制（研究方案 §2.4）：

| 机制 | 公式 | 社会类比 |
|---|---|---|
| 缓慢漂移 | `dε = α·‖c⃗‖·ε·dt` | 知识驱动的渐进改良 |
| 接触传播 | `Δε = rate×(ε_j−ε_i)×dt` | 高技术者教低技术邻居 |
| Poisson 跳跃 | `prob = λ·(1+κ‖c⃗‖)·dt` | 技术突破（火、冶铁、蒸汽机） |

### `loyalty.hpp/cpp` — 依附关系与忠诚度

对应研究方案 §2.3 "阶段4"：

```
dL/dt = α·protection − β·tax − γ·‖c⃗_i−c⃗_j‖ + η(t)
```

| 函数 | 社会含义 |
|---|---|
| `form_attachments()` | 从支配图建立 superior 依附 |
| `evolve_loyalty()` | 忠诚度演化 |
| `process_loyalty_events()` | 叛乱（L<0.1）、投靠（L<0.2） |
| `apply_taxation()` | 财富向上流动 |
| `attempt_conquest()` | Power 比 > 1.5 时概率征服 |
| `process_succession()` | 领主死亡→继承 |

## 依赖关系

- 依赖：`core/`、`domain/`（cell_list 邻居遍历）
- 被依赖：`main.cpp`（主循环 Step 2–4, 6b）
