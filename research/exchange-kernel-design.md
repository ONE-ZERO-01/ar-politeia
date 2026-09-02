# 交换核稳态设计（D0）

> Cycle 3 前置分析。产出自 plan D0 阶段：交换核稳态理论诊断 + 候选新核设计。
> 本文件是设计权威记录，指导 D1（实现）与 D2（数值校准）。

## 1. 结论摘要

- **根因**：当前交换核是无耗散的富者更富过程，无非平凡稳态，必然向极化态（Gini→1）演化。
  这是 Cycle 1→2 的 `stationarity` 与 `dt_convergence` 反复失败的模型层根因，不是数值问题。
- **修复方向**（用户已确认）：修正交换核，保留标签对称 / 零和守恒 / 非负 / equal-state 吸收，
  新增**非平凡稳态**。
- **推荐候选**：候选 B（能力差驱动漂移 + 与 |D_ij| 成正比的反对称零和涨落）。
- **旧方案呼应**：`politeia-ds` 的 Q1（"对称资源交换是否收敛到 Boltzmann-Gibbs 分布"）从未被回答，
  本设计直接补上这块遗留缺口。

## 2. 当前核的极化证明

交换规则（Cycle 1/2 confirmatory 参数下 ε=1，w_ref=5）：

```
A(w) = w / (w + w_ref)            （严格单调增：A'(w) = w_ref/(w+w_ref)^2 > 0）
D_ij = (A_i − A_j) / (A_i + A_j)
Δw   = η · D_ij · min(w_i, w_j)
```

**定理（极化）**：在无生产、无消费、无衰减、无噪声时，任意非退化初值下财富分布趋向极化，不存在非平凡稳态。

证明思路（Lyapunov）：

- 总财富 `W = Σ w_i` 守恒（零和，`w_i += Δw, w_j -= Δw`）。
- 由 `A` 严格单调，`sign(D_ij) = sign(w_i − w_j)`，故富人恒赢、穷人恒输。
- 取 `V = Σ w_i^2`。对任一对 `(i,j)`，`w_i ≥ w_j` 时转移使 `w_i` 增、`w_j` 减，`(w_i − w_j)^2` 严格增，
  故 `dV/dt ≥ 0`，等号仅当全体 `A_i = A_j`（均匀态）或 `min(w_i,w_j) = 0`（穷人已归零）。
- 均匀态是不稳定平衡：`wealth_log_sigma = 0.01` 的初始扰动被放大（略富者在后续每对交换中稳定获胜）。
- 因此稳态只有两类：不稳定均匀态、极化吸收态。**无非平凡稳态。** ∎

这精确解释了观测：equal-state 是吸收态（`equal_state_is_absorbing` 通过），而扰动初值持续向极化漂移
（Gini 随有效交换充分度上升，Cycle 1 中 dt 越小、Gini 越高；Cycle 2 修复 dt 缩放后 dt 收敛通过，
但 `total_time=500` 内仍无稳态窗口）。

## 3. 候选新核

### 候选 A（CC / saving-propensity 随机再分配）—— 否决

经典 Chakraborti–Chakrabarti 模型：随机选对，按随机比例 λ 再分配总财富。稳态是 Gamma 分布（理论已知）。

否决理由：它破坏 **equal-state 吸收**。均匀态 `w_i = w_j` 在随机 λ 下仍会再分配（除非 λ=1/2），
与 `E0-NUMERICS` 的 `equal_state_is_absorbing ≤ 1e-20` 检查冲突；且破坏"能力差驱动"的机制叙事。

### 候选 B（能力差漂移 + 反对称零和涨落）—— 推荐

对每对 `(i,j)`：

```
Δw = min(w_i, w_j) · [ η_d · D_ij  +  η_n · |D_ij| · s_ij ]
```

- `η_d`：漂移强度（沿用原 `exchange_rate = 0.003`）。
- `η_n`：涨落强度（新增参数，建议初值 0.1–0.3，由 D2 校准）。
- `D_ij = (A_i − A_j)/(A_i + A_j) ∈ (−1, 1)`，反对称：`D_ji = −D_ij`。
- `s_ij ∈ {+1, −1}`：**反对称随机因子**，`s_ji = −s_ij`（构造见 §4）。

物理解释：漂移项延续"能力差驱动的富者更富"，涨落项在财富差越大（|D_ij| 越大）时越强，
把极端富者拉回，形成漂移—扩散平衡，从而存在非平凡稳态。`η_n/η_d` 比值调节稳态 Gini 水平
（比值越大越平等）。

## 4. 不变式检查

| 不变式 | 候选 B 是否满足 | 说明 |
|---|---|---|
| 标签对称 | 是 | `D_ij` 反对称，`s_ij` 反对称，`|D_ij|` 对称，整体交换 i↔j 变号 |
| 零和守恒 | 是 | `w_i += Δw, w_j -= Δw` |
| 非负 | 是（需 clamp） | `Δw = clamp(Δw, −w_i, w_j)`；`|Δw| ≤ min(w_i,w_j)·(η_d+η_n)`，取 `η_d+η_n ≤ 1` 即安全 |
| equal-state 吸收 | 是 | `D_ij = 0` 时 `|D_ij| = 0`，涨落项消失，`Δw = 0` |
| 非平凡稳态 | 是（§5 论证） | 漂移与扩散平衡 |

### s_ij 的反对称构造（关键实现约束）

`s_ij` 必须满足 `s_ji = −s_ij`，且不能依赖遍历方向（否则破坏零和）。推荐确定性对称伪随机：

