# 深度反思 v11：阶段总结 — 从 H=209 到 v17 长跑

> **日期**: 2026-05-19  
> **状态**: v14c ✅ | v17 运行中（step ~900） | 问题 19 待 v17 全量确认

---

## 一、本阶段完成了什么

### 1.1 科学问题链（已闭合 / 进行中）

| 阶段 | 问题 | 结果 |
|------|------|------|
| KE 发散 | 热力学不稳定 | ✅ v14c 全程稳定 |
| 人口「崩溃」 | 是否 bug | ✅ 涌现：超载→~60k 再平衡 |
| H=209 + 数万环 | 图论病态 | ✅ v16 快验 H=4、零环 |
| 双目标张力 | 修层级 vs 帝国 | ⏳ **v17 全量验证中** |

### 1.2 工程交付

**代码（v15→v16→v17）**
- `would_create_cycle()`、全路径深度检查、`repair_hierarchy_graph()`
- `max_hierarchy_depth`、`hierarchy_repair_interval`（v17b: 500）
- `polity::get_depth` 环安全；stamp 数组去 O(n²) 分配

**算例与管线**
- v14c 无约束基线 20k step 完成 → [[query-2026-05-19-v14c-final]]
- v16 快验（10k/3k）通过
- v17 全量已启动（单进程+OpenMP，~0.3 step/s）

**运维脚本（本轮新增/加固）**
- `v14c_is_done.sh` / `cleanup_stale_v14c.sh` — 解决 MPI 僵死阻塞
- `wait_and_run_v17.sh` + flock — 防重复启动
- `ensure_v17_pipeline.sh` — 管道兜底
- `on_v14c_complete.sh` — 终局报告自动生成
- `post_v17_hierarchy_check.sh` + `watch_v17_milestones.sh`
- `summarize_run_progress.sh`

---

## 二、v14c 终局：对照实验的价值

| 指标 | v14c @20k | 说明 |
|------|-----------|------|
| N | 59,671 | 人口再平衡完成 |
| H | **53** | 仍严重超物理上限 |
| 环上粒子 @20k | **20,996** | ~35% 在环上 |
| largest_polity | 3,386 | 帝国 0 |
| Q | 0.956 | 文化序参量高 |

**帝国时间序列（瞬态）**：3 → 1 → 0（@50/100/150/200 time）。  
→ v17 验收用 **largest_pop ≥ 1000 @10k**，而非「必须有 empire 标签」。

---

## 三、v17 当前态势（step ~1100）

| 项 | 值 |
|----|-----|
| N @1000 | **82,328**（与 v14c 同期 82,394 一致） |
| 速率 | 0.3 step/s，ETA ~17 h |
| 构建 | 单进程 + OpenMP（MPI=OFF） |

**step 1000 信号**：`repaired 73039 superior links` — 首次 repair 大 sweep（repair_interval=500）。需在 **@5k checkpoint** 判定：环=0、H≤10 是否成立，以及政体是否仍能凝聚。

**待验证（@5k/10k/20k）**：五维矩阵 — H≤10、环=0、depth 口径一致、largest≥1000、KE 稳定。

---

## 四、深刻反思

### 4.1 「完成」的定义必须是多信号

v14c 教训：`Simulation complete` 在 log 里，但 **MPI 进程不退出** → waiter 死等。  
→ **完成 = log 标记 +（可选）进程退出**；僵死用 `cleanup_stale_v14c.sh`。

### 4.2 验证经济学已落地

| 档位 | 用途 | 本阶段 |
|------|------|--------|
| 10k/3k 快验 | 证伪、性能 | v16 ✅ |
| 100k/20k 全量 | 仅对照实验 | v14c ✅ → v17 进行中 |
| 脚本自动化 | 可重复验收 | milestone watcher |

### 4.3 双目标仍是核心科学问题

v16 证明：**硬约束可行**。  
v14c 证明：**无约束时文明指标更丰富但图论病态**。  
v17 假说：**repair 降频** 可在 H≤10、零环下保留更大政体。

若 v17 @10k 通过层级但 largest<1000 → 下一旋钮是 repair 策略（断边 vs 整链变 root），不是放弃 max_depth。

### 4.4 运维债：MPI 构建与启动不一致

- v14c 运行时曾见 3 个 `politeia` 进程；当前 build **MPI=OFF**
- v17 单进程 ~0.3 step/s，20k step ≈ **17–24 h**
- **建议**（不中断当前 run 的前提下）：并行准备 `POLITEIA_USE_MPI=ON` 重建，供下一算例使用

### 4.5 知识库工作流有效

`wiki/query` + `reflection` + `troubleshooting` + `log.md` 形成闭环；  
本轮 v14c-final 自动生成验证了 **ingest/change/query** 流水线。

---

## 五、下一步（按优先级）

```
[✅] v14c 终局报告
[🔄] v17 跑至 20k（~17h）
[ ]  @5k  — post_v17_hierarchy_check.sh
[ ]  @10k — 五维验收 + wiki/query v17 vs v14c
[ ]  @20k — 问题 19 标为全量确认 / 或 ADR
[ ]  P3: culture_force 独立算例（监测 KE）
```

---

## 相关

- [[reflection-2026-05-19-v5]] — 五维验收矩阵  
- [[query-2026-05-19-v14c-final]]  
- [[query-2026-05-19-hierarchy-baseline]]  
- [[troubleshooting#问题-19]]
