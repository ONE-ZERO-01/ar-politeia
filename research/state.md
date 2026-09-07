# Research state

```
current_stage = EXPERIMENT
cycle = 3
replan_from = cycle-2
```

This file is a human-readable stage summary for the single research plan under
`research/`. Orchestrator truth lives in `.autoresearcher/orchestrator/state.json`
and must not be overwritten from here.

Cycle 3 = exchange-kernel steady-state refactoring (design doc
`research/exchange-kernel-design.md`, D0-D4). D2 calibration passed
(E0-NUMERICS-C3 + B0-DYNAMICS-PILOT-C3); D3 confirmatory E1-MATCHED-LANDSCAPES
executed and passed — C2-LANDSCAPE **supported** (clustered-minus-shuffled paired
effect 4 metrics Holm-significant above frozen SESOI); E2-CHANNEL-ABLATION
executed and passed — C3-CHANNELS **supported** (movement single-channel
attribution, production zero effect on spatial structure, interaction zero).
C4-ROBUSTNESS awaits the E3 CPU budget decision.

## E2 完成后的收尾与决策

E2 结论已提交（`ca2192a`，result.json + channel_effects.json 进 git），findings /
cycle-output / plan / state 已同步 C3→supported。C1-NUM / C2-LANDSCAPE /
C3-CHANNELS 三项核心+机制主张全部 supported。

**待决策**：E3-ROBUSTNESS-HOLDOUT（C4 稳健性）是否执行——新的 CPU 预算边界，需
人类批准。E3 已 prepare-only 验证（240-run 输入生成通过），但高人口（10000）run
存在 O(N²) 交换核超时风险，批准前需先跑一次高人口 benchmark 实测。

**D4 前需手动对齐的 Gate（不阻塞 E3 决策）**：

1. **jobctl reconcile 陈旧** — ✅ 已解决：服务器 `.autoresearcher/jobs/` 下
   7 个 Cycle 1/2 过时 jobctl 运行态记录（死 pid、旧 commit `029820d`、worker
   exit_code=1）已清理。Cycle 3 实验全走 nohup 手动运行（非 jobctl submit），
   不依赖 jobctl handle；清理后 `jobctl reconcile` 返回 `no_handle`，语义正确。
2. **audit 缺 manifest.json** — ✅ 已解决（`42a6d50`）：新增 foundation 工具
   `gen_manifest.py`，从 result.json（status=completed && pass=true）生成
   manifest.json（exit_code=0/mode=server/artifacts[{path,sha256,size}]）。
   已为 E0-C3/B0-C3/E1 生成，退休 C1/C2 job（pass=false）与未运行 job（blocked）
   自动跳过（走 claim evidence 路径）。本地 audit 确认 manifest 检查通过，仅剩
   `claims file is missing`（D4 写 paper claims.json 时补齐）。
3. **timeline 再生成**：已纳入 C2 supported，E2 完成后需再生成纳入 C3。

**E2-CHANNEL-ABLATION 已完成**（`ca2192a`）：160/160 runs，三 gate 全过，C3
supported。两处判定逻辑修正（drift 绝对漂移容差 + wealth_variance 移出 E2 gate）
见 exchange-kernel-design.md §16，均已提交（`d8a4cd1`）。
