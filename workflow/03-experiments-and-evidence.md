# 实验执行与证据

## 实验声明

`local` 实验应声明：

- 目的、关联 claim、baseline、ablation、指标和验收标准。
- 参数列表形式的 `command`，禁止拼接 shell 字符串。
- `commit_id`、config、环境快照和输入数据 checksum。
- seeds；P0 默认至少三个，或提供 `seed_waiver`。
- `workspace_inputs`、`timeout_seconds`、`gpu_count`。
- artifact 路径和失败策略。

详细硬性要求见 [实验复现性规则](../rules/experiment-reproducibility.md)。

## 计算策略选择

实验过慢时，Agent 可以自主选择性能优化、替代算法、快速筛选或混合方案。框架不要求固定
尝试顺序。关键是说明结果的证据角色与适用边界。

```json
{
  "computational_strategy": {
    "approach": "两粒子 Benettin 快速筛选，变分方法验证关键点",
    "evidence_role": "screening",
    "supports_core_claim": false,
    "evidence_boundary": "只选择候选点，不直接证明核心 Lyapunov claim"
  }
}
```

若筛选或近似方法直接支撑核心 claim，必须再声明参考验证或方法学论证。详细规则及扩展字段
见 [计算策略](../rules/computational-strategy.md)。

## 代码对齐审查

实验代码在提交前必须通过代码对齐审查——这是 Hook 纪律，不过不准跑实验。

**开干净 session**，只读 `plan.json` 和实验代码目录，不带前一轮上下文。
审查代码是否完整实现了计划中声明的每个 claim、baseline、ablation 和指标，是否存在硬编码参数。
输出 `review_log.json`，记录每个 claim 的覆盖情况和发现的问题。

- 全部通过 → Preflight。
- 有未覆盖的 claim → 回 EXPERIMENT 设计修代码。

## Preflight

提交前检查：

- 源仓库不是 dirty，计划 commit 与当前 HEAD 一致。
- config 和环境快照存在、非空并生成 SHA-256。
- 数据 checksum、seed、artifact 和 timeout 声明完整。
- 输入路径没有逃离项目根目录。
- 若声明 `computational_strategy`，策略、证据角色和证据边界必须明确。
- 筛选/近似方法直接支撑核心 claim 时，参考验证声明和 validation artifact 必须完整。

Preflight 约束证据质量，不限制 Agent 选择研究方法。

## 隔离执行

本地实验在以下目录运行：

`.autoresearcher/runs/<run_id>/jobs/<experiment_id>/workspace/`

声明的脚本、配置、环境文件和输入会复制到 workspace。相对路径写入不会直接污染源仓库。

长任务提交前先写 `handle.json`，完成后原子写入 `result.json` 和 `manifest.json`。恢复逻辑
依据结果记录、退出码和声明 artifact，而不是仅凭 PID 或任意输出文件判断完成。

## 已有证据导入

`import` 实验把已有证据快照复制到 run 内，并记录大小、SHA-256 和源 commit。manifest
使用 run 内相对路径，源项目移动或后续修改不会改变已归档证据。

实验指纹包含计划字段及 config、环境、脚本、输入和导入证据的实际 checksum。输入内容改变
后不得错误复用旧结果。
