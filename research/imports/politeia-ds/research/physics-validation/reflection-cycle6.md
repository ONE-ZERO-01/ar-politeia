# Cycle 6 收关反思：从问题到答案 — 五轮迭代的完整教训

> 日期：2026-06-15 | 从 Cycle 1 至今的总结
> 关联：[[reflection-cycle1]] · [[reflection-cycle2]] · [[reflection-cycle3]] · [[reflection-cycle4]] · [[reflection-cycle5]]

---

## 一、五轮迭代的时间线

```
06-11  Cycle 1: 物理验证 (BBK/LJ/terrain/exchange/FDT) → 发现 flat bug ✅
06-11  Cycle 2: hierarchy 消融 (M1.10) → loyalty 是必要条件 ✅
06-11  Cycle 3: conquest 调试 → cbp=0.02 太低, 人口爆炸 ✅
06-12  Cycle 4: fertility 约束 → f=1e-4 最优, max=983@10K ✅
06-12  Cycle 5: 再加 2500 步 → 🎉 6 STATES! + M2.1 地形对照 ✅
06-15  Cycle 6: Phase 2 三种地形 12500 步完整矩阵 → 🔄运行中
```

---

## 二、所有实验结果汇总

### 2.1 三种地形 × 12500 步对比（已知数据）

| 地形 | N_final | max_polity | states | HHI | 政权数 |
|------|:--:|:--:|:--:|:--:|:--:|
| **Continent** | **46475** | **1515** | **6** 🎉 | 0.012 | 215 |
| China (s42) | 24423 | 733 | 0 | 0.011 | 239 |
| China (s123/456) | 🔄 | 🔄 | 🔄 | - | - |
| Europe (×3) | 🔄 | 🔄 | 🔄 | - | - |

### 2.2 三种地形 × 10000 步对比（完整，6 seeds）

| 地形 | N | max | HHI | 合并速度 | 特征 |
|------|:--:|:--:|:--:|:--:|------|
| Continent | 31283 | 983 | 0.011 | ↓13% | 高承载+均匀 |
| Europe | 16045 | 707 | 0.014 | ↓43% | 低承载+集中 |
| China | 16154 | 485 | 0.011 | ↓34% | 低承载+均匀 |

### 2.3 核心参数配方

```
conquest_base_prob = 1.0          # 致命默认值 0.02！
conquest_power_ratio = 0.8
deterrence_enabled = true
succession_loyalty_factor = 0.95   # 关键！< 0.8 则碎片化
max_fertility = 1e-4               # 关键！> 5e-4 则人口爆炸
initial_particles = 10000           # 关键！> 20K 则白跑
total_steps ≥ 12500                 # 关键！结构需要时间
```

---

## 三、五个核心教训

### 3.1 "代码有 bug" → "参数是默认值"
**问题**：conquest 从不触发 → 怀疑代码有 bug → 花数小时读源码、加 debug 日志
**真相**：`conquest_base_prob = 0.02` 太低。改为 1.0 后立马万次征服。
**教训**：先用极端参数诊断，确认机制正常后再调优。

### 3.2 "更多粒子 → 更大政体" → "粒子越多越膨胀"
**问题**：20K 粒子 → population 爆炸到 75K → 每步 O(N²)→ 3h 跑不完一个 run
**真相**：10K 是最优起始规模。20K 粒子 = 2× N + 4× 计算开销。
**教训**：先小后大，线性扩展不是免费的。

### 3.3 "一起调参" → "调参是对抗的"
**问题**：调高 cbp（conquest）+ 调高 fertility → 两个参数互相抵消 → 什么都看不出来
**真相**：先切源头（fertility ↓），再看效果（conquest ↑）。一次只调一个参数。
**教训**：源头阻断法 — 先控制最基础的变量，再验证上层机制。

### 3.4 "高 NFS 和脚本健壮性" 
**问题**：脚本用 `set -e` → 任一 run 失败就全部中断。NFS 陈旧句柄导致 `rm -rf` 卡死。
**修复**：`set -u` 代替 `set -e`，用 `mv` 代替 `rm -rf`，run 失败不影响后续。
**教训**：shell 脚本的优雅退化和 NFS 的特殊处理。

### 3.5 "假说指导实验" → "实验推翻假说"
**原假说**："China 封闭地形 → 更大政体"
**实验事实**：Continent → 6 states (1515)，China → 0 states (733)
**修正**：政体规模 = 人口承载力 × 空间破碎度
**教训**：不要执着于假说。让实验告诉你什么是真的。

---

## 四、项目现状

### 4.1 已完成

| 阶段 | 实验数 | 核心结果 |
|------|--------|----------|
| P0 物理验证 (M1.1–M1.9) | 27 | BBK/LJ/terrain/exchange/FDT 全部通过 |
| 机制消融 (M1.10) | 8 | loyalty 是 state 涌现的必要条件 |
| 参数探索 (M1.11–M1.13) | 12 | 找到 STATE 配方 |
| STATE 涌现 (M1.16) | 1 | **6 states** 确认 |
| 地形对照 (M2.1 5K+10K) | 12 | 地形是决定性变量 |
| Phase 2 12500步 | 1/6 | china_s42 完成，5 个剩余 |

### 4.2 🔄 进行中

Phase 2: China + Europe × 12500 步 × 3 seeds（剩余 5 runs，~50 min）

### 4.3 待完成

```
Phase 2 完成   → 三地形矩阵完整对比
WRITE 阶段     → 论文草稿（按 AutoResearcher Stage 4）
  - 方法: Langevin-jump-diffusion 仿真框架
  - 核心发现: ① STATE 涌现的临界参数 ② 地形对政体形成的决定性影响
  - 对比: Turchin/Seshat 真实世界数据
M2 真实验证   → 真实世界参数校准
```

---

## 五、教训文档索引

| 文档 | 核心内容 |
|------|----------|
| [[reflection-cycle1]] | flat bug, BBK 正确性 |
| [[reflection-cycle2]] | hierarchy 消融, loyalty 必要性 |
| [[reflection-cycle3]] | conquest 调试, cbp 默认值陷阱 |
| [[reflection-cycle4]] | fertility 约束, 人口爆炸 |
| [[reflection-cycle5]] | STATE 涌现, 地形对照, 假说推翻 |
| 本文 | 五个核心教训, 项目现状, 下一步 |

---

> **最终洞察**：「五轮迭代，从'能量不守恒'到'6 个 state 涌现'。真正的科学方法不是一次跑对，而是一次次跑错后找到对的路径。参数、地形、步数——三者缺一不可。」
>
> **三条金律**：
> 1. 极端值诊断 → 源头阻断 → 单变量验证
> 2. 10K 粒子、1e-4 fertility、1.0 cbp、0.95 slf、12500 步
> 3. 实验推翻假说时，接受实验