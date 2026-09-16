# AR-Politeia 实际模型规范与因果结构（Cycle 4）

日期：2026-09-16。性质：**模型写实文档**，不产生新数值证据。处置 `simulator-improvement-plan.md`
中的 S01（P0，财富反馈缺失）与 S09（P1，source–sink 组合因子），并交付 WP0 §3.2/§3.3 的两项产物：
当前因果图、旧结论处置表。

本文件的每一条机制描述都对应活动源码，并给出文件与行号锚点。描述对象是 **Cycle 4 修复后的
受控参考配置**（单 rank、`confirmative_mode`、`strict_numerics`、`OMP=1`），不是完整模型的全部
分支。完整人口模型、MPI、restart 的适用性见 §8。

## 1. 版本锚点

| 项 | 值 |
|---|---|
| 源码 commit | `8d3e3fc`（= V1F 执行所在 checkout） |
| 受控实验 ID | `V1F-NONFLAT-CALIBRATION-C4`（进行中）；`E1-MATCHED-LANDSCAPES-C4`（未授权） |
| 参数锁 | Cycle 4 最终锁尚未生成；当前仍为 Cycle 3 锁 `ar-politeia-cycle3-confirmatory-v3` |
| 参考执行模式 | `nprocs=1`、`OMP_NUM_THREADS=1`、`confirmative_mode=true`、`strict_numerics=true` |

本文件在 Cycle 4 最终参数锁冻结后必须复核一次：若 `model-specification` 与锁内参数不一致，
以锁为准，并更新本文件而不是反过来改锁。

## 2. 状态变量

每个粒子携带以下量（`core/particle_data.hpp`）：

- `x = (x, y)`：连续空间位置，域为 `[xmin,xmax] × [ymin,ymax]`，受控配置为 `[0,100]²`；
- `p = (px, py)`：动量；
- `w`：财富；
- `eps`（ε）：能力/技术水平，受控配置下由 `initial_wealth_log_sigma` 之外的
  `epsilon_log_sigma` 抽样，**在本周期内不演化**（`technology_enabled=false`）；
- `age`、`sex`、`culture[d]`、`gid`（稳定全局 ID）、`status`（Alive/Dead）。

**因果相关的关键事实**：受控配置下主导状态是 `(x, p, w, eps)`。`eps` 是初值给出的**固定异质性**，
它同时进入财富交换（§5.4）与财富生产（§5.5），因此 `eps` 是财富过程的共同原因，
也是"能力—财富"相关性的来源，而不是被财富反向影响的变量。

## 3. 单步更新流水线（`src/main.cpp:643` 起）

受控配置下每一步按固定顺序执行以下阶段。开启的模块加粗；关闭的模块列出以便界定适用边界。

| # | 阶段 | 受控配置 | 源码锚点 |
|---|---|---|---|
| 1 | Langevin 积分（含力、边界、摩擦、噪声） | **开** | `langevin_integrator.cpp:96` |
| 2 | 河流力、气候摩擦 | 关 | `main.cpp:664`、`main.cpp:677` |
| 3 | 更新局地地形势、河流场缓存 | **开**（地形） | `main.cpp:693` |
| 4 | Berendsen 温控速度缩放 | **开** | `main.cpp:701` |
| 5 | 邻域资源交换 | **开** | `resource_exchange.cpp:74` |
| 6 | 文化同化 | 关 | `main.cpp:766` |
| 7 | 技术演化 | 关 | `main.cpp:773` |
| 8 | 局地密度、承载力、气候产出调制 | 关/开（无气候） | `main.cpp:791` |
| 9 | 资源生产 − 消费 − 衰减 | **开** | `resource_exchange.cpp:221` |
| 10 | 全粒子状态校验（`strict_numerics`） | **开** | `main.cpp:870` |
| 11 | 年龄、死亡、瘟疫、繁殖 | 关 | `main.cpp:877` |
| 12 | MPI 迁移 | 单 rank 下无操作 | `main.cpp:1013` |
| 13 | 周期压缩 + SFC 重平衡 + 邻域重发现 | **开** | `main.cpp:1021` |
| 14 | 快照输出 | **开** | `main.cpp:1076` 起 |

**顺序本身是模型的一部分**：第 5 步交换在第 9 步生产之前，同一粒子的财富在一步内先被交换
再被生产/衰减影响；第 1 步的力使用第 4 步温控之前的位置与动量。改变顺序即改变模型，
必须作为新模型版本声明，不能当作实现细节。

