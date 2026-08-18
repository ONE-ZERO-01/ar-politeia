# 多 Agent DAG 编排

## 目标与边界

编排器把 AutoResearcher 从“一个 Agent 按文档切换角色”升级为可执行的多 Agent 图。
每次只探索一个研究方案，产物位于扁平的 `research/`：

```text
plan_experiments（PLAN + 实验设计 → 任务清单）
  → preflight_experiments（foreach：逐实验确定性 Gate）
  → run_experiments（foreach：逐实验隔离 worker，动态并行）
  → analyze（reconcile + 证据判定）
  → write_comprehensive
  → Nature ─┬─ 3 reviewers ─┐
  → PRL ────┴─ 3 reviewers ─┤
                            ↓
                       Strategy
            replan/revise ↺  │
            continue → Audit │
            request_human → AWAITING_HUMAN（写 human-decision.json 恢复）
```

编排器只控制依赖、并发、文件契约、失败、恢复和 cycle，不做科学判断。Agent 之间不传递
对话历史，只通过声明的文件输入输出通信。`preflight`、`jobctl` 和 `audit` 继续作为
确定性 Gate。

## 图契约

图是 `schema_version=1` 的 JSON。示例位于
`orchestration/research-graph.example.json`。

顶层关键字段：

| 字段 | 含义 |
|------|------|
| `workspace` | 所有 workdir、输入、输出、状态和日志的根目录 |
| `max_parallel` | 同时运行的最大节点数 |
| `max_cycles` | STRATEGY 可触发的最大研究轮数；达到上限硬阻断 |
| `adapters` | Agent CLI 命令模板与 prompt 传递方式 |
| `cycle_control` | 决策文件、字段、重复动作和终止动作 |
| `nodes[]` | 节点、边、文件契约、资源、超时和重试 |

节点关键字段：

| 字段 | 含义 |
|------|------|
| `id` | 全图唯一节点 ID |
| `kind` | `agent`、`command`、`gate`、`barrier` 或 `foreach` |
| `depends_on` | 上游节点 ID；所有上游成功或跳过后才 ready |
| `inputs` / `outputs` | 相对 workspace 的非空文件或目录契约 |
| `optional_inputs` | 存在则读、缺失不阻塞的输入（如上一轮 `strategy.json`、`reviews/`） |
| `output_schemas` | output 路径 → JSON schema 文件；节点成功前校验产物结构，防空壳文件 |
| `prompt_file` | Agent 的角色指令；运行时自动添加节点信封 |
| `timeout_seconds` / `retries` | 节点超时和有限重试 |
| `exclusive_resources` | 互斥资源名，例如 `gpu:0` 或 `research:main` |
| `when` | 基于 JSON 文件字段选择条件分支 |
| `tasks_file` / `task_template` / `task_parallel` | 仅 `foreach`：任务清单文件、任务执行模板、节点内并发数 |

所有命令必须是字符串数组，编排器不通过 shell 执行。所有运行路径必须保持在 workspace
内，防止节点契约意外写到研究目录之外。

## foreach：任务级动态 fan-out

`foreach` 节点在运行时读取上游产出的任务清单 JSON（根数组或 `{"tasks": [...]}`），
按 `task_template` 为每个任务生成一次隔离执行，`task_parallel` 控制节点内并发。
模板中的字符串字段支持 `{task.<key>}` / `{task_id}` 占位符，替换值来自任务对象：

```json
{
  "id": "run_experiments",
  "kind": "foreach",
  "tasks_file": "research/orchestration/experiment-tasks.json",
  "task_parallel": 2,
  "task_template": {
    "kind": "agent",
    "prompt_file": "orchestration/prompts/experiment-worker-agent.md",
    "outputs": ["{task.exp_dir}/result.json"],
    "timeout_seconds": 7200,
    "retries": 1
  }
}
```

规则：

- 任务 `id` 必须唯一且文件系统安全；替换后的 output 路径必须留在 workspace 内。
- 每个任务独立重试、独立日志（`cycle-<n>/<node>--<task_id>/`）、独立
  `AUTORESEARCHER_TASK_JSON` 环境变量；agent 模板的信封中附带任务 JSON。
