# AutoResearcher 工作流

**项目参数**（改这里的数值即可控制迭代规模）：
- `max_cycles = 5` — PLAN→DECIDE 最多运行几轮
- **一次只探索一个研究方案** — 产物平铺在 `research/`，不并行多方向

**计算环境**：数值实验在 A100 服务器运行（`ssh umi-wanwb`），项目根目录
`/home/wanwb/ONE/ar-politeia`。详见 [AGENTS.md](AGENTS.md) 与
[rules/server-config.md](rules/server-config.md)。

AutoResearcher 按七个 Stage 组织研究工作：`PLAN → EXPERIMENT → ANALYZE → WRITE-COMPREHENSIVE → WRITE-JOURNAL → REVIEW → DECIDE`，
根据证据和审稿反馈在两个循环间跳转，不执行固定步骤序列。

写作采用**两阶段策略**：先写内容丰富的完整论文作为权威记录，再从中提炼适合 Nature、PRL
等顶刊的浓缩投稿版本。

## 执行模式

- **多 Agent 图模式（推荐）**：`autoresearcher.orchestration` 读取显式 DAG，自动并行启动
  独立 Agent、等待 barrier、执行 Gate、阻断失败下游、恢复中断运行，并强制
  `max_cycles`。单方案示例见 `orchestration/research-graph.example.json`
  （`plan_experiments` → 逐实验 preflight/worker fan-out → `analyze` →
  `evidence_gate`（逐周期证据存在性确定检查）→ `write_comprehensive` →
  双刊写作 → 六路审稿 → Strategy，`request_human` 会暂停在
  `AWAITING_HUMAN` 等待人工决策文件）。图级 `budget.max_agent_seconds_per_cycle`
  是每周期 agent 壁钟时间熔断；agent 节点重试时会把上次失败原因注入提示词。
- **手动兼容模式**：单个 Agent 按本文逐 Stage 执行，适合调试或很小的研究任务。

两种模式使用相同的文件产物和 Foundation Gate。图模式的唯一运行状态位于
`.autoresearcher/orchestrator/state.json`；`research/state.md` 是面向研究者的阶段摘要，
不得反向覆盖编排器状态。

**核心执行原则：每个 Stage 开干净 session。**

- `research/state.md` 由 Agent 负责读写：
  ```
  current_stage = PLAN
  cycle = 1
  replan_from =
  ```
  `replan_from` 只在回到 PLAN 时填写（`ANALYZE`/`REVIEW`/`PI`），首次启动留空。Agent 结束当前 Stage 时更新到下一个 Stage。
- 重规划时，旧 plan 先归档到 `research/versions/cycle-${old}/`，再生成新的 `plan.json`。
- 目的：Plan 的中间推理不污染 Experiment 的判断，实验细节不污染写作，上一轮审稿偏见不污染下一轮。

**强制纪律**（不可跳过，每一项检查不过就必须停下来修复）：
- **提交实验前** → 必须跑代码对齐审查 + `preflight`，有一项不通过、不提交。
- **实验完成后** → 必须跑 `jobctl reconcile` 确认产物完整，缺失/损坏就重跑。
- **声称可以投稿前** → 必须跑 `audit`，不通过、不进入人类决策。

> **Agent 做科学判断，Gate 做结构验证，人类只在边界介入。**
> 详细规则见 [自主性与项目配置](workflow/01-autonomy-and-projects.md)。

## 工作流文档导航

| 文档 | 内容 |
|------|------|
| [01-autonomy](workflow/01-autonomy-and-projects.md) | Agent 自主边界、人类决策点、项目配置 |
| [02-planning](workflow/02-planning-and-strategy.md) | PLAN 制定计划、ANALYZE 解释证据、STRATEGY 重规划 |
| [03-experiments](workflow/03-experiments-and-evidence.md) | 实验声明、代码对齐审查、Preflight、隔离执行、证据导入 |
| [04-writing](workflow/04-writing-review-and-decision.md) | WRITE-COMPREHENSIVE 完整论文、WRITE-JOURNAL 期刊适配、REVIEW 模拟审稿、DECIDE 审计决策 |
| [journal-formats](rules/journal-formats.md) | Nature/PRL 等顶刊的格式、篇幅和叙事要求 |
| [05-operations](workflow/05-operations-budget-and-provider.md) | 预算、运行记录、LLM Provider 接入 |
| [07-orchestration](workflow/07-multi-agent-orchestration.md) | 多 Agent DAG、适配器、并行、汇合、恢复和 cycle 控制 |

---

## 循环 A：证据驱动

```
PLAN → EXPERIMENT（设计 → 代码审查 → Preflight → 执行）→ ANALYZE
  ↑                                                                   │
  │                             ←── replan ←──                        │ contradicted/inconclusive
  │                                                                   │
  └────────────────────────────────────────────────────── WRITE-COMPREHENSIVE（全部 supported）
```

- **PLAN**（读 `question.md` + 研究文档 → 出 `plan.json`）：生成 claims[] + experiments[]，Gate 验证结构。
  详见 [02-planning](workflow/02-planning-and-strategy.md)。
