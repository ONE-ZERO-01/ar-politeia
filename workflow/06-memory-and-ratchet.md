# 记忆与棘轮（Memory & Ratchet）

> 目的：让框架从每一次失败中沉淀可复用的经验，并在人类闸门下把稳定经验固化成硬约束，
> 使同类错误结构上不再重复（ratchet pattern，棘轮模式）。
>
> 一句话原则：**沉淀可以自动，改框架必须人批。**

---

## 1. 为什么需要

现有框架的 Gate（`preflight` / `jobctl` / `audit`）能拦住结构性错误，但拦下来之后
**信息就丢了**：同一类错误（空壳 config、路径逃逸、证据缺失、被审稿反复挑同一问题）
会在下一个 cycle、下一个方向里重新发生。

记忆与棘轮机制把这些失败变成显式、可检查、可淘汰的经验，让 harness 随使用而增强，
而不是每轮从零开始。

设计上刻意避免两个常见死法：

- **不压缩对话历史。** 对话 90% 是过程噪音，提炼出的“注意 X”既不可执行也无法验证。
  经验只从**结构化失败事件**产生。
- **不让经验只增不减。** 每条经验有生命周期，会被去重、降权、归档，避免记忆库变成
  越用越乱的垃圾场。

---

## 2. 两层结构（务必分开）

| 层 | 文件 | 谁能写 | 是否影响 Agent 行为 |
|----|------|--------|--------------------|
| 经验层（候选池） | `memory/lessons.json` | Agent / 脚本自动追加 | 否，仅供参考 |
| 规则层（硬约束） | `rules/*.md`、Gate 代码 | **仅人类审批后** | 是，Gate 强制执行 |

经验层只是**候选**。只有反复命中且经人类确认的经验，才“毕业”进入规则层。
这道分层是整个机制安全性的关键——它阻止 Agent 把“被 audit 拦住”自我合理化成
“audit 太严”并自动放松 Gate（棘轮反向转）。

---

## 3. 数据结构：失败卡片

每条经验是一张结构化的失败卡片，存于 `memory/lessons.json` 的 `lessons[]`：

```json
{
  "id": "L-2026-0042",
  "created": "2026-07-21T11:00:00+08:00",
  "trigger": "audit_blocked",
  "stage": "DECIDE",
  "project": "ar-politeia",
  "cycle": 3,
  "symptom": "claim C2 的 evidence 指向空壳 result.json（size>0 但无有效 key）",
  "root_cause": "preflight 的 config 检查只验证文件存在，不验证内容",
  "rule_candidate": "config 必须含非空 key，且被 experiment.command 实际引用",
  "scope": "all",
  "evidence_refs": ["research/versions/cycle-3/audit_final.json"],
  "hits": 1,
  "last_hit": "2026-07-21T11:00:00+08:00",
  "status": "proposed"
}
```

字段说明：

| 字段 | 含义 |
|------|------|
| `trigger` | 触发来源，见 §4 触发点枚举 |
| `symptom` | 观察到的现象（客观、可核对） |
| `root_cause` | 根因判断（可由 Agent 填，人类复核时校正） |
| `rule_candidate` | 建议固化成的规则，必须**可执行、可验证** |
| `scope` | 适用范围：`all` / `<project>` / `<stage>` |
| `evidence_refs` | 指向归档产物，支撑此条经验，便于回放 |
| `hits` / `last_hit` | 命中次数与最近命中，用于生命周期管理 |
| `status` | `proposed → adopted → deprecated`，见 §6 |

---

## 4. 触发点（自动写入，不依赖对话）

失败卡片在以下**确定性事件**发生时追加，触发点全部是框架已有信号，
不需要 LLM 去“读懂对话”：

| 触发 | 来源 | 备注 |
|------|------|------|
| `preflight_blocked` | `preflight` 退出码 1 | 携带 `failed[]` |
| `audit_blocked` | `audit` 退出码 1 | 携带 `failed_checks[]` |
| `job_failed` | `jobctl reconcile` 发现 `exit_code≠0` / 产物缺失 | |
| `replan` | STRATEGY 选择 replan | 记录 `replan_from` |
| `human_reject` | 人类决策为 `revise` / `terminate` | 附人类给出的理由 |

`symptom` 与 `failed` 明细可由退出信息机械填充；`root_cause` 与 `rule_candidate`
由 Agent 在该 Stage 结束时补全。首轮可只写 `symptom`，根因留空。

