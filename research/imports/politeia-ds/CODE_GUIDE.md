# Politeia 代码指南：每个模块的物理含义

> **导航**：[[research-proposal]] · [[DEVELOPMENT_PLAN]] · [[docs/parallel-framework-design]] · [[docs/stochastic-distributions]]

## 总览

Politeia 模拟的核心方程是 **Langevin-跳跃扩散方程**：

```
m·q̈ = −∇V(q) − γ·q̇ + ξ(t) + J(t)
```

- `−∇V(q)`：确定性力（地形势 + 人际 LJ 势）→ 代码中的 `force/` 模块
- `−γ·q̇`：耗散力（制度腐化、知识遗忘）→ `integrator/langevin_integrator.cpp` 中的摩擦项
- `ξ(t)`：高斯白噪声（日常随机事件）→ 积分器中的随机力项
- `J(t)`：Poisson 跳跃（技术突破、命运大事件）→ `interaction/tech_spread.cpp`

每个粒子代表一个**人**，状态向量为：

```
Z_i(t) = (x_i, p_i, w_i, c⃗_i, ε_i)
  x_i: 地理位置（在哪里）     → particle_data 中的 x_[]
  p_i: 动量（移动能力）       → particle_data 中的 p_[]
  w_i: 财富/资源存量（有多少） → particle_data 中的 w_[]
  c⃗_i: 文化向量（知道什么/认同谁） → particle_data 中的 cv_[]
  ε_i: 能量利用能力（能做什么） → particle_data 中的 eps_[]
```

---

## 模块详解

### 1. `core/` — 基础数据层

