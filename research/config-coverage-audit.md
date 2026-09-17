# 配置键覆盖审计（S19）

**目的**：把"未验证通道必须在入口被拒绝"从个案修补变成**机制**。S16/S17/S18 的共同
成因是同一件事——某个通道既没有被校验，也没有在入口被拒绝，于是它可以在没人注意时
是活跃的。本轮把同一把尺子量到最基础的一层：**模拟器的配置面**。

- 状态：审计完成（2026-09-17，静态；未执行模拟器、未构造数值证据、未改动 C++）
- 机制落地：`tests/test_config_coverage.py`（5 项测试，经变异检验确认会失败）
- 相关：S16 / S17 / S18（台账 §4.7）、R07（配置校验）、R08（原地交换的顺序依赖）

## 1. 问题的形状

| 量 | 值 |
|---|---|
| `config.cpp` 可解析的键 | **185** |
| 参考配置（E1-C4 实际生成的 `politeia.cfg`）显式声明的键 | **47** |
| 未声明、取值来自 `config.hpp` 类内初始化的键 | **138** |

`default_config()` 返回 `SimConfig{}`，即默认值全部来自类内初始化；`politeia.cfg`
没有写出的键**不是"没有生效"，而是取 C++ 默认值**。所以在这 138 个键里，每一个都
必须回答一个问题：**在参考配置下它是否可达、是否中性？**

在这之前，仓库里没有任何地方回答过这个问题——这正是 S16/S17/S18 的同一个结构缺口
在更基础一层的投影。

## 2. 分类结果（138 = 136 中性 + 2 缺口）

分类不靠印象，靠消费点：对每个未声明键定位 `cfg.<field>` 的全部使用处，再判断这些
使用处是否被参考配置钉为 `false` 的模块开关包住。

| 类别 | 数量 | 判定依据 |
|---|---|---|
| `gated:<switch>` | 136 | 全部消费点位于 `if (cfg.<switch>)` 之内，而参考 cfg 把该开关钉为 `false` |
| `ic-superseded` | 5 | IC 文件提供了对应列（`w`/`age`）或无 IC 文件的分支未走（`init_jitter_factor`、`age_pyramid`、`init_age_min/max`） |
| `branch-inert` | 4 | 二进制地形分支未走（`terrain_grid_rows/cols`）、`checkpoint_interval = 0`（`checkpoint_dir`、`restart_file`） |
| `sentinel` | 1 | `exchange_cutoff = -1` → 解析为已声明的 `interaction_range` |
| `legacy-alias` | 1 | `terrain_scale` 同时写入两个已声明的地形尺度 |
| `no-consumer` | 2 | `mpi_px`、`mpi_py` 在 `src/` 全仓无消费者 |
| **`effective-undeclared`** | **2** | **可达、非中性，且值不在参考配置里——见 §3** |

按开关细分的 gated 计数：reproduction 21、river 20、loyalty 16、climate 16、
mortality 14、conquest 12、plague 8、technology 8、culture 5、carrying capacity 2、
terrain barrier 1。

值得单独记下的一条**正面**结论：`culture_mate_threshold`、`interaction_range` 这类
"一个键喂多个参数结构体"的情况经逐一核对都成立——`interaction_range` 被力、交换、
繁殖、文化四路共用，因此它是**已声明**的；`culture_mate_threshold` 的两路消费者
（mating 与 culture）恰好都在参考配置里被关掉，因此归到开关下是成立的。

## 3. 两个缺口：effective-undeclared

这两个键在参考配置下**确实生效**，而它们的值只存在于 C++ 默认值里。这与 S09 里
`w_ref`（`ability_saturation_w`）当初的处理是**同一类问题**——那里的修复就是把它显式
写进每个 `politeia.cfg`。不是可复现性缺陷（参考 binary SHA 与生成的 cfg 都已冻结，
所以结果仍然完全确定），而是**声明完备性**缺陷：单看声明出来的配置，推不出这次运行
的初始条件与遍历顺序。

### 3.1 `density_radius`（默认 `5.0`）→ 决定 cell 几何

```startLine:246:endLine:253:research/src/experiments/politeia/src/main.cpp
    // Cell size must cover interaction range, density radius AND exchange
    // cutoff (S10.1): exchange uses its own cutoff, so a larger exchange_cutoff
    // would otherwise fall outside the fixed 3×3 search and miss neighbours.
    const politeia::Real exchange_cutoff_effective =
        (cfg.exchange_cutoff > 0) ? cfg.exchange_cutoff : cfg.interaction_range;
    const politeia::Real cell_cutoff = std::max(
        std::max(cfg.interaction_range, cfg.density_radius),
        exchange_cutoff_effective);
```

该式的**本意**是让 cell 覆盖 `density_radius`（密度只在 carrying capacity 开启时
计算）。但参考配置下 `carrying_capacity_enabled = false`，`density_radius` 本身没有
任何消费者，**却仍然通过这个 `std::max` 把 `cell_cutoff` 从 `2.5` 抬到 `5.0`**。
于是 cell 边长翻倍、cell 数量减为 1/4、候选对的分组方式改变——这决定了
`cells.for_each_pair` 的**枚举顺序**，而交换核是串行原地更新：

