# git 工作流与远程仓库约定

本文件规定本仓库的 git 使用纪律，所有 Agent 与人类协作者必须遵守。

## 双远程分层

| 远程名 | 地址 | 角色 | 频率 |
|---|---|---|---|
| `github` | `https://github.com/ONE-ZERO-01/ar-politeia.git` | **异地容灾 + open science 公开**（2026-09-04 起设为 public） | 里程碑 |
| `umi` | `umi-wanwb:/home/wanwb/ONE/ar-politeia` | **日常自持远程**（内网，速度快、隐私自持） | 每次 commit |

- 二者**不可互相替代**：`umi` 是内网单点、依赖跳板 `thu_wwb`，抗不住机房级故障，不是容灾；`github` 提供真异地备份。
- 仓库名 `ar-politeia` 与研究核心对应，`project_id = ar-politeia`。

## commit 边界（不是按 Agent 动作，而是按研究事件）

- **实验级**：`experiment(<exp_id>): pass — <summary>`（含脚本 + `result.json` + 结论）。
- **循环级**：`cycle(1): strategy=replan`（一个 orchestrator cycle 结束）。
- **文档/规则级**：`docs: …` / `rules: …`。
- 禁止：每个 agent 子步骤各提交一次（产生噪音）、把中间态当成果提交。

## 提交内容边界

- **进 git**：源码、`result.json`（含 `pass` 判定的小文件）、计划书、`rules/`、`AGENTS.md`。
- **不进 git**（已在 `.gitignore`）：`research/jobs/*/workspace/`、大 CSV/图/PDF、`.autoresearcher/orchestrator/`（运行态真相源，由 orchestrator 管，不归 git）、`__pycache__`。
- `result.json` 属于「结论」，必须提交；`workspace/` 属于「产物」，不提交。

## push 纪律

- 日常：`git push umi`（每次 commit 顺手推，内网快）。
- 里程碑（满足任一即 `git push github`）：
  1. 任一实验产出原创正/负结果；
  2. 论文初稿成型（哪怕草稿）；
  3. 每 30 天兜底一次。

## 结果回传同步（服务器 → 本地）

研究结果（代码、`result.json`、`findings.json`、论文 `.tex`/`claims.json`、审稿、strategy
决策）由服务器上的 Agent 产出，落于共享 NFS 工作区但**尚未进 git**。回传本地按以下两步：

1. 在服务器（`ssh zeus`）提交结果，`.gitignore` 会自动排除数据（`workspace/`、`*.pdf`、
   `.autoresearcher/` 运行态）：

   ```bash
   cd /home/wanwb/ONE/ar-politeia
   bash scripts/commit-research.sh "cycle(1): strategy=replan"
   ```

2. 在本地拉取：

   ```bash
   bash scripts/sync-research.sh
   ```

数据永不跨过此边界：服务器提交时只暂存 `.gitignore` 允许的文件，本地拉取只拿这些提交。

## 安全红线

- 永不 `push --force`（尤其对 `github` 与 `umi` 主分支）。
- 永不提交密钥、token、`.env`（GitHub token 已存于本机 keyring，不落盘到仓库）。
- 运行态 `.autoresearcher/orchestrator/state.json` 由 orchestrator 唯一管理，git 不覆盖。
