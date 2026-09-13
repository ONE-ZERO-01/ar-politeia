# V1CD 稳态估计量诊断设计

日期：2026-09-14。V1CD 只重分析 V1C 已固定的 225 个运行，不产生新的模拟数据，也不能改变
V1C 的失败结论。目标是区分物理平衡尚未完成、时间自相关导致的低 ESS，以及 15 个独立 seed
对总体均值已经提供的精度。

## 固定分析

- 校验 V1C `run_specs.json`、`numerical_calibration.json` 和
  `ensemble_stationarity_report.json` 的 SHA-256；
- 读取 135 个 timestep runs 的最后 288 帧，分成两个相邻、互不重叠的 144 帧窗口；
- 原样重现 V1C 尾窗的 1/9 稳态失败和 6/9 时间 ESS 精度失败，否则诊断停止；
- 对每个 landscape×dt×metric 报告前窗和尾窗 ensemble 稳态、时间 ESS、跨窗均值变化及其
  配对 `|mean shift|+2SE`；
- 以每个 seed 的尾窗均值为独立样本，报告跨 seed SD、SE、2SE 半宽和达到预先写入
  `e1-cycle4-readiness.md` 候选科学半宽所需的 seed 数；
- 候选规划半宽固定为 Spearman/Moran 0.05、entropy/Gini 0.025。它们只用于规划新设计，
  不作为 V1C 的替代 Gate。

## 决策用途

若失败仅来自低时间 ESS，而相邻窗口变化及独立 seed 精度稳定，则下一版可以把“时间序列已进入
稳定区间”和“总体均值的独立重复精度”拆成两个有统计意义的 Gate。若相邻窗口仍系统漂移，下一版
必须延长 burn-in/总时长或修改模型的慢松弛机制，并用全新 seeds 重校准。任何结论都不得启动 E1；
只有后续独立校准完整通过才解除阻塞。
