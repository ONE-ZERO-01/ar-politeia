# AutoResearcher 框架设计与部署指南

本文描述 AutoResearcher 多 Agent 研究框架的设计、实现与部署，目标是可复用到其他项目。
以 AR-Politeia 为运行示例，框架本身与具体研究课题无关。

目标拓扑（也是你推广到其他项目时的拓扑）：

- 本地 macOS：代码与研究产物的 git 权威。
- zeus：控制面，有全量外网，跑编排器 + Codex CLI + LLM Provider（DeepSeek）。
- umi：算力节点（A100），只跑数值实验。
- zeus 与 umi 共享 NFS `/home`，同一项目根目录两边即时可见。

---

## 1. 框架解决什么问题

AutoResearcher 是可恢复的多 Agent 研究 DAG。把“做一项科研”拆成
`PLAN → EXPERIMENT → ANALYZE → WRITE → REVIEW → DECIDE`，用显式 DAG 编排多个隔离
Agent，并在关键边界插入确定性 Gate 做结构验证。

核心设计边界：

- 一次只探索一个研究方案，不并行多方向。
- Agent 做科学判断：提计划、设计实验、分析、写论文、决定下一轮方向。
- Gate 做结构验证：只检查确定性约束（文件存在、路径不逃逸、产物契约、checksum），
  不替 Agent 做科学判断。
- 人类只在边界介入：预算、权限、投稿。
- 崩溃可恢复：每次状态转换原子写 state.json，中断后可续跑。

这条边界让 LLM 的“不可靠”被确定性 Gate 兜住，而科学判断仍留给 Agent。

## 2. 三机拓扑与数据流

```
本地 macOS（git 权威）
   │  git push umi（代码/计划）
   │  git pull umi（结果回传）
   ▼
umi-wanwb:/home/<user>/<project>   ← 共享 NFS，zeus/umi 同一份工作副本
   ▲                    ▲
   │ ssh umi（zeus→umi） │ ssh zeus / ssh umi-wanwb（本地→服务器）
   │                    │
zeus（控制面） ───────▶ umi（算力）
  orchestrator          numerical experiments
  Codex CLI + DeepSeek
```

要点：

- zeus 是编排器唯一运行位置：有全量外网，供 LLM Provider。
- umi 是数值实验唯一运行位置：脚本用 host guard 强制。
- 两边共享 NFS，产物路径一致，不需要 scp/rsync。
- 跨设备同步研究产物一律走 git，不走运行态。

## 3. 代码结构

```
src/autoresearcher/
├── orchestration/          # 编排器
│   ├── graph.py            # 图 schema 加载与校验
│   ├── runner.py           # 异步执行、崩溃恢复、cycle 控制
│   ├── contracts.py        # 无依赖 JSON Schema 子集校验
│   ├── timeline.py         # 只读研究历程 HTML
│   └── cli.py              # validate/render/run/status/reset/timeline
└── foundation/             # 三个确定性 Gate（不依赖编排器）
    ├── preflight.py        # 实验提交前复现性检查
    ├── jobctl.py           # 幂等作业提交/状态/恢复
    ├── audit.py            # 投稿前证据链审计
    └── evidence_check.py   # 每周期证据存在性 Gate
```

安装：`pip install -e .`，或服务器上用 `PYTHONPATH=src` 直接运行。
入口：`autoresearcher-graph`（即 `python3 -m autoresearcher.orchestration`）。

## 4. 编排器

### 4.1 图文件顶层字段

| 字段 | 说明 |
|------|------|
| schema_version | 固定为 1 |
| project_id | 项目标识 |
| workspace | 相对图文件的根目录，所有路径必须解析在其内 |
| state_file / logs_dir | 运行态路径 |
| max_parallel | 并发节点数 |
| max_cycles | 最多运行几个 cycle |
| adapters / default_adapter | Agent CLI 适配器 |
| nodes | 节点数组 |
| cycle_control | 循环决策与人工门 |
| budget | max_agent_seconds_per_cycle（每周期 agent 壁钟熔断） |

### 4.2 节点类型

| kind | 说明 |
|------|------|
| agent | 启动 Agent CLI（经 adapter），读 inputs、写 outputs |
| command | 直接执行命令数组（不经过 shell） |
| gate | 确定性校验命令，退出码 0 即通过 |
| barrier | 依赖满足即成功，不执行任何东西 |
| foreach | 读 tasks_file，按 task_template 对每个任务并行执行 |

