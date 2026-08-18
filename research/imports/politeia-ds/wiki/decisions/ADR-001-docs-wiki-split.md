# ADR-001: 保留 `docs/`，与 `wiki/` 并列

> 日期：2026-04-19  
> 状态：已接受  
> 来源：[[wiki/log#2026-04-19] decision | 保留 `docs/`，与 `wiki/` 并列]

## 背景

建立 LLM Wiki 时，需决定正式长文（随机分布、并行设计、MOC、构建说明等）放在何处：全部迁入 `wiki/`，还是与 `wiki/` 分工。

## 选项

| 选项 | 优点 | 缺点 |
|------|------|------|
| A. 全部迁入 wiki | Agent 单目录检索 | 双份维护风险、长文难读 |
| B. `docs/` + `wiki/` 并列 | 人读长文、Agent 索引；各守其责 | 需约定链接与分工 |
| C. 仅 README + wiki | 极简 | 不足以承载研究型长文 |

## 决定

采用 **B**：`docs/` 为正式参考文档；`wiki/` 为 index、log、模块速查、概念/ADR。wiki **不**复制 `docs/` 全文，以 `[[docs/...]]` 链接。

## 理由

- 研究型项目需要可评审、可引用的成体系长文（L2）
- Agent 更需要轻量索引与时间线（L3），而非第二套全文仓库
- Karpathy LLM Wiki 模式 + 正式 `docs/` 层是已验证组合

## 后果

- `AGENTS.md` 与 `wiki/index.md` 必须维护 docs/wiki 分工说明
- 新文档默认进 `docs/`，wiki 只加摘要行
- 反模式：把 `docs/` 全文复制进 wiki
