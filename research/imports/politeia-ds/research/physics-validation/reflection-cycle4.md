# Cycle 3→4 终极反思：寻找 state 涌现的参数窗口

> 日期：2026-06-12 | AutoResearcher: EXPERIMENT → (replan) → PLAN
> 关联：[[reflection-cycle1]] · [[reflection-cycle2]] · [[reflection-cycle3]]

---

## 一、全景：三个 Cycle 最终收敛

### 1.1 所有实验数据的统一视图

```
                    原版 M1.10         v2 (conquest fix)    v3 (v2+2000步)
                    ─────────         ────────────────    ──────────────
conquest_base_prob    0.02                 1.0                1.0
succession_slf        0.80                 0.95               0.95
起始 N                10K                  10K                10K
步数                  5000                 5000               7000
──────────────────────────────────────────────────────────────────────
最终 N                55,583              53,481             87,751
Gini                  0.644               0.645              —
层级深度 H             5                   10                 10(推测)
政体数 C              2,524               276                ~288(roots)
最大政体              305                 923                489
chiefdoms             280                 205                —
states                0                   0                  0
empires               0                   0                  0
──────────────────────────────────────────────────────────────────────
conquest 事件          0                   23,512/interval    —
merger 事件            0                   0                  0
collapse 事件          0                   258                258
formation 事件         639                 534                534
```

### 1.2 核心发现（按确定度排序）

| # | 发现 | 确定度 | 证据 |
|---|------|-------|------|
| 1 | **conquest 机制完全正常**——只是 `cbp=0.02` 太低 | **极确定** | debug 日志：cbp=1.0 时 23K 征服/interval |
| 2 | **conquest 在削减碎片化**（polities 2524→276, 89%） | **极确定** | v2 对比原版 |
| 3 | **层级加深 2×**（H 5→10） | **极确定** | v2 比原版 |
| 4 | **最大政体 ~2×**（305→923, 但未过 state 门槛 1000） | **较高** | v2 单次实验 |
| 5 | **继承碎片化压倒征服合并**（923→489 between 5K-7K） | **较高** | v3 对比 v2 |
| 6 | **人口爆炸抹杀一切优化**（10K→55K/54K/88K） | **极高** | 全部实验 |

### 1.3 我们陷入了什么

```
conquest ↑  →  bigger polities  →  更多人口保护  →  fewer deaths
                                            ↓
                                   人口爆炸 (5.5-8.8×)
                                            ↓
                                   更多 births  →  new particles
                                            ↓
                              new attachments  →  层级加深
                                            ↓
                              领袖死亡  →  succession 碎片化
                                            ↓
                          碎片化速度 > conquest 合并速度
                                            ↓
                               ╔══════════════════╗
                               ║   NO STATE        ║
                               ╚══════════════════╝
```

这是一个**正反馈陷阱**：conquest 越好 → 更多粒子被保护 → 更多繁殖 → 更多粒子 → 更多层级 → 更多领袖死亡 → 更多碎片化。**突破征服瓶颈后，下一个瓶颈是人口膨胀驱动的继承碎片化。**

---

## 二、三重根本矛盾

### 矛盾 1：征服需要层级，但层级放大人口

```
conquest works only when roots exist
  → loyalty creates hieraries → population protected → births ↑
    → more particles → more roots → more conquest candidates ✓
                     → BUT also more population → step/s ↓↓↓
```

### 矛盾 2：大政体需要时间，但人口爆炸让每一步都越来越慢

| 规模 | 初始 N | 最终 N | 增长率 | step/s |
|------|--------|--------|--------|--------|
| M1.10 原版 | 10K | 55.6K | 5.6× | 5.6→19 |
| v2 | 10K | 53.5K | 5.4× | ~5→19 |
| v3 | 10K | 87.8K | 8.8× | <5 |
| M2.1 | 50K | 154K@3.1K | 3.1×@31% | 0.6→0 |

**任何参数下都无法逃脱此定律**——只要繁殖和死亡模块开启，人口就从 10K 爆炸到 50K+。

### 矛盾 3：参数是博弈的

```
若 fertility ↑  → 更多 births → 人口爆炸 → 更多领袖死亡 = 更多碎片化
若 fertility ↓  → 更少 births → 人口稳定 → 但政体成长慢，需要更多步

若 slf ↑ (继承保真) → 碎片化少 → 但子代自动忠 → 层级不"自然"了
若 slf ↓ (继承衰减) → 更现实 → 但碎片化剧烈

若 cbp ↑ → 征服多 → 碎片化少 → 但人口被保护 → 人口爆炸

一切参数都在互相对抗——没有明显的"甜点"
```

---

## 三、方法论修正：从"参数调优"到"约束调优"