节点通用字段：id、depends_on、workdir、inputs、optional_inputs、outputs、
output_schemas（输出 JSON 契约校验）、timeout_seconds、retries、env、
exclusive_resources、when（条件跳过）。

### 4.3 执行与恢复

- 每次状态转换 temp + rename 原子写 state.json。
- fcntl.flock 文件锁防止两个 runner 同时跑同一 state。
- 中断恢复：RUNNING 回 PENDING；SUCCEEDED 节点若声明输出消失则回退。
- 节点失败：指数退避重试；agent 重试时把上次错误注入提示词。
- AWAITING_HUMAN：cycle_control.human_values 命中即暂停，等人工写决策文件。

### 4.4 Adapter（Agent CLI）

agent/foreach(agent) 节点通过 adapter 启动真实 Agent CLI。示例（zeus 上的 Codex）：

```json
"codex": {
  "command": [
    "codex", "exec",
    "--ephemeral",
    "--dangerously-bypass-approvals-and-sandbox",
    "--color", "never",
    "-C", "{workspace}",
    "-"
  ],
  "prompt_mode": "stdin"
}
```

占位符：{workspace}、{workdir}、{node_id}、{prompt}、{state_file}、{output_last_message}。
环境变量：AUTORESEARCHER_NODE_ID、AUTORESEARCHER_WORKSPACE、AUTORESEARCHER_INPUTS_JSON、
AUTORESEARCHER_OUTPUTS_JSON 等。

### 4.5 输出契约（output_schemas）

节点产出 JSON 后，编排器用 contracts.py 校验结构。该校验器只实现无依赖的 JSON Schema 子集：
type / enum / required / properties / items / minItems / minLength。未知关键字只告警、不强制。

## 5. 三个确定性 Gate

| Gate | 用途 |
|------|------|
| preflight | 提交前：commit/env/config/seeds/artifacts/checksums/计算策略 |
| jobctl | 幂等提交/状态/崩溃恢复（INTENT → RUNNING → result.json） |
| audit | 投稿前证据链完整性 + SHA + NaN/Inf |
| evidence_check | 每周期：ANALYZE 后校验证据路径真实存在 |

Gate 独立于编排器，可单独调用；编排器把它们作为 gate/command 节点接进同一张图。

## 6. 研究产物链（扁平 research/）

```
research/question.md → plan.json → jobs/<exp_id>/ → findings.json
    → paper/comprehensive/ → paper/<journal>/
        → orchestration/reviews/ → orchestration/strategy.json
            → decision_packet.json → reproducibility-bundle.json
```

同步 research/state.md（进度摘要）、research/versions/cycle-n/（历史归档）。

git 边界（关键）：结论（result.json、findings.json、.tex、claims.json、审稿）进 git；
产物（workspace/、大 CSV/图、*.pdf、.autoresearcher/ 运行态）不进 git。

## 7. 计算环境部署

### 7.1 zeus 装 Codex CLI（无 sudo，用户级）

```bash
cd ~/.local
curl -fsSL -o node.tar.xz https://nodejs.org/dist/latest-v20.x/node-v20.20.2-linux-x64.tar.xz
tar -xf node.tar.xz && mv node-v20.20.2-linux-x64 node
export PATH="$HOME/.local/node/bin:$PATH"
npm install -g @openai/codex
```

### 7.2 配置 DeepSeek（Responses API）

`~/.codex/config.toml`：

```toml
model_provider = "deepseek"
model = "deepseek-v4-pro"

[model_providers.deepseek]
name = "DeepSeek"
base_url = "https://api.deepseek.com"
env_key = "DEEPSEEK_API_KEY"
wire_api = "responses"
```

密钥放 `~/.codex/deepseek.env`（权限 600，git 仓库之外）：

```bash
export DEEPSEEK_API_KEY="sk-..."
```

注意：Codex CLI 2026-02 起只用 wire_api = "responses"，不再支持 Chat Completions。
DeepSeek 老模型只有 /chat/completions 会 404，要用原生支持 Responses 的 v4 系列
（deepseek-v4-flash / deepseek-v4-pro）。

### 7.3 启动器

scripts/run-orchestrator.sh：设 PATH → source 密钥 → 设 PYTHONPATH=src →
exec python3 -m autoresearcher.orchestration run <graph>。

