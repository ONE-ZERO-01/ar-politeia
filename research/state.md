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
effect 4 metrics Holm-significant above frozen SESOI). C3-CHANNELS / C4-ROBUSTNESS
await the E2/E3 CPU budget decision.

## E1 完成后的收尾与决策

E1 结论已提交（`99a1f03`，result.json + paired_effects.json 进 git），findings /
cycle-output / plan / state 已同步 C2→supported。

**待决策**：E2-CHANNEL-ABLATION（C3 机制）与 E3-ROBUSTNESS-HOLDOUT（C4 稳健性）
是否执行——这是新的 CPU 预算边界，需人类批准。

**D4 前需手动对齐的 Gate（不阻塞 E2/E3 决策）**：

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
3. **timeline 再生成**：已纳入 C2 supported。

**E2-CHANNEL-ABLATION 运行中**（`1608ab9` 锁 v3 后启动）：160 runs，progress 见
`research/jobs/E2-CHANNEL-ABLATION/workspace/`（completion.json 计数），预计 ~27h。
完成后走 `channel_effects.json` 做 C3 通道机制判定（movement/production 主效应 +
interaction 的 Holm 校正）。
