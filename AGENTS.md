# AGENTS.md

本文件是给所有平台 Agent（Cursor、Codex、Claude Code 等）的自动发现入口，会话开始即应读取。

## 项目是什么

AutoResearcher：可恢复的多 Agent 研究 DAG。每次只探索一个研究方案，产物平铺在 `research/`，
三个确定性 Gate（`preflight` / `jobctl` / `audit`）独立可调用。

当前研究方案：**AR-Politeia**（`project_id = ar-politeia`）。
完整工作流入口：[autoresearcher.md](autoresearcher.md)。
框架设计与部署（可复用到其他 zeus+umi 项目）：[FRAMEWORK.md](FRAMEWORK.md)。

## 计算环境（必读）

- **本地**：本仓库（macOS），是代码与研究的 git 权威。
- **算力**：A100 服务器 `ssh umi-wanwb`（登录后主机名 `umi`，4 × NVIDIA A100-40GB），
  经跳板 `thu_wwb`（`zeus`，有外网）ProxyJump 直达，一条命令即可。
  数值实验计算量大时可将计算搬到 A100 GPU——资源规格、何时用、技术栈现状与迁移步骤见
  [rules/gpu-compute.md](rules/gpu-compute.md)。
- **项目根目录（服务器）**：`/home/wanwb/ONE/ar-politeia`，即 `AR_PROJECT_ROOT`。
- **铁律**：本项目所有代码、文件、数据只放在 `$AR_PROJECT_ROOT` 内；实验代码在
  `research/src/experiments/`，声明与结果在 `research/jobs/<exp_id>/`，重产物写入
  `research/jobs/<exp_id>/workspace/`（git 忽略）。禁止写入 `$HOME` 根目录或项目外临时盘。
- **orchestrator 运行位置**：多 Agent DAG（`python -m autoresearcher.orchestration run ...`）
  **只在服务器 `zeus`（控制面）上运行**。本地 mac 与其他电脑只写代码/计划/看结果，不在本地跑
  orchestrator——运行态（`.autoresearcher/orchestrator/`：state.json、logs、lock）含本机
  绝对路径与进程锁，不该跨设备同步；且本地项目在 OneDrive 同步目录里，高频原子重写
  `state.json` 会与 OneDrive 同步冲突。`zeus` 有全量外网，用于 Codex CLI + DeepSeek 等
  LLM Provider。跨设备同步研究产物一律走 git，不走运行态。
- **数值实验运行位置（铁律）**：所有数值实验脚本（`research/src/experiments/*.py`，
  经 `jobctl` 提交运行的）**一律只在服务器 `umi` 上运行**，包括开发、调试、校准、
  冒烟测试，本地 mac 不运行任何数值实验。本地只写代码、写计划、看结果；实验的
  权威产物（`result.json`、图表）由服务器生成后回传 git。
- 详细见 [rules/server-config.md](rules/server-config.md)、[rules/gpu-allocation.md](rules/gpu-allocation.md)
  与 [rules/gpu-compute.md](rules/gpu-compute.md)。

## git 纪律（必读）

- 双远程：`github`（异地容灾，里程碑 push）+ `umi`（日常自持，每次 commit push）。
- commit 按研究事件（实验/循环/文档），不按 Agent 动作；结论（`result.json`）进 git，产物（`workspace/`）不进。
- 完整约定见 [rules/git-workflow.md](rules/git-workflow.md)。

## 常用命令

```bash
python3 -m pip install -e .
python -m pytest -q
python3 -m autoresearcher.orchestration validate orchestration/research-graph.example.json
python3 -m autoresearcher.orchestration run orchestration/research-graph.json
python3 -m autoresearcher.orchestration timeline  # 研究历程 HTML → research/timeline.html
```

## 关键约定

- 一次只探索一个研究方案，不并行多方向。
- 提交实验前跑 `preflight`，完成后 `jobctl reconcile`，投稿前 `audit`——任一不过就停下修复。
- 领域知识、服务器路径、GPU 纪律写入 `rules/`，不硬编码进 foundation 工具。
- Agent 做科学判断，Gate 做结构验证，人类只在预算/权限/投稿边界介入。