### 7.4 跨机路由（zeus → umi）

- 本地 mac 到 umi：ssh umi-wanwb（经 thu_wwb ProxyJump）。
- zeus 到 umi：ssh umi（umi-wanwb 是本地 mac 的别名，zeus 上解析不了）。
- 数值脚本用 host guard 强制在 umi 跑（检查 socket.gethostname() == "umi"）。
- 实验 worker 提示词：execution_host=umi 且不在 umi 时，经 ssh umi '...' 执行。

## 8. git 与结果回传

双远程：github（异地容灾，里程碑 push）+ umi（日常自持，每次 commit push）。

结果回传（服务器 → 本地）：

1. 服务器（ssh zeus）：
   ```bash
   bash scripts/commit-research.sh "cycle(1): strategy=replan"
   ```
2. 本地：
   ```bash
   bash scripts/sync-research.sh   # git fetch umi + merge
   ```
   本地若有新代码，再 git push umi main。

数据边界（.gitignore 是唯一事实源）：

```
research/jobs/*/workspace/
*.pdf
.autoresearcher/*
!.autoresearcher/orchestrator/
.autoresearcher/orchestrator/*
!.autoresearcher/orchestrator/cycles/
```

## 9. 从零部署一个新项目（bootstrap checklist）

1. 复制框架 src/autoresearcher/，pip install -e .。
2. 写研究内容（research/question.md、hypothesis.md）。
3. 写 orchestration/research-graph.example.json + prompts + schemas。
4. 在 zeus 装 Codex CLI + 配 DeepSeek（第 7 节）。
5. 配 adapter + scripts/run-orchestrator.sh。
6. 配 git 双远程 + .gitignore + 回传脚本。
7. 冒烟测试：最小 agent→gate 图，验证编排器能 spawn agent 且输出契约通过。
8. 质量探针：让模型读真实研究输入、产出带 schema 校验的评审，确认推理质量。
9. 复制 example → research-graph.json，备份 tag，nohup 无人值守启动完整 DAG。

## 10. 已踩过的坑

1. 图命令参数必须与 CLI 一致：validate 只查图结构，不查命令参数。曾因图里给 preflight
   传了不存在的 --source-root 导致运行时才报错。
2. adapter 要匹配部署：例图里 cursor adapter 在 zeus 未安装，改为统一走 codex。
3. .autoresearcher/ 根目录文件要忽略：只保留 orchestrator/cycles/ 进 git。
4. NFS 双 IP：同一 /home 在 zeus 显示 192.168.0.21、umi 显示 10.0.0.21。
5. umi 外网是选择性的：github/pypi/deepseek 可达，raw.githubusercontent.com 超时。
6. DeepSeek 只用 Responses API，模型要选 v4 系列。
7. 非 bare 远程拒绝 push：当 umi 工作区有未提交结果时本地 push 会被拒；先服务器提交再 push。
8. --dangerously-bypass-approvals-and-sandbox 无 OS 级沙箱：agent 有全量权限，安全边界只剩
   prompt + Gate + 路径校验。跨用户共享服务器建议容器化或受限用户。
9. adapter_version 探针可能抓到 CLI 的 warning 行而非版本号（纯 cosmetic）。

## 11. 安全与隔离

见 rules/agent-containment.md：当前信任模型是“prompt 约束 + 确定性 Gate + 路径校验”，
无强制沙箱。启动真实 DAG 前至少做其一：受限用户、容器化、或降级 sandbox + 审批。

## 12. 常用命令速查

```bash
python3 -m autoresearcher.orchestration validate orchestration/research-graph.json
python3 -m autoresearcher.orchestration render   orchestration/research-graph.json
python3 -m autoresearcher.orchestration run      orchestration/research-graph.json
python3 -m autoresearcher.orchestration status   orchestration/research-graph.json
python3 -m autoresearcher.orchestration reset    orchestration/research-graph.json --node <id>
python3 -m autoresearcher.orchestration timeline
python -m autoresearcher.foundation.preflight --exp-dir research/jobs/E0 --priority P0
python -m autoresearcher.foundation.jobctl submit/status/reconcile --exp-id E0 ...
python -m autoresearcher.foundation.audit --run-dir research --claims-file paper/comprehensive/claims.json
```