---

## 5. 去重与合并（自动）

写入前先比对已有条目，避免同类失败刷屏：

1. 用 `(trigger, root_cause, scope)` 做相似度归并键。
2. 命中已有条目 → `hits += 1`、更新 `last_hit`、追加 `evidence_refs`，**不新建**。
3. 未命中 → 新建 `proposed` 卡片。

这一步可由脚本完成，无需 LLM。合并逻辑保证 `hits` 真实反映“这类错误发生了几次”，
是后续“是否值得提升为规则”的核心依据。

---

## 6. 生命周期：proposed → adopted → deprecated

```
proposed ──(人类审批 + hits≥阈值)──▶ adopted ──(长期不命中/被取代)──▶ deprecated
    │                                                                      ▲
    └──────────────(人类判定为噪音/甩锅)───────────────────────────────────┘
```

- **proposed**：候选池默认状态，不影响 Agent 行为。
- **adopted**：满足 ①`hits ≥ 阈值`（建议 3）**且** ②人类确认是真规律，
  才提升。提升动作 = 把 `rule_candidate` 落进 `rules/*.md` 或 Gate 代码，
  并在卡片记录 `promoted_to`（指向具体规则/代码位置）。
- **deprecated**：`adopted` 规则长期不再命中、或被更强规则取代、或环境变化后失效，
  降级归档，保留可追溯历史。

> **硬性约束**：`proposed → adopted` 这一步**必须有人类点头**。
> Agent 可以给出 `rule_candidate` 和 `hits` 统计作为建议，但不得自行修改
> `rules/` 或 Gate 代码。这是防止棘轮反向转的唯一闸门。

---

## 7. 闭环验证：用数据说话

一条经验提升成规则后，要能验证它**真的减少了同类失败**，而不是让 Agent 自评：

- 每个 cycle 收尾时，统计各 `trigger` 类别的失败次数，写入
  `versions/cycle-<n>/` 的运行小结。
- 对比某规则 `adopted` 前后，其对应 `root_cause` 的 `hits` 增长是否变缓/停止。
- 若提升规则后同类失败仍高发 → 规则设计有误，回到 proposed 重新打磨，而非加更多规则。

---

## 8. 与现有框架的接线

- **不改变** Stage 序列与三个 Gate 的既有职责。
- **新增目录** `memory/`（放在单方案目录下，`research/memory/lessons.json`；
  跨项目通用经验放仓库根 `memory/lessons.json`）。
- **可选钩子**：`preflight` / `audit` 的 blocked 出口，增加一个 `--emit-lesson <path>`
  可选参数，退出前机械追加一张 `proposed` 卡片。默认关闭，保持工具纯确定性。
- **Stage 责任**：每个 Stage 结束、更新 `state.md` 时，Agent 顺带补全本轮新增卡片的
  `root_cause` / `rule_candidate`。
- **人类决策点**：在 DECIDE 后的人类决策环节，附带展示本轮 `hits` 达阈值的
  `proposed` 卡片，由人类批准是否提升。

---

## 9. 边界与反模式

| 反模式 | 后果 | 规避 |
|--------|------|------|
| 压缩整段对话当经验 | 噪音多、不可执行 | 只从 §4 触发点生成 |
| 经验只增不减 | 矛盾、过期、被忽略 | §6 生命周期 + 去重 |
| Agent 自动改 Gate/规则 | 棘轮反向转、自我松绑 | §6 人类闸门 |
| 用 Agent 自评经验有效性 | 自我合理化 | §7 用历史 hits 数据验证 |
| `rule_candidate` 写成“注意/尽量” | 无法固化、无法验证 | 必须可执行、可被脚本或 Gate 检查 |

---

## 10. 落地顺序建议

1. 先只做**经验层**：定义 `lessons.json` 结构 + 手动记录几轮真实失败，验证字段够不够用。
2. 加**自动触发 + 去重**：给 Gate 出口接 `--emit-lesson`，让卡片自动生成、自动合并。
3. 跑够几个 cycle 后，人工挑出 `hits` 高的候选，走一次 `proposed → adopted`，
   观察 §7 的失败曲线是否下降。
4. 确认闭环有效后，再考虑把生命周期管理脚本化。

> 不要一步到位做全自动闭环。先让人在回路里跑几轮，确认经验质量，再谈自动化程度。