> 理论基础 → [[research-proposal#2.2 个体状态向量]]
> SoA 设计 → [[DEVELOPMENT_PLAN#1.1 数据布局：SoA（Structure of Arrays）]]

#### `types.hpp` — 类型别名

| 类型 | 含义 |
|---|---|
| `Real` = `double` | 所有物理量的精度 |
| `Index` = `size_t` | 粒子索引 |
| `Vec2` = `array<Real,2>` | 二维向量（位置、动量） |
| `ParticleStatus` | 粒子状态：Alive/Dead/Pregnant/Nursing |

#### `constants.hpp` — 物理常数

| 常量 | 物理含义 | 默认值 |
|---|---|---|
| `DEFAULT_DT` | 时间步长（年） | 0.01 |
| `DEFAULT_TEMPERATURE` | 社会"温度"——随机涨落强度，高温=乱世 | 1.0 |
| `DEFAULT_FRICTION` | 耗散系数 γ——制度损耗率 | 1.0 |
| `DEFAULT_LJ_EPSILON` | LJ 势阱深度——人际吸引强度 | 1.0 |
| `DEFAULT_LJ_SIGMA` | LJ 特征距离——人际"舒适距离" | 1.0 |
| `DEFAULT_LJ_CUTOFF` | LJ 截断距离——超过此距离两人互不影响 | 2.5 |
| `DEFAULT_INITIAL_WEALTH` | 初始人均财富 | 5.0 |
| `DEFAULT_SURVIVAL_THRESHOLD` | 生存阈值——低于此值开始饿死 | 0.1 |
| `DEFAULT_CONSUMPTION_RATE` | 每步资源消耗率——"吃饭"成本 | 0.002 |
| `DEFAULT_PUBERTY_AGE` | 性成熟年龄 | 15.0 |
| `DEFAULT_MENOPAUSE_AGE` | 绝育年龄 | 45.0 |
| `DEFAULT_GESTATION_TIME` | 妊娠期（年） | 0.75 |
| `DEFAULT_NURSING_TIME` | 哺育期（年） | 2.0 |
| `DEFAULT_CULTURE_DIM` | 文化向量维度 | 2 |
| `DEFAULT_ACCIDENT_RATE` | 意外死亡概率/步 | 1e-4 |
| `DEFAULT_GOMPERTZ_BETA` | Gompertz 衰老加速参数 | 0.085 |

#### `particle_data.hpp/cpp` — SoA 粒子数据容器

**物理含义**：存储所有"人"的属性。使用 Structure-of-Arrays 布局而非 Array-of-Structures，使得力计算等热点路径可以连续访问同一属性的所有粒子数据，对 CPU 缓存友好。

| 数组 | 存储 | 物理含义 |
|---|---|---|
| `x_[N*2]` | 位置 (x,y) 交错 | 这个人在地图上的什么位置 |
| `p_[N*2]` | 动量 (px,py) 交错 | 这个人的移动速度×质量 |
| `w_[N]` | 财富 | 这个人拥有多少可交换的资源 |
| `cv_[N*D]` | 文化向量 | 这个人的知识和文化取向 |
| `eps_[N]` | 能量利用能力 ε | 这个人能利用多少自然能量（技术水平） |
| `age_[N]` | 年龄 | 确定性演化 da/dt=1 |
| `last_birth_time_[N]` | 上次生育时间 | 用于妊娠/哺育冷却期 |
| `status_[N]` | 存活状态 | Alive/Dead/Pregnant/Nursing |
| `force_[N*2]` | 力累加器 | 当前步所有力的合力 |

**关键方法**：
- `add_particle()`: 新生儿出生——在数组末尾添加一个新人
- `mark_dead()`: 标记死亡——设置 status=Dead 但不立即删除（避免打乱索引）
- `compact()`: 压缩数组——移除所有死者，活人索引重排

#### `config.hpp/cpp` — 配置文件解析

从 key=value 格式文件读取所有模拟参数。对应研究方案中"可调参数"的集合。

---

### 2. `domain/` — 空间管理

> MPI 并行设计 → [[DEVELOPMENT_PLAN#1.2 MPI 并行策略：2D 区域分解]]
> 大规模 SFC 方案 → [[docs/parallel-framework-design]]

#### `cell_list.hpp/cpp` — Cell List 邻居搜索

**物理含义**：在计算人际交互（交换资源、文化传播、交配等）时，只有距离足够近的两个人才会互动。Cell List 将二维空间划分为网格，每个格子里记录哪些人在里面，只需检查相邻格子中的人对，将 O(N²) 降为 O(N)。

| 方法 | 作用 |
|---|---|
| `init()` | 按截断距离将域划分为网格 |
| `build()` | 将所有粒子按位置分配到格子（计数排序，每步重建） |
| `for_each_pair()` | 遍历所有距离小于截断的粒子对，对每对执行回调（力计算、交换等均通过此接口） |

**热点路径**：`for_each_pair` 是整个模拟中调用最频繁的函数。

#### `decomposition.hpp/cpp` — MPI 2D 域分解

**物理含义**：将全局"世界地图"切割为 px×py 个子区域，每个 MPI 进程负责一个子区域内的所有人。当一个人走出自己所在的子区域时，通过 MPI 通信"迁移"到新进程。

| 方法 | 作用 |
|---|---|
| `init()` | 计算本 rank 的子域边界 |
| `owns()` | 判断一个位置是否在本 rank 的管辖范围 |
| `migrate_particles()` | 检测越界粒子 → pack → MPI_Sendrecv → unpack |
| `exchange_halos()` | 将边界附近的粒子副本发给邻居（用于跨域力计算） |
| `global_sum()` | MPI_Allreduce 求全局标量和（如总人口、总财富） |

---

### 3. `force/` — 力计算

> 势函数理论 → [[research-proposal#9.2 势函数设计（核心难点）]]

#### `social_force.hpp/cpp` — 人际空间交互力

**物理含义**：模拟人际吸引和排斥。借鉴 Lennard-Jones 势的数学形式，但命名和含义完全面向社会模拟。这是研究方案 §2.6 中"对称规则"的核心——规则本身不偏袒任何人，但结果是不对称的。

**公式**（借鉴 LJ 势数学形式）：
```
V(r) = 4ε [(σ/r)¹² − (σ/r)⁶]
F(r) = 24ε [2(σ/r)¹² − (σ/r)⁶] / r
```

| 代码符号 | 数学 | 社会类比 |
|---|---|---|
| `SocialForceParams::epsilon` | ε | 人际吸引强度——决定聚集的紧密程度 |
| `SocialForceParams::sigma` | σ | 人际"舒适距离"——聚居但不拥挤的平衡点 |
| `SocialForceParams::cutoff` | r_cut | 社交视野半径——超过此距离的人互不可见 |
| 排斥项 (σ/r)¹² | | 两人不能占同一位置，过近导致资源竞争 |
| 吸引项 (σ/r)⁶ | | 人是社会动物，倾向聚居合作 |
| `F_MAX` | | 力封顶：防止两人过近时数值不稳定 |
| `e_shift` | | 截断处能量平移：保证势能连续 |

**关键实现**：
- 使用 Newton 第三定律：`F_i = -F_j`，每对只计算一次
- 力封顶 `F_MAX=100`：防止初始化时偶然重叠的粒子对产生天文数字的排斥力

#### `terrain_force.hpp/cpp` — 地形外势

**物理含义**：模拟自然地理对人类活动的吸引——河谷/平原是势能低谷，山脉/沙漠是势能高地。人像球在碗里一样自然滚向低势区。

**公式**：
```
V(x,y) = -depth × exp(−(x−cx)²+(y−cy)²) / (2×width²))
F = −∇V = (depth/width²) × exp(...) × (x−cx, y−cy)   （指向势阱中心）
```

| 参数 | 物理含义 | 社会类比 |
|---|---|---|
| `depth` | 势阱深度 | 这片土地有多肥沃/宜居 |
| `width` | 势阱宽度 | 宜居区域有多大 |
| `cx, cy` | 势阱中心 | 河流/绿洲的位置 |

多个势阱 = 多条河谷 = 多个文明发源地。

#### `terrain_loader.hpp/cpp` — 真实地形数据加载器

**物理含义**：用真实 DEM（数字高程模型）替代理想化的高斯势阱，实现基于真实地理的模拟——真正让四大文明起源于大河流域。

| 组件 | 含义 | 作用 |
|---|---|---|
| `TerrainGrid` | 2D 高程网格 | 存储 row-major 高程数据 |
| `load_ascii()` | ESRI ASCII Grid 加载 | 标准 GIS 格式（.asc），自动处理 NODATA |
| `load_binary()` | Raw binary 加载 | float64 row-major，高性能批量数据 |
| `generate_synthetic()` | 合成地形 | valley/ridge/flat，用于测试和快速验证 |
| `elevation(x,y)` | 双线性插值 | 任意点高程查询，越界 clamp 到边界 |
| `gradient(x,y)` | 中心差分梯度 | ∇h，用于计算地形力 |
| `potential(x,y,s)` | 势能 | V = s × (h - h_min)，河谷 V=0，高山 V>0 |
| `force(x,y,s)` | 地形力 | F = -s × ∇h，指向低洼处（河谷吸引） |
| `compute_grid_terrain_forces()` | 批量力计算 | 替代 `compute_terrain_forces` |
| `grid_terrain_potential()` | 资源产出因子 | 河谷 < 0（肥沃），高地 ≈ 0 |

**配置**：`terrain_type=grid` + `terrain_file=xxx.asc` + `terrain_scale=1.0`

#### `river_field.hpp/cpp` — 河流走廊场

**物理含义**：将“河流”从粗尺度背景地形中拆出来，作为独立的 **RiverField** 接入。  
`TerrainGrid` 负责山脉/高原/平原等**障碍与背景势场**，`RiverField` 负责“靠近大河更高产、更易交换、更快传播”的**走廊效应**。这样可避免 DEM 粗化时把尼罗河谷、两河走廊等细结构抹平。

| 组件 | 含义 | 作用 |
|---|---|---|
| `RiverField` | 2D 河流场 | 当前以 `proximity` 为主，`discharge` 预留扩展 |
| `load_ascii()` | ASCII 加载 | 单波段 proximity；若存在第二波段则读为 discharge |
| `load_binary()` | Binary 加载 | float64 row-major |
| `generate_synthetic()` | 程序化主河网 | `major_rivers / nile / mesopotamia / china / europe / indus` |
| `proximity(x,y)` | 邻河强度 | [0,1]，越靠近主河道越大 |
| `corridor_bonus()` | 走廊增益 | 用于资源/交换/传播加成 |
| `gradient()/force()` | 弱河道引导 | 默认关闭，仅在 `river_force_enabled` 时使用 |

**当前耦合点**：

- `apply_resource_dynamics()`：`production *= 1 + s_r * proximity^alpha`
- `compute_carrying_capacity()`：`K *= 1 + s_K * proximity^beta`
- `exchange_resources()`：`dw *= 1 + s_e * min(proximity_i, proximity_j)`
- `evolve_technology()`：`spread_rate *= 1 + s_t * min(proximity_i, proximity_j)`
- `main.cpp` plague 分支：按平均 proximity 放大 `trigger_rate` 与 `infection_rate`
- `main.cpp` dynamics 分支：可选弱引导力 `river_force_enabled`

**配置**：`river_enabled=true` + `river_mode=procedural|file` + `river_*_strength`

---

### 4. `integrator/` — 时间积分

> 物理框架 → [[research-proposal#三、物理框架：Langevin-跳跃扩散社会动力学]]
> Langevin 噪声分布 → [[docs/stochastic-distributions#1. 运动方程 — Langevin 噪声]]

#### `langevin_integrator.hpp/cpp` — BBK Langevin 积分器

**物理含义**：求解 Langevin 方程的数值方法。BBK (Brünger-Brooks-Karplus) 积分格式将每一步分为 5 个子步骤，是 Velocity-Verlet 的随机力推广。

**BBK 算法步骤**（对应代码中的 Step 1-6）：

```
Step 1: 半步动量更新
  p_{n+1/2} = p_n + (dt/2) × F_n − (dt/2) × γ × p_n + σ√(dt/2) × R_n
  ↑确定性力推动  ↑耗散（摩擦减速）  ↑随机力（布朗运动）

Step 2: 全步位置更新
  x_{n+1} = x_n + (dt/m) × p_{n+1/2}
  ↑按新动量移动

Step 3: 边界条件
  如果粒子越界，反弹回来（反射边界）

Step 4: 重新计算力
  F_{n+1} = Force(x_{n+1})   （在新位置上算所有力）

Step 5: 第二次半步动量更新
  p_{n+1} = p_{n+1/2} + (dt/2) × F_{n+1} − (dt/2) × γ × p_{n+1/2} + σ√(dt/2) × R_{n+1}

Step 6: 计算动能
  KE = Σ p²/(2m)
```

| 参数 | 物理含义 | 社会类比 |
|---|---|---|
| `γ` (friction) | 摩擦系数 | 制度腐化速率、知识遗忘率 |
| `T` (temperature) | 温度 | 社会动荡程度——高温=乱世，低温=治世 |
| `σ = √(2γmkT)` | 噪声幅度 | 随机事件的强度（满足涨落-耗散关系） |
| `mass` | 粒子质量 | 个体惯性——改变状态的阻力 |

**关键性质**：
- γ=0, T=0 时退化为确定性 Velocity-Verlet（能量守恒）
- γ>0, T>0 时系统趋向热平衡：⟨KE⟩ = N·T（均分定理）
- 涨落-耗散关系 `σ² = 2γmkT` 保证热力学自洽

---

### 5. `interaction/` — 个体间交互

> 涌现方法论 → [[research-proposal#2.6 涌现方法论：对称规则，不对称结果]]
> 技术演化分布 → [[docs/stochastic-distributions#5. 技术演化 — Lévy-type Jump-Diffusion]]
> 忠诚度/征服分布 → [[docs/stochastic-distributions#6. 社会动力学]]

#### `resource_exchange.hpp/cpp` — 资源交换

**物理含义**：模拟人与人之间的经济交互（贸易、竞争、掠夺）。这是研究方案 §2.6.2 的核心——**规则对称，结果不对称**。

**交换公式**：
```
A_i = w_i × ε_i          （能力 = 财富 × 技术）
Δw = η × (A_i − A_j) / (A_i + A_j) × min(w_i, w_j)
```

| 项 | 含义 |
|---|---|
| `A_i` | 个体 i 的"综合能力"——财富和技术的乘积 |
| `(A_i−A_j)/(A_i+A_j)` | 能力差的归一化度量，∈(-1,1)，**标签互换时符号反转=对称** |
| `min(w_i,w_j)` | 交换量受较穷者限制——你不能从穷人那里拿走他没有的 |
| `η` | 交换率——每次交互转移多少比例的资源 |

**关键性质**：如果 i 和 j 标签互换，Δw 变号——规则完全对称。但如果 A_i > A_j（i 更强），则 Δw > 0（i 获益），不平等自然放大。

#### `apply_resource_dynamics()` — 资源消耗与产出

```
dw = R(x) × ε × dt − consumption × dt
```

- 每步每人消耗固定量（"吃饭"成本）
- 在地形势阱处获得资源（`-V(x)` 越大=土地越肥沃，产出越多）
- 产出受 ε 调制——技术越高，同一块土地的产出越多

#### `apply_survival_threshold()` — 饥饿死亡

`w < threshold → mark_dead()`。资源低于生存线的人死亡——这是人与分子的本质区别之一。

#### `culture_dynamics.hpp/cpp` — 文化动力学

**物理含义**：模拟文化的传播和同化。文化向量 c⃗ 是 d 维向量，其**模**代表知识量，**方向**代表文化取向。

| 函数 | 物理含义 |
|---|---|
| `culture_distance()` | 两人的文化差异——欧几里得距离 \|c⃗_i − c⃗_j\| |
| `culture_force_modifier()` | 文化对空间交互的调制：相似→吸引，不同→排斥 |
| `evolve_culture()` | 文化同化：近邻的文化向量互相趋同（扩散过程） |
| `compute_culture_order_param()` | 文化序参量 Q = \|⟨ĉ_i⟩\|：Q≈0 多样，Q≈1 统一 |
| `compute_culture_correlation()` | 文化空间关联：距离 r 处的文化余弦相似度 |

**同化机制**：
```
Δc⃗_i = rate × exp(−|c⃗_i−c⃗_j|²/(2σ²)) × (c⃗_j − c⃗_i) × dt
```
同化强度随文化距离指数衰减——已经相似的文化更容易进一步融合，非常不同的文化几乎不互相影响。

#### `tech_spread.hpp/cpp` — 技术演化

**物理含义**：模拟能量利用能力 ε 的三重演化机制（研究方案 §2.4）。

| 机制 | 公式 | 社会类比 |
|---|---|---|
| 缓慢漂移 | `dε = α·\|c⃗\|·ε·dt` | 知识驱动的渐进改良（马太效应） |
| 接触传播 | `Δε = rate × (ε_j − ε_i) × dt` | 高技术者教低技术邻居 |
| Poisson 跳跃 | `prob = λ·(1+κ\|c⃗\|)·dt → ε += Δε·ε` | 技术突破（火、冶铁、蒸汽机） |
| 财富正跳跃 | `prob = λ+ → w += fraction·w` | 运气好（发现矿藏、意外继承） |
| 财富负跳跃 | `prob = λ- → w -= fraction·w` | 运气差（被抢劫、火灾） |

---

### 6. `population/` — 人口动力学

> 理论模型 → [[research-proposal#2.5 人口动力学：繁殖模型]]
> 生育/死亡分布 → [[docs/stochastic-distributions#3. 死亡机制]] · [[docs/stochastic-distributions#4. 生育]]

#### `reproduction.hpp/cpp` — 繁殖

**物理含义**：模拟人类生育。每对近邻在满足五个条件时有概率产生后代。

**生育能力曲线 `fertility(age)`**：
```
φ(a) = φ_max × Beta(t; α, β)    当 a ∈ [a_puberty, a_menopause]
φ(a) = 0                         否则
```
钟形曲线：15 岁性成熟后上升，25 岁达峰，45 岁绝育。

**五个交配条件**：
1. 空间距离 < mate_range（要近）
2. 双方存活且可生育年龄
3. 妊娠+哺育冷却期已过（≈2.75年/胎）
4. 文化兼容：\|c⃗_i − c⃗_j\| < threshold
5. 双方财富 > 最低生育门槛

**后代遗传**：
- 位置：父母中点 + 小扰动
- 文化：父母均值 + 变异（跨文化婚姻→文化融合）
- 技术：取父母较高者（技术只会向上兼容）
- 财富：从父母扣除一部分

#### `mortality.hpp/cpp` — 死亡

**物理含义**：四重死亡机制（研究方案 §2.3）。

| 机制 | 公式 | 含义 |
|---|---|---|
| 衰老 | `P = α·exp(β·age)·dt` | Gompertz 法则：死亡率随年龄指数增长 |
| 饥饿 | `P = sigmoid(w, threshold)·dt` | 资源低于阈值时急剧增加 |
| 意外 | `P = λ_accident·dt` | 常数概率，与年龄和财富无关（"命运"） |
| 年龄上限 | `age > max_age → 死亡` | 硬性寿命上限 |

**生产力曲线 `productivity_factor(age)`**：
```
高斯钟形：0岁=0，15岁渐增，30岁峰值，之后衰退
```
调制有效劳动产出——壮年最强。

#### `carrying_capacity.hpp/cpp` — 密度承载力（Phase 23）

**物理含义**：马尔萨斯反馈——人口密度不能无限增长，受限于土地承载力。

| 函数 | 说明 |
|---|---|
| `compute_local_density()` | 利用 CellList 邻居计数估算局部人口密度 ρ(x_i) = N_neighbors / (πr²) |
| `compute_carrying_capacity()` | 局部承载力 K(x) = carrying_capacity_base × max(0, −V(x))；V 越负（河谷）K 越高 |
| `density_suppression()` | 抑制因子 max(0, 1 − ρ/K)；ρ ≥ K 时返回 0 |

**作用机制**：
- **生育抑制**：fertility × min(suppress_i, suppress_j)，密度达到承载力时生育率归零
- **资源竞争**：production × min(1, K/ρ)，拥挤时人均产出下降
- **ε 突破打破天花板**：技术提升 → 产出增加 → 等效 K 提升 → 新一轮人口增长

---

### 7. `analysis/` — 序参量与观测

> 序参量定义与物理含义 → [[research-proposal#六、观测量与序参量：如何检测阶级和制度的涌现]]
> 分析管线 → [[research-proposal#7.8 完整的分析管线]]

#### `order_params.hpp/cpp` — 基础序参量

| 函数 | 物理含义 | 数学定义 |
|---|---|---|
| `compute_gini()` | Gini 系数——不平等程度 | G=0 完全平等，G=1 完全不平等 |
| `compute_wealth_stats()` | 财富统计 | 均值、中位数、标准差、极值 |
| `compute_wealth_histogram()` | 财富分布 P(w) | 观察是否从指数分布转变为幂律分布 |

#### `network_analysis.hpp/cpp` — 交互网络分析

**物理含义**：检测层级是否从对称交互中涌现（研究方案 §2.6.4）。不预设层级存在，而是从资源流动模式中**事后检测**。

#### `polity.hpp/cpp` — 政体检测与分类（Phase 21）

**物理含义**：从个体级层级树自动检测宏观政治实体（类似相变中识别有序域）。

| 函数/结构 | 说明 |
|---|---|
| `PolityType` | 枚举：Band/Tribe/Chiefdom/State/Empire |
| `PolityInfo` | 单个政体的聚合统计（人口、深度、财富、领土、质心） |
| `detect_polities()` | 遍历层级树连通分量，分类并统计每个政体 |
| `classify_polity()` | 按人口+层级深度分类：<50=Band, <300=Tribe, <1000=Chiefdom, <5000=State, ≥5000=Empire |
| `detect_polity_events()` | 对比前后两步政体集合，检测形成/合并/分裂/崩溃事件 |
| `PolitySummary` | 全局统计：政体数、各类型数、HHI 集中度、最大政体规模 |

| 类/函数 | 物理含义 |
|---|---|
| `InteractionNetwork` | 记录每对粒子间的净资源流动量 |
| `build_dominance_graph()` | 从净流动中提取"事实支配关系"——如果 i 持续从 j 获取资源，则 i 支配 j |
| `compute_hierarchy_metrics()` | 计算层级指标：深度 H、分支因子 B、最大分量比 F、实体数 C |
| `compute_effective_power()` | 有效权力 Power_i = 子树中所有人的财富之和 |

**层级指标的社会含义**：

| 指标 | 含义 | 什么值说明什么 |
|---|---|---|
| `H` (max_depth) | 层级深度 | 0=无层级，5+=官僚帝国 |
| `C` (n_components) | 独立政治实体数 | C=1 天下一统，C=多 诸侯并立 |
| `F` (largest_fraction) | 最大实体占比 | F>0.7 统一帝国 |
| `Ψ` (psi) | 分封-集权度 | Ψ≈1 分封制，Ψ≈0 郡县制 |
| `power_gini` | 权力集中度 | 高=权力集中于少数人 |

#### `perf_monitor.hpp/cpp` — 性能监控与负载均衡

**物理含义**：大规模并行模拟中，各 MPI rank 的计算负载可能因人口分布不均（城市密集/海洋稀疏）而失衡。PerfMonitor 负责检测这种失衡并自动触发 SFC 重平衡。

| 组件 | 含义 | 作用 |
|---|---|---|
| `Phase` 枚举 | 9 个计算阶段 | Dynamics/Exchange/Culture/Technology/Resources/Population/Migration/Analysis/IO |
| `start(p)/stop(p)` | 阶段计时 | 高精度 `steady_clock` 分段测量 |
| `step_compute()` | 计算耗时 | 排除 IO（IO 仅 rank 0 执行，不代表计算负载） |
| `LoadReport` | 全局负载报告 | MPI_Allreduce 汇总 max/min/avg 耗时和粒子数 |
| `efficiency` | 并行效率 | avg/max，理想值 100%，< 50% 触发自动重平衡 |
| `needs_rebalance` | 自动重平衡标志 | 效率低于阈值时设为 true |
| `format_report()` | 格式化报告 | 人类可读的负载状态输出 |
| `format_breakdown()` | 阶段分解 | 各阶段占比，定位性能瓶颈 |

---

### 8. `io/` — 输入输出

#### `csv_writer.hpp/cpp` — 数据输出

- `write_positions()`: 每隔 N 步输出粒子位置快照（用于可视化动画）
- `write_energy()`: 每步输出能量时间序列（动能、LJ 势能、地形势能、总能量）

---

### 9. `main.cpp` — 主驱动程序

**一个时间步的完整流程**（对应研究方案中的模拟循环）：

```
for step = 1 to total_steps:
    1. Langevin 动力学  → 更新位置和动量（物理运动）
    2. 资源交换        → 邻居间转移财富（经济交互）
    3. 文化演化        → 邻居间文化同化（文化扩散）
    4. 技术演化        → ε 漂移+传播+Poisson 跳跃（技术进步）
    5. 资源产出/消耗   → 从地形获取食物，扣除生活成本
    6. 人口动力学      → 年龄推进 + 四重死亡 + 繁殖
    6b.层级动力学      → 忠诚度演化 + 叛乱/投靠 + 税收 + 依附形成 + 征服
    7. MPI 粒子迁移    → 越界粒子发送到邻居进程（含 gid/superior/loyalty）
    8. 定期压缩        → compact_with_map + rebuild_gid_map（全局 ID 不变，重建查找表）
    9. 序参量输出      → Gini, Q, H, C, F, Ψ, ⟨ε⟩, ⟨L⟩, Gini(Power)
```

---

### 9b. `interaction/loyalty.hpp/cpp` — 依附关系与忠诚度系统

对应研究方案 §2.3 "阶段4"：在涌现被确认后引入显式层级机制。

| 函数/结构体 | 物理/社会含义 |
|---|---|
| `LoyaltyParams` | 忠诚度系统参数集：保护增益α、税收消耗β、文化惩罚γ、噪声σ、叛乱/投靠阈值 |
| `form_attachments()` | 从交互网络的支配图检测稳定单向资源流，建立 superior 依附（存全局 ID） |
| `evolve_loyalty()` | L_ij 演化方程：dL/dt = α·protection − β·tax − γ·\|c⃗_i−c⃗_j\| + η(t) |
| `process_loyalty_events()` | 叛乱（L < 0.1→断裂）、投靠（L < 0.2→转移到更强根节点） |
| `apply_taxation()` | 上级从下属提取税收，财富向上流动 |
| `compute_effective_power()` | Power_i = Σ w_j × L_path(i,j)，沿依附链累乘忠诚度 |
| `attempt_conquest()` | Power_i > 1.5×Power_j 时概率征服邻近根节点 |
| `repair_superior_after_compact()` | compact 后清理无效 superior（全局 ID 不需索引映射） |

**世袭继承**（Phase 14）：

| 函数 | 物理/社会含义 |
|---|---|
| `process_succession()` | 领主死亡 → 选继承者（wealth×loyalty最高）→ 遗产分配 → 下属转移 |
| `inherit_hierarchy()` | 新生儿自动归入父母所属层级（"生在帝王家"） |

**社会类比**：
- `superior(i)` = 封建领主/部落首领（存全局 ID，跨 MPI rank 稳定）
- `global_id(i)` = 粒子的全局唯一身份标识
- `loyalty_i` = "忠诚度" / "合法性认同"
- `Power_i` = 有效权力（可调动的资源 × 忠诚度衰减）
- 叛乱 = "王侯将相宁有种乎"
- 投靠 = 良禽择木而栖
- 征服 = 以力服人
- 文化距离降低忠诚度 = 异族统治天然不稳定
- 世袭 = "父死子继"，继承者忠诚度冲击 = 新君继位的"考验期"
- 新生儿继承层级 = 封建社会中的出生决定身份

---

### 10. `scripts/` — Python 分析工具

| 脚本 | 功能 |
|---|---|
| `visualize.py` | 粒子位置动画（支持 GIF 导出） |
| `plot_timeseries.py` | 解析控制台日志，绘制 N, Gini, Q, ε, H 时间序列 |
| `plot_distributions.py` | 分析仪表盘：能量、空间分布、人口动态 |
| `param_scan.py` | (T, scale) 参数空间扫描：自动生成配置、运行模拟、收集全部序参量 |
| `plot_phase_diagram.py` | 从扫描结果绘制 2D 相图（Gini, Q, H, N, F, Ψ, ⟨L⟩, Gini(Power), C 九面板热力图） |
| `scaling_test.py` | 自动化 weak/strong scaling 测试：多进程 × 多重复 × 取中位数 |
| `plot_scaling.py` | Scaling 结果可视化：speedup 曲线 + 并行效率柱状图（strong + weak） |
| `plot_snapshot.py` | 粒子快照6面板可视化：财富/层级/忠诚度/技术/权力/文化 |
| `plot_order_params.py` | 从 `order_params.csv` 绘制序参量时间序列（比 log 解析更可靠） |
| `plot_terrain.py` | 合成地形可视化（单类型/全类型对比）：海拔图 + 资源产出图 + 粒子叠加 |
| `plot_polities.py` | 政体分析5面板可视化：类型组成、HHI、最大政体、事件时间线、空间地图 |

---

### 11. 合成地形系统（Phase 19）

`terrain_loader.cpp` 中的 `generate_synthetic()` 支持五种合成地形类型：

| 类型 | 对应地理原型 | 特征描述 |
|---|---|---|
| `valley` | 中央低洼 | 中心低、四周高的碗状地形 |
| `ridge` | 中央山脊 | 中心高、四周低的山丘 |
| `river` | 黄河/尼罗河/两河流域 | 蜿蜒河谷贯穿左右，两侧高地；模拟"依水而居"的文明模式 |
| `basins` | 关中/中原/巴蜀/东北 | 4个独立低洼盆地被山脊分隔；模拟"诸侯割据"的地理基础 |
| `continent` | 大陆+海洋 | 海洋（高势垒）环绕大陆，内有山脉和平原；模拟"大陆文明" |

配置文件通过 `terrain_type = river/basins/continent` 选择合成地形，无需外部 DEM 文件。

### 12. RiverField 河流走廊系统

第一版 `RiverField` 与 `terrain_type = river` 不是一回事：

- `terrain_type = river`：**合成地貌模板**，把“河谷”作为一张高程地形。
- `river_*`：**独立河流水系场**，把“近河走廊效应”直接接到资源、承载、交换、技术传播与瘟疫。

推荐理解：

- **地形**回答“哪里难过去、哪里是背景势垒”
- **河流**回答“哪里更适合聚居、交换和传播”

典型配置：

```ini
river_enabled = true
river_mode = procedural
river_type = major_rivers
river_resource_enabled = true
river_capacity_enabled = true
river_exchange_enabled = true
river_tech_enabled = true
river_plague_enabled = false
river_force_enabled = false
```

新增可配置参数：
- `base_production` — 控制地形产出系数
- `max_fertility` — 最大生育概率
- `tax_rate` — 层级税率（影响附庸财富流失速度）
