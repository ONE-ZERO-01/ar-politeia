# 运行、预算与 Agent Session

## 预算

项目预算记录在 `research/project.json`，方向计划可在各自 `plan.json` 中声明本轮可用预算。
至少跟踪：

- `max_cycles`
- `gpu_hours_allocated` 与 `gpu_hours_consumed`
- `token_limit`

预计实验超过已授权预算时，Agent 必须请求人类调整预算，不得自行扩大资源。实验过慢但仍在
预算内时，先按 [计算策略 Gate](../rules/computational-strategy.md) 选择等价性能优化；
采用快速筛选不能降低核心结果的参考验证标准。

合理的停止依据包括：

- 核心 claim 已有充分且可复现的证据。
- 反证形成了更有价值的新结论。
- 关键不确定性需要当前权限或预算之外的资源。
- 继续实验的信息增益低于成本。
- 方向被可靠证据否定且没有值得检验的替代假设。

## 运行记录

每个研究方向至少保留：

- `question.md`、`state.md`、`plan.json`
- `jobs/`、`findings.json`
- `paper/`、`reviews.json`
- `improvement_plan.json`、`iteration_summary.json`
- `decision_packet.json`、`reproducibility-bundle.json`
- `versions/cycle-<n>/`

Stage 之间通过这些文件传递上下文。每个 Stage 使用干净 Agent session，不能依赖上一会话
未落盘的隐式记忆。

## Agent Session

框架内置 Provider 无关的 Python DAG 编排器。每个 Agent 节点由一个命令数组适配器启动，
以独立 prompt/session 读取声明的文件输入并生成声明的文件输出。内置示例提供 Codex 和
Cursor CLI 适配器；其他 Agent CLI 使用相同的 stdin 或 argument 契约即可接入。

编排器负责：

- 根据 `depends_on` 计算 ready 节点并并行运行；
- 在 barrier 等待所有上游；
- 使用 `exclusive_resources` 避免 GPU、方向目录等资源冲突；
- 记录原子状态、日志、超时、重试和失败传播；
- 根据 STRATEGY 输出推进 cycle，并强制 `max_cycles`。

Agent 在相应 Stage 中调用：

- `python3 -m autoresearcher.foundation.preflight`
- `python3 -m autoresearcher.foundation.jobctl`
- `python3 -m autoresearcher.foundation.audit`

科学判断仍由 Agent 完成；编排器和三个 Gate 只执行确定性控制。完整配置见
[多 Agent 编排](07-multi-agent-orchestration.md)。

## 验证

```bash
python3 -m pytest -q
python3 -m autoresearcher.orchestration validate orchestration/research-graph.example.json
```

正式研究还应验证一次完整链路：

`PLAN → EXPERIMENT → preflight → jobctl → ANALYZE → WRITE → REVIEW → audit → DECIDE`