- **EXPERIMENT 设计**（读 `plan.json` → 更新 `plan.json`）：补充 baseline/ablation/指标/命令/资源。
- **计算策略选择**：Agent 可自主选择原方法、C++/MPI/GPU、替代算法或快速筛选。
  只需诚实声明证据角色与边界；筛选/近似结果直接支撑核心 claim 时必须验证。
  规则见 [计算策略](rules/computational-strategy.md)。
- **代码审查**（读 `plan.json` + 代码目录 → 出 `review_log.json`）：核对代码是否实现计划。
  详见 [03-experiments](workflow/03-experiments-and-evidence.md)。
- **Preflight + 执行**：`preflight` 检查复现性和必要的证据边界；`jobctl` 提交/轮询
  → 出 `jobs/` manifests。
- **ANALYZE**（读 `plan.json` + `jobs/` manifests → 出 `findings.json`）：解释 evidence，判定 supported/contradicted/inconclusive。
  详见 [02-planning](workflow/02-planning-and-strategy.md)。
- **跳转**：全部 supported → WRITE-COMPREHENSIVE。有 unresolved → STRATEGY Agent 自主选择 `replan`（回 PLAN，新 cycle）、`revise`（进 WRITE 改写叙事）、或 `request_human`。

---

## 循环 B：论文与审稿（长文 → 凝练 → 审稿 → 迭代）

论文阶段采用**先写长文、再凝练、对凝练版审稿**的策略：完整长文是权威记录，
Nature/PRL 等期刊版本从中提炼。审稿只针对凝练后的期刊版本，发现科学问题时回溯到
循环 A 补实验，再依次重写长文和期刊版本。

```
WRITE-COMPREHENSIVE  →  WRITE-JOURNAL  →  REVIEW  →  STRATEGY
      ↑                      ↑               │            │
      │                      │    ┌──────────┘            │
      │                      │    │ revise（叙事/格式）    │
      │  ┌───────────────────┘    │                       │
      │  │ replan 回到循环 A      │                       │
      │  │ （补实验）              │                       │
      │  │                        │                       │
      └──┴────────────────────────┘                       │
                                                          │
                                          continue ──→ DECIDE
```

- **WRITE-COMPREHENSIVE**（读 `findings.json` → 出 `paper/comprehensive/`）：生成内容丰富的完整长文，包含全部方法、实验、结果、
  讨论、局限性和补充材料。无篇幅限制，作为研究的**权威记录**和后续凝练的源头。此阶段不做审稿。
- **WRITE-JOURNAL**（读 `paper/comprehensive/` → 出 `paper/nature/`、`paper/prl/`）：从完整长文中按各自期刊要求凝练投稿版本。
  每种期刊版本独立产出 `main.tex`、`main.pdf`、`claims.json`。格式要求见 [期刊格式规则](rules/journal-formats.md)。
- **REVIEW**（读各期刊版本 + `findings.json` → 出各期刊独立的 `reviews.json` + `improvement_plan.json` + `iteration_summary.json`）：
  三个隔离 Agent 从 PRL/专业期刊视角、Broad-impact 视角、Technical 视角审稿，
  同时关注科学正确性和期刊格式/叙事。科学正确性层面直接与 `findings.json` 对照验证。
- **STRATEGY 跳转**：
  - `revise`：仅叙事/格式问题 → 回 WRITE-JOURNAL 修改对应期刊版本。
  - `replan`：证据不足、缺实验、方法缺陷等科学问题 → 回到循环 A 补实验，
    完成后依次重写 WRITE-COMPREHENSIVE 和 WRITE-JOURNAL。
  - `continue`：所有期刊版本均通过审稿 → 进入 DECIDE。
  - `request_human`：需要人工判断。

完整规则详见 [04-writing → 论文审稿迭代 Loop](workflow/04-writing-review-and-decision.md)。

---

## 收尾

- **DECIDE**（读全部产物 → 出 `decision_packet.json` + `reproducibility-bundle.json`）：Agent 生成建议，`audit` 验证证据链。
  详见 [04-writing → DECIDE 与最终审计](workflow/04-writing-review-and-decision.md)。
- **人类决策**：审阅决策包和审计报告后，选择 `submit`、`revise`、`replan` 或 `terminate`。
  详见 [01-autonomy](workflow/01-autonomy-and-projects.md)。

## 产物链

全部落在扁平 `research/`：

```
research/question.md → plan.json → jobs/ → findings.json
    → paper/comprehensive/（完整论文，权威记录）
        → paper/<journal>/（期刊适配版本）
            → orchestration/reviews/ → strategy.json
                → decision_packet.json → reproducibility-bundle.json
```

同步保存 `research/state.md`（当前进度）、`research/versions/cycle-<n>/`（历史归档），确保流程可恢复。

> `.tex` 源文件由 Git 追踪；`.pdf` 文件由 `.gitignore` 排除，通过 `make` 按需编译。
> 详见 [写作/审稿/决策 → PDF 编译](workflow/04-writing-review-and-decision.md#pdf-编译-build)。