## 4. 空间动力学写实（第 1、3、4 步）

### 4.1 积分格式

采用 BBK（Brünger–Brooks–Karplus）两步半步踢 + 一步漂移（`langevin_integrator.cpp:96-201`）：

```
p_{n+1/2} = p_n     + (dt/2)·[F_n − γ·p_n/m] + σ·sqrt(dt/2)·R_n
x_{n+1}   = x_n     + (dt/m)·p_{n+1/2}
F_{n+1}   = Force(x_{n+1})
p_{n+1}   = p_{n+1/2} + (dt/2)·[F_{n+1} − γ·p_{n+1/2}/m] + σ·sqrt(dt/2)·R_{n+1}
```

`σ = sqrt(2·γ·m·T)`（`m = 1`，`k_B = 1`），因此每个半步的噪声幅度为
`sqrt(γ·m·T·dt)`。当 `T = 0` 或 `γ = 0` 时 `σ = 0`，退化为 Velocity-Verlet
（`langevin_integrator.cpp:34-41`）。S06 修复后，**无噪声分支仍然施加摩擦项**
（`langevin_integrator.cpp:134-143`、`langevin_integrator.cpp:183-189`），
OpenMP OFF/ON 两条路径的半步更新公式一致。

### 4.2 力的组成

```
F_i = F_social,i + F_terrain,i
```

- `F_social` 由 `social_strength` 与 `social_distance` 控制，**只读位置**（`force/social_force.cpp`）；
- `F_terrain` 由地形势的负梯度给出，`terrain_force_scale` 缩放（`force/terrain_force.cpp`）；
- 受控配置 `social_strength = 0`，因此**这一步的力完全由外场地形给出**。

`grep` 核实：`force/` 与 `langevin_integrator.hpp` 中**不出现 `wealth`、`w_data`、`eps_data` 的任何读取**。
即运动方程 `(x, p)` 的右端不含 `w`。

### 4.3 边界条件

反射边界（`langevin_integrator.cpp:82-94`）：越界坐标镜像回域内，对应动量分量取反。
这是**弹性反射**，因此域边界本身不耗散也不注入动量；域内粒子数守恒由人口模块关闭保证。

### 4.4 温控（Berendsen 速度缩放）

`temperature > 0` 时，每步检查 `ke_ratio = KE / (N·T)`（2D 等分能量 `N·k_B·T`），
仅当 `ke_ratio > 1.2` 时触发（`main.cpp:719`）：

- 常规修正：`lambda = sqrt(1 + (dt/τ_T)·(1/ke_ratio − 1))`，`τ_T = 0.1`，并夹紧到 `lambda ≥ 0.9`
  （单步最多移除 10% 速度幅度）；
- 强修正：若 `ke_ratio > 2.0`，改用 `lambda = sqrt(1/ke_ratio)`，即**直接把动能拉回目标值**。

这是**对实际过程的介入**，不是纯 Langevin 动力学：受控配置下 `T = 0.5 > 0` 且 `γ = 1 > 0`，
所以温控路径始终处于激活状态，只要动能漂移到目标值的 1.2 倍以上就会被缩放。
诊断输出 `trigger_count`、`max_correction`、`ke_removed`、pre/post 动能写入分窗口 `health.json`
（`main.cpp:1289` 起）。**首次 V0/V1F 实测：`trigger_count = 0`**，即当前参数域内温控从未触发；
这是"当前参数下无介入"的实测证据，不是"机制不存在"的证明。判断依据为 V1F 已完成 run 的
`health.json`。

注意 `V1F` 矩阵的两层结构在这一条上不同：`timestep` 层（smooth/clustered/shuffled × 三级步长）
使用 `temperature = 0.5`，温控路径激活；`order` 层（存储顺序诊断）显式设 `temperature = 0.0`
并给 `initial_temperature = 0.5`，因此**温控在该层完全不参与**，只剩摩擦项。
两层不可互相引用结论。

### 4.5 已确认未接入的路径

- `SFCDecomposition::exchange_halos` 与 `DomainDecomposition::exchange_halos` **在 `main.cpp` 中
  没有任何调用点**（`grep` 核实：仅在定义处出现）。`main.cpp:578/1063` 只调用
  `discover_neighbors`，它缓存邻居 rank 列表，不注入 ghost 粒子。因此**多 rank 下跨 rank 的力、
  交换与密度计算会漏掉真实邻居**。受控配置以 `nprocs=1` 规避，`confirmative_mode` 显式拒绝
  `nprocs>1`（`main.cpp:84-89`）。
