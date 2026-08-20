# B0 预算批准请求（Cycle 1）

状态来源：`research/plan.json` → `budget.status = "awaiting_human_approval_for_B0_only"`。

## 为什么要批准 B0

确认性实验（E1-E3）被参数锁 `ar-politeia-cycle1-confirmatory-v1` 的 candidate 状态硬阻断。
解锁顺序是：**B0 非证据性动力学试点 → 定参（候选锁 finalize）→ E0 数值校准 → 冻结 SESOI 并
绑定校准 SHA → E1-E3 解锁**。B0 是这条链的第一环。

## B0 做什么 / 不做什么

- 做：3 个 run（seeds 7103 / 7207 / 7309），N=500、网格 64×64，仅 clustered-active 景观，
  测量运行成本与动力学健康（wall_clock、stationarity 诊断、minimum_wealth、particle_count、
  有限性审计）。
- 不做：不设 shuffled 对照、不估计景观效应、不做任何聚集-vs-打乱对比。

## 预算请求（上限）

- CPU：**12 CPU-hours**
- wall-clock：**2 小时**
- GPU：**0**
- 依据：3 个顺序 run × 每 run 1800s 超时 × 8 OpenMP 线程；job 级超时 7200s。

## 执行位置与纪律

- 只在 `umi` 上运行（数值实验铁律）。
- 完成后只用 runtime / stability / health 诊断 finalize 或 revise 参数锁；禁止因结果好坏延长运行。
- 不查看任何景观对比，防止结果泄漏污染定参。

## 批准后链条

B0 → 定参 → 单独批准 E0 预算 → E0 校准 → 冻结 SESOI + 绑定 SHA → E1-E3 解锁。

## 决策

- [ ] 批准 B0：12 CPU-hours / 2 wall-clock hours / 0 GPU，在 umi 上执行。
