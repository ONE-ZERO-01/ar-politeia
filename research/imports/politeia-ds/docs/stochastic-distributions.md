# 随机分布清单 — Politeia 全部随机过程

> **导航**：[[research-proposal]] · [[DEVELOPMENT_PLAN]] · [[CODE_GUIDE]] · [[parallel-framework-design]]

> 本文档记录模拟中每个随机过程所使用的概率分布、控制参数及其物理含义。
> 所有 RNG 均基于 `std::mt19937_64`，种子由 `random_seed + rank` 控制。
>
> 物理框架 → [[research-proposal#三、物理框架：Langevin-跳跃扩散社会动力学]]
> 可配置实验框架 → [[research-proposal#9.6 可配置实验框架：规则空间的系统搜索]]
> Phase 26 实现 → [[DEVELOPMENT_PLAN#Phase 26：可配置实验框架]]

---

## 1. 运动方程 — Langevin 噪声

| 物理过程 | 分布 | 公式 | 源文件 | 控制参数 |
|----------|------|------|--------|----------|
| BBK 积分器热涨落 | 高斯 N(0,1) × σ√(dt/2) | σ = √(2γmT)，px/py 各分量独立 | `langevin_integrator.cpp:114,127` | `temperature`, `friction` |

**说明**：Langevin 方程的随机力是各向同性高斯白噪声。当系统达到热平衡后，
速率分布**涌现**为 2D 麦克斯韦-玻尔兹曼分布（Rayleigh），但这是结果而非输入。

---

## 2. 初始条件

| 物理量 | 分布 | 参数 | 源文件 | 配置项 |
|--------|------|------|--------|--------|
| 位置抖动 | 高斯 N(0, σ) | σ = `init_jitter_factor` × min(dx,dy) | `main.cpp:98` | `init_jitter_factor` (默认 0.15) |
| 初始动量 px, py | 高斯 N(0, √T) | 各分量独立；速率 \|p\| 服从 Rayleigh（2D 麦克斯韦） | `main.cpp:99` | `temperature` |
| 初始年龄 | 均匀 U(a_min, a_max) | | `main.cpp:100` | `init_age_min` (默认 15), `init_age_max` (默认 40) |
| 初始文化向量 | 标准高斯 N(0,1) | 各维独立 | `main.cpp:101` | `culture_dim` |
| 初始性别 | Bernoulli P(male) = r | | `main.cpp:113` | `sex_ratio` (默认 0.5) |

---

## 3. 死亡机制

所有死亡判定均为 Bernoulli 试验 `U(0,1) < P(dt)`，等价于泊松过程的离散化。

| 机制 | 概率公式 | 源文件 | 控制参数 |
|------|----------|--------|----------|
| Gompertz 衰老 | P = α · exp(β_eff · age) · dt | `mortality.cpp:108-109` | `gompertz_alpha`, `gompertz_beta`, `lifespan_wealth_*`, `lifespan_tech_*` |
| 饥饿 | P = sigmoid(k, w, w_thr) · dt，其中 sigmoid = 1/(1+exp(k·(w − w_thr/2))) | `mortality.cpp:112-113` | `starvation_sigmoid_k` (默认 10), `survival_threshold` |
| 意外 | P = λ · dt（纯 Poisson） | `mortality.cpp:116` | `accident_rate` |
| 瘟疫 | P = P₀ · (1 − d^k_i)，感染期满后一次判定 | `plague.cpp:144` | `plague_base_mortality` |

**β_eff 的导出**（当 lifespan coupling 启用时）：

```
β_eff = β₀ / (1 + α_w · w/w_ref + α_ε · ε/ε_ref)
a_max_eff = a_max + k_w · min(w/w_ref, 1) + k_ε · ln(1 + ε/ε_ref)
```

---

## 4. 生育

| 物理量 | 分布 | 说明 | 源文件 | 控制参数 |
|--------|------|------|--------|----------|
| 生育概率 | Bernoulli | P = φ(age) × density_suppression | `reproduction.cpp:134` | `max_fertility`, `peak_fertility_age` |
| 生育率曲线 φ(a) | Beta 形状 t^α(1−t)^β | α 可配；β = α(1−t_peak)/t_peak | `reproduction.cpp:20-31` | `fertility_alpha` (默认 2.0) |
| 后代位置偏移 | 高斯 N(0, σ) | 父母中点 + 高斯偏移 | `reproduction.cpp:142-143` | `mutation_strength` |
| 后代 ε 变异 | 半正态 \|N(0,σ)\| × scale | 确保只增不减 | `reproduction.cpp:147` | `mutation_strength`, `epsilon_mutation_scale` (默认 0.01) |
| 后代文化变异 | 高斯 N(0,σ) × scale | 加性噪声 | `reproduction.cpp:176` | `mutation_strength`, `culture_mutation_scale` (默认 0.2) |
| 后代性别 | Bernoulli P(male) = r | | `reproduction.cpp:167` | `sex_ratio` |

---

## 5. 技术演化 — Lévy-type Jump-Diffusion

| 物理过程 | 分布 | 公式 | 源文件 | 控制参数 |
|----------|------|------|--------|----------|
| ε 漂移 | 确定性 | dε = α · \|c⃗\| · ε · dt | `tech_spread.cpp:60` | `tech_drift_rate` |
| ε 接触扩散 | 确定性 | Δε = rate · (ε_j − ε_i) · dt | `tech_spread.cpp:81` | `tech_spread_rate` |
| ε Poisson 跳跃 | Bernoulli ← Poisson | P = λ(1 + κ\|c⃗\|) · dt；幅度 = Δε · ε_i（乘性） | `tech_spread.cpp:113-118` | `tech_jump_base_rate`, `tech_jump_knowledge_scale`, `tech_jump_magnitude` |
| 财富正跳跃 | Bernoulli ← Poisson | P = λ_pos · dt；幅度 = fraction × w（乘性） | `tech_spread.cpp:133-135` | `wealth_jump_rate_pos`, `wealth_jump_fraction` |
| 财富负跳跃 | Bernoulli ← Poisson | P = λ_neg · dt；幅度 = fraction × w（乘性） | `tech_spread.cpp:139-141` | `wealth_jump_rate_neg`, `wealth_jump_fraction` |

**说明**：ε 漂移和扩散是确定性的，只有跳跃是随机的。技术和财富的跳跃构成
**复合 Poisson 过程**（跳跃时刻 Poisson + 乘性跳跃幅度），使得财富分布从
高斯演变为厚尾 Pareto 幂律分布。

---

## 6. 社会动力学

| 物理过程 | 分布 | 说明 | 源文件 | 控制参数 |
|----------|------|------|--------|----------|
| 忠诚度噪声 | 高斯 N(0, σ) | dL += η · dt | `loyalty.cpp:57,82` | `loyalty_noise_sigma` |
| 征服概率 | Bernoulli | P = base_prob × power_i/(power_i+power_j) | `loyalty.cpp:249-250` | `conquest_base_prob`, `conquest_power_ratio` |
| 战争伤亡 | Bernoulli | 每个附庸以 casualty_rate 概率死亡 | `loyalty.cpp:272` | `war_casualty_rate` |
| 瘟疫触发 | Bernoulli ← Poisson | P = trigger_rate · dt（密度超阈值时） | `plague.cpp:63` | `plague_trigger_rate`, `plague_trigger_density` |
| 瘟疫传播 | Bernoulli | P = infection_rate · dt（每对空间接触） | `plague.cpp:102,107` | `plague_infection_rate` |
| 零号病人 | 离散均匀 U{0, N−1} | 随机选一个存活粒子 | `plague.cpp:68-69` | — |

---

## 7. 确定性过程（不含随机性，但易混淆）

以下过程完全由当前状态确定，无随机采样：

| 过程 | 公式 | 源文件 |
|------|------|--------|
| 资源交换 | Δw = η(A_i−A_j)/(A_i+A_j) · min(w_i,w_j) | `resource_exchange.cpp:65` |
| 文化同化 | Δc_k = rate · exp(−d²/2σ²) · (c_j−c_i) · dt | `culture_dynamics.cpp:59-64` |
| 资源产出 | dw = R(x) · ε · dt − consumption · dt | `resource_exchange.cpp:96-107` |
| 生产力曲线 | 高斯包络 exp(−(age−30)²/800) | `mortality.cpp:52-63` |
| ε 下限钳位 | ε = max(ε, 0.1) | `tech_spread.cpp:91` |

---

## 分布族汇总

| 分布族 | 实现方式 | 主要用途 |
|--------|----------|----------|
| **高斯 N(0,σ)** | `std::normal_distribution` | Langevin 噪声、初始条件、变异、忠诚度噪声 |
| **均匀 U(0,1)** | `std::uniform_real_distribution` | 所有 Bernoulli 判定的基础 |
| **均匀 U(a,b)** | `std::uniform_real_distribution` | 初始年龄 |
| **离散均匀 U{0,N−1}** | `std::uniform_int_distribution` | 零号病人选取 |
| **Bernoulli(p)** | `U(0,1) < p` | 死亡/生育/跳跃/传播/征服 |
| **半正态 \|N(0,σ)\|** | `std::abs(normal())` | ε 变异（只增不减） |
| **Beta 形曲线** | 确定性函数 t^α(1−t)^β | 生育率 φ(age) 的年龄调制 |

> **关于麦克斯韦分布**：代码中没有直接使用麦克斯韦分布。初始动量各分量是独立
> 高斯 N(0,√T)，在 2D 中速率模 |p| 自然服从 Rayleigh 分布（即 2D 麦克斯韦）。
> Langevin 恒温器也保证平衡态速度分布涌现为麦克斯韦-玻尔兹曼分布。
> 这些都是高斯输入的数学推论，而非显式设定。