- 邻域 `CellList` 的 cell 尺寸只取 `max(interaction_range, density_radius, exchange_cutoff)`
  （`main.cpp:245-252`）。繁殖的 `mate_range` 与瘟疫的 `infection_radius` **不在其中**；
  受控配置这两个模块关闭，因此不构成当前缺陷，但恢复完整模型前必须补。

## 5. 财富动力学写实

### 5.1 邻域与配对枚举

`CellList::for_each_pair`（`domain/cell_list.hpp:64-121`）：

- 按 `(cy, cx)` 行主序遍历 cell，cell 内按计数排序后的插入序遍历；
- 同 cell 内取 `ii < jj`；跨 cell 只取 4 个前向邻居偏移 `(1,0),(0,1),(1,1),(-1,1)`，
  统一规范化为 `i < j` 后调用；
- 距离判据 `r2 < cutoff² 且 r2 > 0`——**严格重合的粒子对被排除**，不产生交换。

由于 cell 尺寸 ≥ cutoff，3×3 搜索保证覆盖半径 cutoff 内的全部邻居（对 `for_neighbors_of`）；
`for_each_pair` 用前向半邻域等价枚举。**每对每步只被处理一次**。

### 5.2 交换规则（候选 C，连续时间均分回复再分配）

对满足条件的每一对 `(i, j)`，记 `total = w_i + w_j`，`share = w_i / total`：

```
A_i     = ε_i · w_i / (w_i + w_ref)           若 ability_saturation_w > 0
        = w_i · ε_i                           否则
A_j     = 同理
D_ij    = (A_i − A_j) / (A_i + A_j)
share'  = share + dt·[k·(1/2 − share) + η_d·D_ij] + sqrt(dt)·η_n·|D_ij|·s_ij
w_i'    = share' · total
w_j'    = total − w_i' = (1 − share') · total
```

其中 `k` 为回复率（`exchange_reversion_rate`）、`η_d` 为能力漂移率（`exchange_rate`）、
`η_n` 为噪声强度（`exchange_noise_strength`）。受控配置（`V1F/config.json`）为
`k = 1`、`η_d = 0.5`、`η_n = 0.05`；`w_ref = ability_saturation_w` 未在**作业级** config 中给出，
取编译期默认值 **5.0**（`core/config.hpp:52`）。每个 run 生成的 `politeia.cfg` 会由
`common_cpp_config` 显式写入该值（`run_landscape_study.py:344`），所以**逐 run 有记录**，
不存在隐式默认值漂移；但作业 config 里看不到它，审查需下钻到 run 级 cfg。
配置的平均财富 `mean_wealth = 5` 恰好等于 `w_ref`，因此 `use_saturation = true`，
设计意图是让能力函数在初值处处于半饱和点——但实测平衡水平远低于该点（见 §5.8），
这个偏离会改变 ε 异质性的转化效率，所以 `w_ref` 不是数值细节而是机制参数。
交换 cutoff 未显式给出（`exchange_cutoff = -1`），回退为 `interaction_range = 2.5`。

性质：

1. **零和且逐对非负**：`w_i' + w_j' = total` 恒成立；`share'` 被夹紧到 `[0,1]`，
   所以两个端点都不会变负。这取代了候选 B 的 `dw_buf` 累积路径（该路径曾产生负财富）。
2. **标签对称**：把 `i ↔ j` 互换，`D → −D`、`s → −s`、`share → 1−share`，结果只变符号，
   因此规则本身不偏袒任何一方；不平等只来自状态差异。
3. **扰动 ∝ total**：不同于旧核 `Δw ∝ min(w_i,w_j)`，财富悬殊时涨落仍然有效，
   这是"漂移—扩散平衡产生非平凡稳态"的机制来源。
4. **漂移 O(dt)、涨落 O(sqrt(dt))**，因此是连续时间过程的离散化。

### 5.3 边界政策、夹紧与诊断（S02）

`resource_exchange.cpp:130-151` 的判定顺序被刻意固定为：

1. `!isfinite(w)` 或 `!isfinite(eps)` → 计入 `nonfinite_encounters` 并跳过（NaN 与 `Inf` 的比较
   不会自动触发 `<`/`<=` 分支，必须先判有限性）；