```
key = combine(min(i,j), max(i,j), step)   // 与视角无关
r   = 2·bit(hash(key)) − 1                 // r ∈ {+1,−1}
s_ij = (i < j) ? r : −r
```

用确定性 hash 而非共享 RNG，原因有二：

1. **零和正确性**：OpenMP 分支用 `for_neighbors_of`，每对 `(i,j)` 被访问两次（i 视角与 j 视角）。
   反对称 `s_ij` 保证两次访问的涨落转移互为相反数，抵消后守恒。若引入非反对称的 per-pair RNG，
   两次访问会抽到不同值，破坏零和。
2. **OpenMP 安全 + 可复现**：hash 无共享可变状态（遵循 lessons-learned 原则 7.1），且天然可复现，
   契合 `preflight` 的 seed 复现性检查。

### 邻居数解耦（待 D2 验证的风险点）

涨落与漂移都是 per-pair 的，个体净漂移 ∝ 邻居数、净涨落方差 ∝ 邻居数。稳态 Gini 由 `η_d/η_n`
（经邻居数标度后）决定。E3-ROBUSTNESS 会改变人口/分辨率从而改变邻居数，可能导致稳态 Gini 随密度漂移。
D2 校准必须在目标密度下进行，E3 需显式检验密度不变性；若破坏，则需在个体层归一化涨落强度
（如除以 `√邻居数`）。这是 D1 不预解、D2 必须显式回验的点。

## 5. 稳态存在性论证（mean-field 框架）

在完全混合图（mean-field）极限下，个体财富服从 Fokker–Planck 方程：

```
∂f/∂t = − ∂/∂w [ μ(w) f ]  +  ½ ∂²/∂w² [ D(w) f ]
```

- 漂移系数 `μ(w)`：来自富者更富项，使方差增大的方向性流。
- 扩散系数 `D(w)`：来自涨落项，使分布弛豫的随机流。

稳态 `f_*(w)` 满足 `μ f = ½ d(Df)/dw`。当 `η_n > 0` 时扩散非零，漂移与扩散可平衡，存在非平凡稳态。
定性形状介于「指数/Gamma 分布（η_n ≫ η_d，CC 极限）」与「极化（η_n → 0，当前核）」之间。
精确稳态形式与 Gini 值由 D2 数值校准确定（空间局部性使 mean-field 仅为近似）。

## 6. D1 实现改动清单（准确到位置）

| # | 文件 | 改动 |
|---|---|---|
| 1 | `research/src/experiments/politeia/src/core/config.hpp`（约 L50） | `SimConfig` 新增 `Real exchange_noise_strength = 0.0;` |
| 2 | `research/src/experiments/politeia/src/core/config.cpp` | `load_config` 解析 `exchange_noise_strength` |
| 3 | `research/src/experiments/politeia/src/interaction/resource_exchange.hpp` | `ExchangeParams` 新增 `Real noise_strength = 0.0;` |
| 4 | `research/src/experiments/politeia/src/interaction/resource_exchange.cpp` | `exchange_resources` 实现 §3 候选 B，含反对称 `s_ij` 构造与非负 clamp |
| 5 | `research/src/experiments/politeia/src/main.cpp`（约 L380） | 将 `cfg.exchange_noise_strength` 传入 `exchange_params` |
| 6 | `research/src/experiments/run_landscape_study.py`（`common_cpp_config` L255 附近） | 新增 `exchange_noise_strength` 字段并传递到 per-run config |
| 7 | `research/src/experiments/run_landscape_study.py`（`default_conditions`） | E0 perturbed 条件按需设置噪声强度（涨落按 `sqrt(dt)` 缩放、漂移按 `dt` 缩放） |

补充：`exchange_noise_strength` 是扩散项，E0 的 dt 缩放按 **√dt** 缩放（`noise_strength * math.sqrt(factor)`），
以保持连续时间扩散系数分辨率不变；而漂移项 `exchange_rate` 仍按 dt 缩放（`exchange_rate * factor`，
与 Cycle 2 已修复的逻辑对齐）。这是漂移 O(dt) 与扩散 O(√dt) 的连续时间极限差异所要求的。

## 7. D2 待校准参数与验收

- **η_n 初值**：`exchange_noise_strength = 0.15`（`η_n/η_d ≈ 50`），D2 用参数扫描在
  `{0.05, 0.10, 0.15, 0.25, 0.40}` 中确定使稳态 Gini 落在 `[0.3, 0.7]` 且五检查全过的值。
- **五检查验收**（`E0-NUMERICS-C3`）：守恒 ≤1e-8、非负 ≥−1e-12、dt 收敛 ≤0.02、
  equal-state 吸收 ≤1e-20、stationarity（drift≤0.1 且 ESS≥4）**全部通过**。
- **B0 健康验收**（`B0-DYNAMICS-PILOT-C3`）：固定人口、非负、有限指标、稳态窗口 stationarity 全过。
- **失败处理**：任一 Gate 不过则停止，回 §3 调整核/参数，不 tune 出期望的社会结果。

## 8. 边界

- 本设计仅涉及交换微观模型；移动（Langevin）与生产通道不动。
- 交换核改动属于模型层，触发新参数锁 v2 与新 cycle（Cycle 3）。
- Cycle 1/2 的负面证据完整保留，不与 Cycle 3 混算。
- 不声称社会温度 / 涨落—耗散定律为已验证社会定律（遵循 `question.md` 证据边界）。