- 任一任务失败 → 节点 FAILED，仅阻断下游。
- 恢复运行时只重跑产物缺失的任务，已完成任务直接跳过。
- 这使 PLAN Agent 可以**动态决定实验数量**，编排器负责并行与恢复；
  `preflight` 以 `gate` 模板逐实验强制执行，不再依赖大节点内部自觉。

## Agent 适配器

Codex 使用非交互 `exec`，prompt 从 stdin 输入：

```json
{
  "command": [
    "codex", "exec",
    "--sandbox", "workspace-write",
    "--ephemeral",
    "-C", "{workspace}",
    "-"
  ],
  "prompt_mode": "stdin"
}
```

这里刻意不使用绕过 sandbox/approval 的危险参数。Codex 的 `exec`、stdin `-`、
`--sandbox` 和 `--output-last-message` 行为见
[Codex developer commands](https://learn.chatgpt.com/docs/developer-commands#codex-exec)。

Cursor 示例使用 argument prompt：

```json
{
  "command": [
    "cursor-agent", "--print",
    "--output-format", "text",
    "--trust",
    "--sandbox", "enabled",
    "--workspace", "{workspace}",
    "{prompt}"
  ],
  "prompt_mode": "argument"
}
```

可用占位符：

- `{workspace}`、`{workdir}`、`{node_id}`
- `{prompt}`（argument 模式）
- `{state_file}`、`{output_last_message}`

运行时还会注入 `AUTORESEARCHER_NODE_ID`、`AUTORESEARCHER_PROJECT_ID`、
`AUTORESEARCHER_INPUTS_JSON` 和 `AUTORESEARCHER_OUTPUTS_JSON` 环境变量。

## 调度、汇合与失败

节点状态为：

```text
PENDING → RUNNING → SUCCEEDED
                  ↘ FAILED → 下游 BLOCKED
PENDING → SKIPPED（when=false，视为已满足的条件分支）
```

- 没有未完成依赖的节点进入 ready 队列。
- ready 节点在 `max_parallel` 和互斥资源允许时并行启动。
- barrier 不启动进程，只验证所有上游和声明输入已经完成。
- 节点退出码为 0 后仍必须产生全部非空 output，否则视为失败。
- 一个分支失败只阻断它的后代；无依赖的其他分支继续完成。
- 每个 output 必须只有一个生产节点；图校验会拒绝并行 Agent 共写同一产物。
  Write-Comprehensive / Strategy 是唯一汇总写入者。

## Cycle 收敛

STRATEGY 节点是 cycle 的单一决策者，并生成例如：

```json
{
  "action": "replan",
  "rationale": "关键 baseline 缺失",
  "unresolved_items": ["R-P0-3"],
  "next_cycle_scope": ["补 baseline，不重跑已通过实验"]
}
```

`replan` 和 `revise` 触发下一 cycle；上一轮状态原子归档到
`.autoresearcher/orchestrator/cycles/cycle-<n>.state.json`。`continue`、
`request_human` 和 `stop_request` 终止自动循环。若重复动作达到 `max_cycles`，
图状态变成 `BLOCKED`，不能继续烧 token/GPU。

`cycle_control.repeat_reset` 控制下一 cycle 重置哪些节点（含全部下游）：

```json
"repeat_reset": {
  "replan": ["research"],
  "revise": ["journal_nature", "journal_prl"]
}
```

`revise` 只重跑期刊写作与审稿分支，已通过的实验与长文节点保持 SUCCEEDED，
不再为改叙事重烧实验预算。未配置的决策值回退为整图重置。

## 人工决策：暂停与恢复

`cycle_control.human_values`（须为 terminal_values 子集）把对应决策变成可恢复的
暂停点而不是终态：

```json
"human_values": ["request_human"],
"human_decision_path": "research/orchestration/human-decision.json"
```

- 决策命中 `human_values` → 图状态变为 `AWAITING_HUMAN`，运行结束。
- 人类在 `human_decision_path` 写入 `{"action": "replan" | "revise" | "continue"
  | "stop_request", ...}` 后重新执行同一 `run` 命令：
  - `replan` / `revise` → 按 `repeat_reset` 开启下一 cycle 并继续自动运行；
  - 其他 terminal 值 → 图正常收尾（SUCCEEDED）；
  - 文件缺失或 action 仍是 `request_human` → 继续等待。
- 已消费的决策文件自动归档到
  `.autoresearcher/orchestrator/cycles/cycle-<n>.human-decision.json`。

## 状态、日志与恢复

`.autoresearcher/orchestrator/state.json` 是调度状态的唯一事实源。每次状态转换都用临时
文件加原子 rename 落盘。运行时对 `state.json.lock` 持有排它锁，第二个 `run` 进程会被
直接拒绝，防止并发写坏状态。Agent 日志按 cycle/node/attempt 分开保存。

重启同一 `run` 命令时：

- 中断时仍为 `RUNNING` 的节点回到 `PENDING`；
- 已成功节点若 output 仍有效则不重跑；
- 已成功节点的 output 消失时，该节点及全部下游自动失效并重跑；
- 图文件 hash 改变时拒绝复用旧 state，防止新旧拓扑混跑。

## CLI

```bash
# 安装命令入口
python3 -m pip install -e .

# 静态验证和可视化
autoresearcher-graph validate orchestration/research-graph.example.json
autoresearcher-graph render orchestration/research-graph.example.json

# 运行/恢复、查看状态
autoresearcher-graph run orchestration/research-graph.json
autoresearcher-graph status orchestration/research-graph.json
autoresearcher-graph status orchestration/research-graph.json --full

# 修复原因后，重置节点及其全部下游
autoresearcher-graph reset orchestration/research-graph.json --node research

# 生成研究历程 HTML（只读聚合研究产物，不依赖编排器状态）
autoresearcher-graph timeline
autoresearcher-graph timeline --research-dir research --output research/timeline.html
```

也可始终使用 `python3 -m autoresearcher.orchestration ...`，不要求安装 console script。

## 研究历程可视化

`timeline` 子命令把研究产物聚合成**研究叙事**——每一轮做了哪些尝试、验证了哪些主张、
哪些方向失败了、为什么失败、之后如何转向——并渲染为自包含的单文件 HTML（无外部依赖，
可直接双击打开，默认输出 `research/timeline.html`）。设计上保持松耦合：

- **只读聚合研究产物**：数据来源是研究协议本身的落盘文件——各轮 `plan.json`
  （claims、实验设计、`revision` 转向记录）、`findings.json`（supported /
  contradicted / inconclusive 判定与反证故事）、`orchestration/strategy.json`
  （决策与理由）、`iteration_summary.json`（放弃的方向、经验教训）、
  `jobs/<exp>/result.json`（实验通过/失败与关键指标）、`reviews/*.json`（审稿结论）。
  不读编排器 state、不需要 research-graph.json、不改写任何文件。
- **按轮成章**：`versions/cycle-N/` 归档轮 + 当前轮各为一章；刚开题（`status=planned`）
  的当前轮会自动屏蔽上一轮遗留的 findings / strategy / 审稿，避免张冠李戴。
- **失败叙事优先**：`revision.reason` 与退役主张渲染为「方向调整」块，
  `abandoned_directions` 渲染为「放弃的方向 · 失败原因」块，被反驳的 claim 用红色
  verdict 标注并展示反证 note，实验失败显示 `error` 与失败预案。
- **研究故事线**：页面顶部另有一条中轴交错时间线，每个节点是一次尝试，卡片按
  「假设 → 验证 → 结果 → 转折」四段展示；开题、方向调整、放弃方向、本轮决策
  以不同颜色/形状的节点串在轴上。carried-forward 且判定未变的 claim 自动去重，
  故事线只讲新发生的事；完整记录在下方「分轮详细档案」。
- **数据与渲染分离**：`build_research_timeline()` 产出纯 `dict` 数据模型，
  `render_html()` 只做渲染，未来可替换渲染层而不动数据路径。

## 接入单研究方案

1. 复制示例图，不直接运行。
2. 在扁平 `research/` 放入 `question.md`、假说源和初始 `plan.json`。
3. 接 `research` → `write_comprehensive` → Nature/PRL 写作与六个独立 reviewer。
4. 最后接 STRATEGY、条件 Audit 和 `cycle_control`。
5. 用小型假任务验证图，再允许真实 Agent 消耗 token/GPU。

旧 `research/state.md` 保留为研究摘要；编排器 state 才是“哪个节点可以运行”的权威来源。