2. 任意 `w < 0` 或 `eps < 0` → 计入 `negative_wealth_encounters` 并跳过（**在零总额分支之前**，
   所以 `(−2,1)`、`(−1,−1)` 不会被静默跳过）；
3. `total <= 0` → 无操作（唯一被允许的早退）；
4. **单个零端点是允许进入交换的**（S02 修复）。`(−,0)` 与 `(0,+)` 可以发生财富回流，
   因为 `share ∈ [0,1]` 保证两端合法；
5. 能力之和 `< 1e-15` → 计入 `degenerate_ability_encounters` 并跳过。

夹紧事件（`share` 撞到 0 或 1）计入 `clamp_events`。`active_pairs` 记录**进入更新的 pair
数（含 `dw = 0`）**，`nonzero_transfer_pairs` 才记录实际发生转移的对数——两者不可混用。

**S02 的残余限制（必须随结论一起声明）**：修复后的政策是"**允许**零财富端点回流"，
不是"**保证**回流"。在锁定参数 `k = 1`、`η_d = 0.5` 下，单零端点 `D = −1` 时确定性漂移
恰为 `k/2 − η_d = 0`，是否离开边界取决于噪声与截断。因此"破产吸收"与"自动恢复"两种
叙事都不能由代码直接推出，只能由边界驻留统计（§7）判定。

### 5.4 交换的随机来源（S07）

符号 `s_ij` 不是状态化随机流，而是**确定性哈希**（`resource_exchange.cpp:58-69`）：

```
s_ij = ±1,  由 splitmix64( (seed ⊕ stream) , lo(gid), hi(gid), step ) 的最低位决定
seed      = cfg.random_seed ⊕ EXCHANGE_STREAM_ID
stream    = 0x9e3779b97f4a7c15
```

关键性质：

- 用**稳定全局 ID** `(gid_i, gid_j)` 而不是数组下标，因此**存储重排、迁移、重启后逐对随机
  定义不变**；
- 构造上反对称（`s(i,j) = −s(j,i)`），因此 `for_neighbors_of` 从两端访问也保持严格零和；
- 混入 `base_seed`，所以**不同 `replicate_seed` 会独立重采样交换流**（修复前交换噪声不含 seed）；
- 依赖 `step`，因此同一步内 `|D|` 相同的对不同符号；跨步序列由哈希给出，不是独立同分布抽样。

交换使用的是**独立子流**，与运动的 `mt19937_64` 流和人口流互不干扰。

### 5.5 更新顺序（S08）

交换核是**串行原地更新**（`for_each_pair` + 立即写回 `w[i]`、`w[j]`），不是同步 `dw` 累加。
因此当某粒子参与多对交易时，**后处理的 pair 看到的是前一个 pair 已修改的财富**，
最终结果依赖枚举顺序。这是有限步长下的顺序效应，不是 bug，但必须被量化：

- V1/V1B/V1C 的"三级步长 × 完整相态重排"诊断已给出存储顺序误差界，且**在当前参数域内
  低于冻结的数值分辨率上限**；
- 反向结论同样重要：早期版本的"多粒子原地交易对存储重排逐粒子完全不变"这一要求
  **已被实测否定**，稳定 GID 只固定随机抽样，不能消除非交换的顺序更新效应。
  该反例记录在 `simulator-remediation-status.md` §4.2。
- **扩大参数域必须重新校准该界**。

### 5.6 生产—衰减（S09 的核心）

`apply_resource_dynamics`（`resource_exchange.cpp:221-261`）同一循环内施加三项：

```
local_resource = base_production · terrain_production_scale · max(0, −V(x_i))      若地形产出启用
                 × (1 + river_resource_strength · prox^alpha)                      若河流产出启用
production     = local_resource · ε_i · dt
consumption    = consumption_rate · dt
decay          = wealth_decay_rate · max(0, w_i) · dt
w_i           += production − consumption − decay
```

受控配置：`base_production = 0.01`、`terrain_production_scale = 1`、`consumption_rate = 0`、
`wealth_decay_rate = 0.02`。

**这就是 S09**：单一 `terrain_production_enabled` 开关**同时**控制局地源项与（通过
`max(0,−V)` 的景观依赖）衰减背景下的净收支，`off` 条件等价于"关掉源项、保留衰减"。
因此该因子是**生产—衰减组合通道（source–sink bundle）**，不是"纯生产"。
本周期内所有涉及该开关的效应必须按组合通道命名与解释，禁止写成"生产效应"。

