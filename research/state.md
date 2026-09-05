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

1. **jobctl reconcile 陈旧**：`.autoresearcher/jobs/E1-MATCHED-LANDSCAPES/handle.json`
   指向已死 pid、config_sha256 旧值、worker result.json 仍是 exit_code=1。
   E1 通过 nohup 手动运行（非 jobctl submit），reconcile 需刷新 handle 或归档重建。
2. **audit 缺 manifest.json**：`audit.py` 读 `research/jobs/*/manifest.json`
   （字段 exit_code/mode/artifacts[{path,sha256,size}]），当前无任何 manifest.json；
   jobctl 写的是 result.json（artifacts 用 {path,valid}），结构不同，投稿前需转换/生成脚本。
3. **timeline 再生成**：已纳入 C2 supported。
