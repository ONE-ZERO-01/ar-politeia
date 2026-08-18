# 写作、审稿与决策

论文阶段采用**长文 → 凝练 → 审稿 → 迭代**策略：完整长文是权威记录，Nature/PRL
等期刊版本从中提炼。审稿只针对凝练后的期刊版本；审稿发现科学问题时回溯到循环 A
补实验，再依次重写长文和期刊版本。

---

## WRITE-COMPREHENSIVE（完整长文）

WRITE-COMPREHENSIVE Agent 基于 `findings.json` 生成完整论文，产出位于
`paper/comprehensive/`：

- `paper/comprehensive/claims.json`
- `paper/comprehensive/main.tex`
- `paper/comprehensive/main.pdf`（由 Makefile 编译生成，Git 忽略）
- `paper/comprehensive/supplementary/`（补充材料、附录）

**此阶段不做审稿**。长文是研究的权威记录和后续凝练的唯一源头，直接进入 WRITE-JOURNAL。

**长文三大质量维度**（图文并茂 / 易读 / 详细）。长文无篇幅限制，以科学完整
和易读为首要目标；宁可详细，不可简略。

**（A）图文并茂** —— 长文不能是「公式 + 文字」的线性堆砌，须让读者看图即懂：

- 每个实验小节至少配一张图或一张表；无图无表的纯文字结果视为不完整。
- 核心机制与定理配示意图（TikZ 或矢量图）：最优分解 $M+N$、零和子空间
  $\mathcal N$、蛇形排列、双重中心化等结构，须有图示而非仅公式。
- 核心结论用「摘要框 / 定理框」（tcolorbox 或 amsthm 的 framed theorem）突出，
  读者扫一眼即可抓到要点。
- 数值结果优先用表格呈现，标注单位、容差阈值、与 `result.json` 的对应字段。
- 每张图 caption 必须自足：一句话说清「横轴 / 纵轴 / 关键观察 / 结论」，
  读者不读正文也能看懂图。

**（B）易读** —— 以「同行专家快速读懂、跨领域读者可跟上」为目标：

- 每个 section 开头写 2–3 句导语：本节讲什么 + 结论先行。
- 术语首次出现须给物理直觉解释，不能只给数学定义。
- 每个公式后必须紧跟一句文字解释其物理含义。
- 关键发现用一句「人话」概括（不依赖行话）。
- 章节层级 ≤ 3 层，标题清晰，读者可扫读目录定位。

**（C）详细** —— 长文是权威记录，宁详勿略：

- 完整实验参数表：维度、耦合范围、seed、实例数、容差阈值、收敛判据、硬件环境。
- 数值结果表与 `result.json` 逐项一致（有效数字、小数位不丢失）。
- 核心定理正文给 proof sketch，完整证明放 `supplementary/`（可复现、可查证）。
- 每个 claim 显式标注 evidence 路径（`jobs/<exp_id>/result.json`）。
- 负结果 / null result 详细记录，不得省略或淡化。
- Related Work 与 Discussion 充分展开；limitations 逐条列出真实边界，不得空写。

默认章节覆盖 Introduction、Related Work、Method、Experiments、Discussion、Limitations
和 Conclusion。不同领域可调整。

论文核心 claim 必须映射到 finding 和 evidence，不得引入未被证据支持的新结论。

**长文质量检查清单**（WRITE-COMPREHENSIVE Agent 完成前逐项自检）：

- [ ] 每个实验小节有图或表
- [ ] 核心定理 / 机制有示意图
- [ ] 核心结论有摘要框 / 定理框
- [ ] 每张图 caption 自足（横轴 / 纵轴 / 观察 / 结论）
- [ ] 每个 section 有导语、结论先行
- [ ] 术语首次出现有直觉解释
- [ ] 公式后紧跟文字解释
- [ ] 完整实验参数表 + 数值结果表
- [ ] 数值与 `result.json` 一致
- [ ] 完整证明在 `supplementary/`
- [ ] claim → evidence 路径显式标注
- [ ] 负结果未省略

---

## WRITE-JOURNAL（凝练期刊版本）

WRITE-JOURNAL Agent 以 `paper/comprehensive/` 为输入，为每个目标期刊生成适配版本。
默认目标期刊为 Nature 和 PRL，可通过 `project.json` 中的 `journals` 字段增减。

每种期刊版本独立产出：

- `paper/<journal>/main.tex`
- `paper/<journal>/main.pdf`（由 Makefile 编译生成，Git 忽略）
- `paper/<journal>/claims.json`
- `paper/<journal>/cover_letter.tex`（可选）

**凝练原则**：

1. **不引入新科学内容**：期刊版本只能从完整长文中**选取、浓缩、重组**，不得引入
   长文中没有的结果或 claim。
2. **聚焦核心叙事**：每种期刊根据其定位，选择最匹配的核心故事线。
3. **遵守期刊格式**：篇幅、章节结构、图表数量、引用格式必须符合目标期刊要求。
   格式规则见 [期刊格式规则](../rules/journal-formats.md)。
4. **调整影响力叙事**：针对不同期刊的读者群，调整 motivation、significance 和
   broader impact 的表述。

**核心法则——先删后改**：筛选核心 claim → 删次要实验 → 缩方法细节 → 简讨论方向 → 调语言匹配期刊读者群。

---

## PDF 编译 (Build)

`.tex` 源文件由 Git 追踪；`.pdf` 产物被 `.gitignore` 排除，通过 Makefile 按需生成。

**paper 目录下的 Makefile 提供完整构建管线**：