另外注意 `decay` 与 `max(0, w_i)` 的关系：`w_i` 为 0 时衰减项为 0，因此衰减**不会**把财富推成负值；
负财富只能由非法输入或其它模块产生，`strict_numerics` 会在第 9 步后立刻校验并失败。

### 5.7 ε 的双重角色

`ε_i` 同时出现在：

- 交换能力 `A_i = ε_i·w_i/(w_i+w_ref)`（§5.2）——决定谁在交易中占优；
- 生产 `production = local_resource·ε_i·dt`（§5.6）——决定同一块土地的产出放大倍数。

这在 Cycle 1 假说 H2 中被称为"生产通道"，但严格说它同时是**交换通道的异质性来源**。
所以"地形拓扑效应"与"能力异质性效应"在机制上不可由单一 ε 开关分离；分离需要单独的
ε 同质化对照，属未开展设计。

### 5.8 参考过程的实际工作点（2026-09-16 实测）

对 V1F（`dt = 0.005`、力开启、`d = 0.02`、`base = 0.01`）已完成 run 的尾帧逐 run 计算平均财富，
59 对 seed 的结果：

| 条件 | 平均财富 | `w/w_ref` | `min wealth` |
|---|---:|---:|---:|
| clustered | 1.9838 | 0.397 | ~1e−05 |
| shuffled | 1.3810 | 0.276 | ~1e−07 |
| smooth | 0.5918 | 0.118 | ~1e−05 |

三条必须随结论声明的模型性质：

1. **过程不在 `w_ref` 附近运行。** 初值设计（`initial_wealth = mean_wealth = 5.0 = w_ref`）
   暗示意图是半饱和点，但平衡水平是 0.59–1.98，`w/w_ref = 0.12–0.40`。
   在此区间 `A = ε·w/(w+w_ref)` 近似线性于 `w`，能力异质性转化为交换优势的效率低于半饱和点。
   因此 §5.2 的 `w_ref` 不是可忽略的数值常数，而是决定**确认性实验处在哪个机制区域**的
   模型参数。
2. **下边界被强烈占据。** `min wealth` 达 1e−05…1e−13，`share` 的 `[0,1]` 夹紧在实际运行中活跃。
   所以 `w = 0` 不是稀有事件，S02 的边界政策在确认性尺度上确实起作用，
   `zero_wealth_fraction` 是必要的边界诊断而不是形式指标。
3. **衰减与源共同决定水平，源的强度依赖位置。** `ω* = Σprod/(N·d)`，而 `Σprod` 依赖
   粒子是否停在资源阱内。因此力的开与关使平衡水平相差约 3.4 倍（力开 1.98 → 力关 0.59）。
   凡是**财富类**结局，"运动通道"都与"平衡财富尺度改变"混杂。

### 5.9 位置对财富类因子是外生的（实证恒等）

由 §6.2 的因果图可推出一个强预测：位置 `(x, p)` 的轨迹只由 `(seed, 动力学参数)` 决定，
**与任何只写 `w` 的因子无关**。该预测已在 Cycle 3 E2 的归档数据上逐位确认：

- `occupancy_entropy(density)` 与 `morans_i(density)` 只依赖位置
  （`landscape_study.py:442/459`），而 `resource_density_spearman_rho` 依赖资源场；
- 在 E2 的全部 40 个 `(seed, force)` 组合上，切换 source+sink 开关后
  `occupancy_entropy`、`density_morans_i`、`resource_density_spearman_rho` **字符串完全相等**；
- 更强的是：在 `force` 关的单元上，entropy 与 Moran 在 `prod` 关/开之间**逐位相同**，
  即财富类因子连轨迹都未改变。

这条恒等有两个用途：它是 S01 在实验数据上的直接体现；它也是 E2-C4 识别策略的基础
（[e2-cycle4-channel-design.md](e2-cycle4-channel-design.md) §3 约束 3）——
在关闭地形力时，位置成为外生变量并可在全部单元间逐位共享，于是空间指标从"结局"变成
"恒等护栏"，财富类效应的位置混杂被彻底消除。

## 6. 因果图（WP0 §3.2 交付物）

### 6.1 实际实现的结构

