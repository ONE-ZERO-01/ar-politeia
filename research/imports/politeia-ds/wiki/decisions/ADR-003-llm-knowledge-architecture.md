# ADR-003: 采用五层 LLM 知识架构 + 会话级 planning

> 日期：2026-05-19  
> 状态：已接受  
> 来源：[[wiki/log#2026-05-19] change | 撰写可推广的 LLM 文档管理架构总览]

## 背景

项目已有 `raw/`、`docs/`、`wiki/`、`AGENTS.md` 与 `research-proposal` 权威源，但缺少：(1) 可推广的总览文档；(2) 复杂任务的会话级工作记忆；(3) 结构化 ADR 目录实践。

## 决定

1. 编写 `docs/llm-knowledge-architecture.md` 作为可推广方法论文档  
2. 安装 [planning-with-files](https://github.com/OthmanAdi/planning-with-files)（`.cursor/skills/` + hooks）  
3. `wiki/decisions/` 存放 ADR 正文；`wiki/log.md` 的 `decision` 条目仅作索引  
4. `DEVELOPMENT_PLAN.md` 顶部维护 **「当前焦点」** 小节（3–5 条活跃项）

## 理由

- 长期记忆（L0–L3）已成熟，短期任务编排（L4）是主要短板
- ADR 与 log 分离：log 可 grep，ADR 可深读
- 当前焦点避免 1000+ 行开发计划难以定位「下一步」

## 后果

- 复杂 Agent 任务须创建 `task_plan.md` 三文件，结束后归档到 `wiki/log.md`
- 季度或发版前执行 `lint` 并写入 log
- 会话三文件默认 gitignore