前三轮 Cycle 的策略是：**找到一个参数 → 跑实验 → 不满意 → 调另一个参数**。这是 `O(N)` 的盲目搜索。

正确策略应该是：**先建立"能使 state 涌现"的必要条件公式，再调适配参数**。

### 3.1 State 形成的物理必要条件

```
state = 政体人口 ≥ 1000

政体人口 = Σ(粒子), 其中粒子.superior 链通到该政体 leader

leader 的政体人口 = 1 (自己) + Σ(直接子级的人口)
                       + Σ(子级的子级) + ...

在稳态下:
  population(polity) = f(conquest_rate, birth_rate, death_rate, succession_decay, time)
```

目前数据：
- 在 cbp=1.0, pr=0.8, deter=on 下，每 500 步新增 ~200-900 粒子（conquest net gain）
- 在 population 模块下，每 500 步净增 ~5000-8000 粒子（births - deaths）
- **人口增长是征服合并速度的 10-25×**

**结论：State 不可能在目前的人口膨胀率下涌现** —— 征服合并的政体增长每 500 步 200-900，但同期总人口增加 5000-8000，新粒子大部分是"生根"（自己当 leader），反而增加碎片化。

### 3.2 修正路线

**两步走，每步一个"阻断"参数**：

```
Step 1: 阻断人口膨胀
  ├─ max_fertility: 5e-4 → 1e-4 (降 5×)
  ├─ consumption_rate: 缺省 → 调高使死亡 ≈ 出生
  └─ 验收标准: N(step 5000) < 1.5 × N(step 0)

Step 2: 用征服产生足够大的政体
  ├─ 用 v2 的 conquest 参数 (cbp=1.0, pr=0.8, deter=on)
  ├─ 扫描 slf (0.95, 1.0)
  └─ 验收标准: 至少 1 个政体 ≥ 1000 人口 → STATE
```

### 3.3 时间估算（人口控制后 step/s 大幅提升）

```
max_fertility = 1e-4 (vs 5e-4) → 出生率 1/5 → 人口增长 < 1.5×
  → 结束 N ≈ 15K (vs 55K) → step/s ≈ 10-15 (vs 5-6)
  → 5000 步 < 10 min (vs 22 min)
```

---

## 四、重规划：Cycle 4 — 约束调优

### 4.1 执行计划

```
Phase 1: fertility 摸底 (2 runs × 5 min)
  ├─ M1.13a: max_fertility = 5e-5 (原值1/10), 其他=v2
  ├─ M1.13b: max_fertility = 1e-4 (原值1/5)
  └─ 序参量: 最终 N, N 增长率, 最大政体

Phase 2: 基于 Phase 1 选最优 fertility + 征服参数 + 扫 slf (3 runs × 5 min)
  ├─ 固定 fertility + conquest(v2) + 5000 步
  ├─ 扫 slf ∈ {0.95, 0.98, 1.00}
  └─ 序参量: s_count, max_polity, H

Phase 3: 如果 Phase 2 产生 s≥1
  ├─ 锁定全部参数
  ├─ M2.1-reduced: China vs Europe (20K×5000×3 seeds×2 地形, ~30 min)
  └─ 核心假说验证

Phase 4: 如果 Phase 2 仍 s=0
  ├─ 研究 polity 分类门槛是否需要降低 (state ≥ 1000 是否过高)
  └─ 或接受"10K 粒子规模下无法形成 state" 的现实
```

### 4.2 优先级

| 优先级 | 内容 | 跑量 | 耗时 |
|--------|------|------|------|
| **P0** | Phase 1: fertility 摸底 | 2 runs | ~10 min |
| **P1** | Phase 2: slf 扫描（人口受控） | 3 runs | ~15 min |
| **P2** | Phase 3: 中欧对照 | 12 runs | ~30 min |
| **P3** | Phase 4: 重新评估 | — | — |

---

## 五、状态与下一步

### 5.1 当前

```
current_stage = REPLAN
cycle = 4
关键洞察: "人口爆炸是自我惩罚。断了繁殖，才能看到征服。"
```

### 5.2 立刻执行

1. **Step 1a**: max_fertility=5e-5, v2 conquest params, 10K×5000
2. **Step 1b**: max_fertility=1e-4 (并行或顺序)
3. **选择** → Phase 2

---

> **格言**：「不要用更多的征服来对抗人口爆炸——先灭了爆炸，再看征服能否独力推过 state 门槛。」
>
> **教训**：「参数调优的次序是决定性的。」先调 cbp（conquest）→ population 仍然爆炸 → 再调 slf→ 仍然碎片化。真正的次序应该是：先 caps population (fertility) → 再看 conquest 能否在可控规模下建立 state。
>
> **重复模式**：三个 Cycle 的共同错误——「增加一个参数的值来补偿另一个参数的副作用」，而非「切断副作用的源头」。