```
                 ┌──────────────┐
   terrain V(x) ─┤  F_terrain   ├──▶ (x, p) ──┬──▶ 邻接图 (r < cutoff)
                 └──────────────┘   运动       │
                                               │
   ε (固定初值) ────────────────────────────────┼──▶ 交换  ──┐
                                               │            ├──▶  w
                 ┌───────────────┐             │            │
   terrain V(x) ─┤  生产衰减组合  ├──▶ 源项 ────┴──▶ w  ─────┘
                 └───────────────┘   sink
                                               │
   w ──────────────────────────────────────▶ 衰减 (∝ w)
```

文字化：

1. `terrain → F_terrain → (x, p)`：景观经由外场力改变运动；
2. `(x, p) → 邻接图`：位置决定谁与谁在 cutoff 内相邻；
3. `邻接图 + ε → 交换 → w`：交易重分配财富；
4. `terrain + ε → 生产−衰减 → w`：局地资源按能力放大产出，衰减与 w 成正比；
5. `ε → 交换` 与 `ε → 生产`：能力同时进入两条财富通道。

### 6.2 缺失的边（S01）

**不存在 `w → (x, p)` 的边。** 核实方式：`grep` 确认力的计算与积分器右端不读取 `wealth`/`w_data`；
主循环中没有任何按财富加权的速度、迁移或邻域选择。因此：

- 出生、死亡、承载力关闭时，**空间过程与财富过程是单向耦合**：
  景观与位置影响财富，财富不影响位置；
- 因此"景观改变空间组织 → 空间组织改变财富结构"这一中介链条在当前模型里**不成立**；
  景观对财富的影响只能走直接通道（§6.1 第 4 条）与邻接图通道（第 2、3 条）；
- **E2 的空间部分应重新表述为"结构隔离检查"**：当社会作用强度为 0 且运动方程不读财富时，
  切换生产—衰减开关**不应**改变位置过程。这是对模型结构的验证，不是"发现零效应"。
  旧记录中把该零效应当作"通道不存在"的证据是误读。

该推理在数据上已被逐位确认，见 §5.9：位置对任何只写 `w` 的因子完全不变。

### 6.3 一个不能声称的独立性

即使 `social_strength = 0`，粒子间仍通过**交换**耦合财富，再通过温控（§4.4）与
共同的随机抽样共享干预。因此本模型**不是独立粒子集合**，不能把粒子当独立样本使用；
统计单位是"seed 级运行"，这也是 E1-C4 把 seed 尾窗均值作为重复单位的原因。

### 6.4 通道不是正交的（v2 新增）

`§6.1` 的分支看起来像两条独立通道，但有两条不可忽略的连接：

1. **力 → 平衡财富尺度。** 力把粒子送进资源阱后 `Σprod` 上升，`ω* = Σprod/(N·d)` 随之上升。
   实测：力开使 `clustered` 的平衡水平比力关高约 3.4 倍（1.98 对 0.59，§5.8）。
   由于 §5.2 的能力函数含 `w_ref`，财富尺度的改变会改变交换核的工作点，
   所以**"运动通道"对任何财富类结局都不是纯净的**；
2. **生产—衰减组合因子同时改变水平与机制。** 见 §5.6：单开关同时改变 `Σprod` 与 `d`，
   使单元从"零和守恒、`w = w_ref`"变到"源汇平衡、`w ≪ w_ref`"。

结论：涉及**财富类**结局时，"景观效应"必须写明它同时包含空间组织与平衡财富尺度的贡献；
只有**位置类**指标（`occupancy_entropy`、`density_morans_i`）才是与财富尺度无关的干净结局。
E2-C4 的识别策略与 E1-C4 的次要家族限定都建立在这一条上。

## 7. 可观测诊断与它们的边界（WP0/WP5 对齐）

| 诊断 | 含义 | 不能推出 |
|---|---|---|
| `zero_wealth_fraction`、`min_wealth_observed` | 边界驻留质量（S02） | 不能推出"必然回流"或"必然吸收" |
| `clamp_events` | share 撞边界次数 | 不能推出越界已消除 |
| `active_pairs` / `nonzero_transfer_pairs` | 进入更新的对数 / 真实转移对数 | 前者不能当活跃交易数 |
| `nonfinite_encounters`、`negative_wealth_encounters` | 非法输入定位 | 计数 > 0 即应触发失败链，不能仅计数 |
| `thermostat trigger_count`、`max_correction`、`ke_removed` | 速度缩放的介入强度 | 0 只说明当前参数与时长下未触发 |
| `stationarity_pass` / `precision_pass` | 尾窗无漂移 / 估计量精度足够 | 都不等价于"完整联合分布平稳" |

