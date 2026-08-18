# AutoResearcher

AutoResearcher 是一个可恢复的多 Agent 研究 DAG：每次只探索一个研究方案，产物平铺在
`research/`，并保留三个可独立调用的确定性 Gate：

| 工具 | 用途 | 调用方式 |
|------|------|---------|
| `autoresearcher-graph` | 多 Agent 图校验、并行执行、汇合、恢复和循环控制 | `python3 -m autoresearcher.orchestration` |
| `preflight` | 实验提交前检查（commit/env/seed/artifact/计算策略） | `python -m autoresearcher.foundation.preflight` |
| `jobctl` | 幂等任务提交、状态查询、崩溃恢复 | `python -m autoresearcher.foundation.jobctl` |
| `audit` | 投稿前证据链完整性审计 | `python -m autoresearcher.foundation.audit` |

Foundation Gate 不依赖编排器，仍可单独使用；DAG 编排器通过命令适配器启动相互隔离的
Codex、Cursor 或其他 Agent，并把 Gate 作为普通确定性节点接入同一张图。

完整工作流从 [autoresearcher.md](autoresearcher.md) 进入，分主题说明位于 `workflow/`。

## 快速开始

```bash
python3 -m pip install -e .
python -m pytest -q
python3 -m autoresearcher.orchestration validate orchestration/research-graph.example.json
python3 -m autoresearcher.orchestration render orchestration/research-graph.example.json
```

示例图会启动多个真实 Agent；运行前必须复制并审查 Agent 适配器、预算、工作目录和产物契约：

```bash
cp orchestration/research-graph.example.json orchestration/research-graph.json
python3 -m autoresearcher.orchestration run orchestration/research-graph.json
python3 -m autoresearcher.orchestration status orchestration/research-graph.json
python3 -m autoresearcher.orchestration timeline
```

`timeline` 只读聚合 `research/` 下的研究产物（各轮 plan / findings / strategy /
iteration_summary / jobs 结果），生成研究历程 HTML（默认 `research/timeline.html`）：
每轮的主张判定、实验结果、放弃的方向与失败原因、方向调整与决策理由。

完整字段和迁移说明见
[多 Agent 编排](workflow/07-multi-agent-orchestration.md)。

## 计算环境

数值实验在 A100 服务器上运行（`ssh umi-wanwb`，4 × NVIDIA A100-40GB），项目根目录为
`/home/wanwb/ONE/ar-politeia`。服务器、路径、Python 环境与输出纪律见
[AGENTS.md](AGENTS.md)、[rules/server-config.md](rules/server-config.md) 与
[rules/gpu-allocation.md](rules/gpu-allocation.md)。

## 设计边界

- 每次只探索一个研究方案；换题时替换扁平 `research/` 内容，不并行多方向。
- 编排器只决定何时运行、并行、等待、重试、阻断和恢复，不替 Agent 做科学判断。
- Agent 负责提出研究计划、设计实验、分析数据、写论文和策略决策。
- Gate 只做确定性验证（结构完整性、证据对应、复现性约束）。
- Agent 自主选择性能优化或替代方法；框架只要求诚实声明证据边界，并保护核心 claim 的验证标准。
- 人类在预算、权限、投稿等边界介入。

## 迭代指南

每一个 PLAN → DECIDE 为一个 cycle，历史归档到 `research/versions/cycle-<n>/`。在图模式下，
STRATEGY 的 `replan/revise` 会生成下一 cycle；达到 `max_cycles` 后编排器强制阻断。
手动兼容模式仍可按下表回到对应环节：

| 不满意什么 | 操作 |
|-----------|------|
| 论文表述、图表、结构、claim 强度 | 回 WRITE 改稿，跑 `audit` 和审稿 |
| 缺实验、缺 baseline/ablation、统计不足、反例 | 回 PLAN 重新设计实验，走完整流程 |
| 审计不通过（证据缺失/checksum 不对） | 补充缺失 evidence 后重跑 `audit` |
| 方案不成立，需要换问题 | 重写 `research/question.md`，或清空后开新方案 |

通用研究建议 5 轮。每轮过后问自己：补实验或改稿的收益是否还大于成本？