```startLine:118:endLine:124:research/src/experiments/politeia/src/interaction/resource_exchange.cpp
    // Candidate C (Cycle 3): multiplicative reallocation with serial in-place
    // updates. share ∈ [0,1] keeps both endpoints non-negative and each pair
    // exactly zero-sum, eliminating the accumulated-clamp negative-wealth bug
    // of the candidate-B OpenMP dw_buf path. The perturbation is proportional
    // to total wealth (w_i+w_j), so it stays effective even when the wealth
    // gap is large — this is what yields a non-trivial steady state.
    cells.for_each_pair(x, n, cutoff_sq,
        [&](Index i, Index j, Real dx, Real dy, Real r2) {
```

也就是说 `density_radius` 属于 **R08 / S18 的"遍历顺序"家族**：它不改动物理公式，
但改变原地更新的施加顺序。与 S18 的关系是互补的——S18 关心"行序"，这里关心"cell
几何"，两者都通过同一段 Kahan-敏感代码生效。

**影响评估**：不改变任何已冻结阈值（值确定、binary 冻结）；但"参考配置"这一表述
在字面上不完整，且 V1F 的存储顺序误差界是在 `density_radius = 5.0` 这一固定几何下
取的。

### 3.2 `culture_dim`（默认 `constants::DEFAULT_CULTURE_DIM = 2`）→ 消耗 IC 装载的 RNG

IC 文件表头是 `x,y,w,eps,age`——**没有 `c0`/`c1` 列**。装载器的 `culture` 回退分支
因此对每个粒子抽 `culture_dim` 个 N(0,1)：

```startLine:167:endLine:173:research/src/experiments/politeia/src/io/ic_loader.cpp
        for (int d = 0; d < cfg.culture_dim; ++d) {
            if (iculture[d] >= 0 && iculture[d] < static_cast<int>(fields.size())) {
                particles.culture(idx, d) = std::stod(fields[iculture[d]]);
            } else {
                particles.culture(idx, d) = dist_cv(rng);
            }
        }
```

关键在**同一个 `rng` 也供初始动量**，且动量在文化之前抽、按粒子交错：

```startLine:137:endLine:143:research/src/experiments/politeia/src/io/ic_loader.cpp
        Vec2 pos = {x, y};
        Vec2 mom = (ipx >= 0 && ipx < static_cast<int>(fields.size()) &&
                    ipy >= 0 && ipy < static_cast<int>(fields.size()))
                     ? Vec2{std::stod(fields[ipx]), std::stod(fields[ipy])}
                     : Vec2{dist_p(rng), dist_p(rng)};
```

因此 `culture_dim` 每变 1，每个粒子多消耗 1 个随机数，**此后所有粒子的初始动量都变了**
（每粒子抽序是 mom(2) → culture(D)）。而文化向量本身在参考配置下是惰性的
（`culture_enabled = false`；`culture(` 的读取只在文化动力学、繁殖、技术扩散、输出与
迁移缓冲里，前者三个都被开关关掉），所以这不是物理错误，而是：
**有效初始条件由未声明的维度决定**。

## 4. 机制：审计不能落后于代码

`tests/test_config_coverage.py` 的 5 项：

1. `test_every_parser_key_is_classified_exactly_once` —— 用正则从 `config.cpp` 取全部
   解析键、从驱动本身生成参考 cfg，要求每个键**恰好**落在"已声明"或某一审计类别里。
   **变异检验**：临时插入 `probe_new_knob` 后该项失败并指名该键，随后已还原。
2. `test_reference_cfg_pins_every_gating_switch_off` —— 11 个门控开关必须在参考 cfg
   里逐字为 `false`；否则 gated 分类失效，审计必须重做。
3. `test_no_gated_or_gap_key_is_emitted_by_the_driver` —— 被归为惰性/缺口的键若突然
   出现在生成的 cfg 里，说明分类或构建已不一致；
4. `test_effective_defaults_keep_their_anchors` —— 两个缺口的默认值（`5.0`、
   `DEFAULT_CULTURE_DIM = 2`）以及两处代码锚点（cell cutoff 的 `std::max`、文化回退
   抽取）必须保持不变，否则登记失效；
5. `test_shared_and_declared_keys_are_never_filed_as_gated` —— 多消费者键不得被误归。

## 5. 下一步（都排在 E1-C4 之后）

1. **补齐声明（不改 C++、不改 binary SHA）**：把 `density_radius` 与 `culture_dim`
   显式写进 `common_cpp_config`（与 `ability_saturation_w` 同样的做法）。这一步会改变
   生成的 `politeia.cfg`，因此对**已授权**的 E1-C4 不能追溯应用——按 S15 的教训，
   已授权实验的产物必须能由其冻结 `source_commit` 逐字节复现。故只能对新实验（E2-C4
   之后）生效，并需同步更新本审计的"已声明"集合。
2. **消除隐式耦合（改 C++，需重跑校准）**：`cell_cutoff` 只应按**活跃**的 kernel
   半径取最大（carrying capacity 关闭时不该被 `density_radius` 抬升）。
3. **S18 实测**：`T = 0.5` 下的 canonical vs permuted，判定热噪声↔行序耦合是否落在
   已冻结的数值上限内。