稳态结论必须在**被声称的那个观测量上**成立，并写成"在指定观测量与时间尺度上未检出漂移"。

## 8. 支持矩阵（本文件写作时的真实状态）

| 维度 | 受控参考 | 状态 |
|---|---|---|
| MPI rank 数 | `nprocs = 1` | 参考模式；`nprocs>1` 在 confirmative mode 被拒绝（halo 未接入，§4.5） |
| 线程数 | `OMP_NUM_THREADS = 1` | 参考；OpenMP OFF/ON 的 CTest 与构建 Gate 已通过，逐位一致未验证 |
| restart | 不支持 | `--restart` 在 confirmative mode 被拒绝；RNG 与已存配置不恢复 |
| 河流 / 气候 / 文化 / 技术 / 人口 / 忠诚 / 征服 | 关闭 | 未验证；其 bug 只单独登记，不扩大当前受控实验的验证声明 |
| 完整人口模型 | 关闭 | 死亡粒子、compact 后索引、继承、资源收支均未验证 |

## 9. 旧结论处置表（WP0 §3.3 交付物）

| 旧证据 | 模型版本 | 暂定用途 | 重新成为确认性证据的条件 |
|---|---|---|---|
| C1 数值校准（E0-NUMERICS-C3） | Cycle 3 核 | 旧核在平坦测试下的守恒/非负/等态吸收记录 | 需在非退化景观 + 修复后边界 + 三级步长上重做（Cycle 4 用 V1F 承接） |
| C2 景观差异（E1-MATCHED-LANDSCAPES） | Cycle 3 核 | 旧模型有限时间内的已观察效应 | 新核上以新 seeds 独立重跑，且全部稳态 Gate 通过；**禁止**与 Cycle 4 结果合并 |
| C3 通道归因（E2-CHANNEL-ABLATION） | Cycle 3 核 | 空间部分作为**结构隔离检查**；财富部分作为组合通道探索 | 明确 §6.2 的因果结构、把因子改称"生产—衰减组合通道"后重新设计 |
| C4 规模稳健性（E3-ROBUSTNESS-HOLDOUT） | Cycle 3 核 | 旧版本的规模/分辨率敏感性记录 | `incomplete`（62 completed / 9 timeout / 169 未尝试），不得 resume 或并入 Cycle 4 |
| 平坦景观校准 | Cycle 3 核 | 仅用于守恒、自由运动与隔离交换 | 平坦场的常数相关必须标 `undefined/degenerate`，**不得**作为景观效应的误差标尺 |

**结论性说明**：Cycle 3 的 `supported` 标签在 §6.2 的因果结构下必须重新解释，其中
C2/C3 的主效应解释受"生产—衰减组合"与"空间无反馈"两处影响最大。Cycle 4 使用全新
实验 ID、全新 non-degenerate 校准与全新参数锁，不继承旧 `supported` 标签。

## 10. 本文件关闭与未关闭的事项

**已写实（本文件交付）**：

- 单步更新流水线与顺序（§3）；
- 运动、边界、温控的实际过程与介入记录方式（§4）；
- 交换规则的公式、边界政策、随机来源、更新顺序（§5.1–5.5）；
- 生产—衰减组合因子的准确定义（§5.6，S09）；
- 因果图与缺失的 `w → (x, p)` 边（§6，S01）。

**仍未关闭（不得由本文件宣称解决）**：

1. S02 边界驻留的长期行为——需要 V1F/E1 的 `zero_wealth_fraction` 与边界驻留统计；
2. S05 温控在**完整模型**（社会力非零）下的介入强度与力截断自洽性；
3. S10 的 MPI halo 接入与 restart RNG 恢复（当前仅以拒绝模式规避）；
4. S11 高密度交换的计算成本（尚无实测性能报告）；
5. 完整人口模型的资源收支与不变量；
6. 混合梯度/非平凡稳态的存在性——这是 Cycle 4 当前仍未验证的**科学前提**，
   由 V1F 与 E1-C4 的稳态 Gate 判定。

第 6 条是当前唯一的科学阻塞项：`research/state.md` 的记录为
"the numerical error bounds are now empirically resolved, but the steady-state premise
remains unvalidated. No Cycle 4 confirmatory claim is currently supported."
