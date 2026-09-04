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
(E0-NUMERICS-C3 + B0-DYNAMICS-PILOT-C3); D3 in progress (parameter lock v2
final, E1-MATCHED-LANDSCAPES executing on umi).

## E1 完成后（D3→D4 转换）待办清单

E1 通过 nohup 手动启动（`run_landscape_study.py` 直接运行，非 jobctl submit），
因此完成后的三个 Gate 需手动对齐：

1. **jobctl reconcile 陈旧**：`.autoresearcher/jobs/E1-MATCHED-LANDSCAPES/handle.json`
   指向已死 pid 3871200、config_sha256 是旧值 f87d3a4f（当前 config 为 ac38d263）、
   worker result.json 仍是 Aug 20 的 exit_code=1。E1 完成后需刷新 handle 或重新
   `jobctl submit`（会触发 config_changed，需先归档旧 job_dir），否则 reconcile 误报 failed。
2. **audit 缺 manifest.json**：`audit.py` 读 `research/jobs/*/manifest.json`
   （字段 exit_code/mode/artifacts[{path,sha256,size}]），当前无任何 manifest.json。
   投稿前（D4）需为每个 job 生成 manifest；注意 jobctl 写的是 result.json（artifacts
   用 {path,valid}），与 audit 期望的 manifest.json 结构不同，需一个转换/生成脚本。
3. **timeline 再生成**：findings.json 键名修复后已重新生成一次（C1-NUM supported），
   但 E1 完成后需再次生成以纳入 E1 的 completed 结果与 C2 判定。

这些是 E1 完成后的机械对齐工作，不阻塞当前 E1 运行。
