# Cycle 1 启动就绪状态与开放决策

日期：2026-08-20（Asia/Shanghai）

## 系统验证状态（全部通过）

| 项 | 结果 |
|----|------|
| 编排器 + Codex CLI 0.148.0 + deepseek-v4-pro（Responses API） | ✅ 端到端 SUCCEEDED |
| 最小 DAG 冒烟（agent → gate，产物契约 + gate） | ✅ 2 节点通过 |
| 研究推理质量探针（读真实 question/hypothesis，schema 校验评审） | ✅ 评审质量专家级 |

运行时位于 zeus（控制面），数值实验仍只在 umi。启动器：`scripts/run-orchestrator.sh`。

## 质量探针发现（LLM 评审，供研究循环参考，未经人工验证）

deepseek-v4-pro 在读真实研究输入后提出两点，建议下一轮 plan/strategy 参考：

1. **连通性/拓扑混淆**：空间打乱在保持像素直方图和可达面积的同时，会连带改变高资源区的
   渗流连通性、局地资源梯度与到高资源区的距离。主效应可能被“移动网络连通性 / 混合时间”
   解释，而非资源值空间自相关本身。建议增加一层“资源自相关 × 高资源区连通性”的对照，
   并记录平均首达距离 / 混合时间。
2. **2×2 消融边界**：足以判断“单通道是否充分、交互是否主导”（对应成功判据 3），但不能
   分解移动↔生产的间接/中介效应与反馈，也不能外推到全耦合自然态；交互显著时应只报组合
   效应（与方案预注册一致）。

以上不是对冻结 `plan.json` 的修改，只是存档供后续研究决策使用。

## 启动序列

B0（人工批准）→ 定参 → E0（单独预算）→ 冻结 SESOI + 绑定 SHA → E1-E3 解锁。

## 两个开放决策

1. **B0 预算人工批准**：见 [b0-budget-approval.md](b0-budget-approval.md)。
2. **冻结 plan vs 重规划**：正式 `orchestration/research-graph.json` 尚未创建。需决定
   `plan_experiments` 是 (a) 全量重规划，还是 (b) 从已冻结的 `research/plan.json` 与
   `research/jobs/*/` 继续。默认不建议 (a)，因为它可能覆盖人工冻结的 Cycle 1 设计。