```bash
cd research/paper                          # 单方案论文目录

make           # 生成图表 + 编译所有 PDF
make figures   # 仅从 gen_fig*.py 生成图表 PDF
make main.pdf  # 仅编译某篇论文
make arxiv     # 编译 arXiv 投稿包版本
make clean     # 清理编译中间产物 (*.aux, *.log 等)
make distclean # 清理所有生成文件（含 PDF 和图表）
```

**构建管线**：
1. `make figures` → 运行 `gen_figures.py` 及 `gen_fig3.py`~`gen_fig8.py`，输出图表到 `figures/`
2. `make main.pdf` 等 → `latexmk -pdf` 自动处理多遍编译（pdflatex → pdflatex）

**何时编译**：
- WRITE-JOURNAL 完成后、REVIEW 开始前（REVIEW Agent 需要读 PDF）
- DECIDE 前（audit 检查 PDF 大小/页数/格式合规）
- 修改 .tex 后重新生成最新版本

**注意**：PDF 文件不在 Git 中，clone 新环境后需先 `make` 才能获得可读版本。

---

## REVIEW（期刊版本审稿）

每个期刊版本启动三个相互隔离的审稿 Agent：

- **PRL/专业期刊视角**：新意、主张强度、科学定位，以及稿件是否符合该期刊的标准。
- **Broad-impact 视角**：跨领域意义、叙事可读性和影响范围。
- **Technical 视角**：方法、误差、baseline、反例和复现性。同时对照 `findings.json`
  验证期刊版本中的 claim 是否有对应的 evidence 支撑。

审稿输出必须标记 `simulated: true`，不得冒充真实期刊意见。

审稿**同时关注两个维度**：

| 维度 | 检查内容 |
|------|----------|
| 科学正确性 | 每个 claim 是否有 finding/evidence 支撑；数值是否一致；是否漏掉关键限制条件；是否 overclaim |
| 期刊适配 | 篇幅、图表数、格式是否符合目标期刊；叙事是否聚焦；跨领域影响力表述是否到位 |

每个审稿 Agent 还必须输出结构化 `actionable_items`：问题来源、优先级、类型、动作、
成本估计和 acceptance。框架将三份审稿汇总为 `improvement_plan.json`。从第二轮开始，
审稿 Agent 依据 acceptance 标记上一轮项目的 `resolved_item_ids` 和
`unresolved_item_ids`，框架生成 `iteration_summary.json`。

**`iteration_summary.json` 是跨 cycle 传递"历史教训"的唯一载体**（新 cycle 不加载 `versions/`），必须包含：

- 本轮 claim 变化：哪些被删除/替换/收缩，以及原因。
- 被放弃的方向与方法：什么尝试被证明不可行，为什么。
- 核心教训：下一轮 Agent 必须知道的已踩过的坑。
- 未解决风险：哪些 P0/P1 问题仍待解决。

---

## 审稿迭代 Loop

`WRITE-COMPREHENSIVE → WRITE-JOURNAL → REVIEW → STRATEGY`

每一轮 STRATEGY Agent 汇总所有期刊版本的审稿结果后决定跳转方向。

出现 fatal、major concern、reject 或 major revision 时，问题类型决定路径：

- **必须重新设计并执行实验**：缺少关键 baseline/ablation、样本或 seed 不足、统计检验
  不充分、实验设置不能区分替代解释、方法或数值实现存在缺陷、关键反例未检验、证据无法复现。
  → `replan`，回到循环 A 补实验，完成后依次重写 WRITE-COMPREHENSIVE 和 WRITE-JOURNAL。
- **通常只需改稿（期刊版本层面）**：现有证据充分，但论文结构、表述、图表、引用、claim
  强度、limitations 或期刊定位需要修改。
  → `revise`，回到 WRITE-JOURNAL 修改对应期刊版本。
- **可以继续**：审稿意见不影响核心 claim，且已有 finding/evidence 可以明确回应。
  → `continue`，进入 DECIDE。
- `request_human`：需要额外预算、权限或人工边界判断。

新审稿必须针对重新生成的最新 PDF，不复用上一轮审稿会话。历史 reviews 和论文版本保存在
`versions/cycle-<n>/`。

**停止条件**：

- 每个目标期刊版本都没有 fatal/P0 问题。
- major/P1 问题已解决，或被证据支持地降级为 limitation。
- 所有期刊版本的 claim 与 findings/evidence 完整对应。
- 各期刊版本与完整长文的科学内容一致。
- 继续迭代的信息增益低于成本，或达到 `budget.max_cycles`。

---

## DECIDE 与最终审计

DECIDE Agent 综合 findings、各期刊 reviews、预算和 Gate，生成 `decision_packet.json`。
决策包中列出每个目标期刊版本的投稿建议（submit / revise / do-not-submit），但 Agent
不能自行投稿。

最终 evidence audit 检查：

- plan claim 是否都有 finding。
- paper claim（所有版本）是否映射到 finding。
- evidence 是否位于 run 内。
- manifest 退出码、artifact 大小和 SHA-256。
- 本地实验 preflight、config 和环境绑定。
- JSON 格式以及 NaN/Inf。
- PDF 大小、页数、必需章节和参考文献等项目级投稿规则。
- 期刊版本格式合规（篇幅、图表数等）。
- 期刊版本与完整长文的科学一致性抽查。
- 可选 clean-clone 中的配置化复现命令。

审计产物为 `reproducibility-bundle.json` 和 `submission/clean-clone.json`。任一启用的
审计失败时不能进入 `DONE`。clean-clone 默认关闭，项目明确配置命令后启用。

最终人类动作包括 `submit`、`revise`、`replan` 和 `terminate`。人类可选择投哪个期刊，
或在多个期刊版本都通过时同时投稿（如果期刊政策允许）。
