# Agent 执行隔离（Containment）

本文件描述多 Agent 编排在共享服务器上的安全边界与必须采取的缓解措施。

## 当前信任模型

- orchestrator 在 `zeus` 上通过 codex adapter 启动 agent，adapter 当前使用
  `--dangerously-bypass-approvals-and-sandbox`。
- 这意味着每个 agent 节点在共享 NFS `/home` 上拥有**全量磁盘 + 网络权限**。
- 现有安全边界只有：prompt 约束 + 确定性 Gate + 输出路径校验。orchestrator 只校验
  “声明产物”的路径落在 workspace 内，**不约束 agent 的其它副作用**（写别的目录、连外网等）。

## 风险

- 一个被错误引导的 agent 理论上可以写 `$AR_PROJECT_ROOT` 之外，包括 `/home/wanwb`
  根目录或其他用户目录。
- Linux 上 Codex CLI 的原生沙箱（macOS seatbelt）不可用；`--sandbox danger-full-access`
  只是关闭沙箱，同样不提供隔离。

## 缓解（启动真实 DAG 前至少采用其一）

1. 用受限用户运行 orchestrator：该用户只对 `$AR_PROJECT_ROOT` 有写权限，对 `/home` 其余部分只读。
2. 容器化（Docker/Podman）：`/home` 只读挂载，仅项目根可写，并限制出网。
3. 至少把 adapter 从 `--dangerously-bypass-approvals-and-sandbox` 降级为
   `--sandbox danger-full-access` + 审批策略，保留一道人工/自动审批。

## 决策

- [ ] 在启动真实研究 DAG 前，采用上述缓解措施之一。
