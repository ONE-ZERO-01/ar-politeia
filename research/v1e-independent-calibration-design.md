# V1E 独立稳态数值校准设计

日期：2026-09-14。状态：**设计冻结，等待 runner 实现与 V0E 实现 Gate**。V1E 使用全新 seeds，
不能改变 V1C 的负结论。设计只依据 V1CD 的稳态、方差和运行成本诊断，不使用任何 E1 科学效应。

## 诊断依据

V1CD 精确复现 V1C 尾窗结果。前一个 144 帧窗口有 3/9 条件未稳态，尾窗降至 1/9；六个低精度
条件全部由时间 ESS<4 引起。与此同时，36 个相邻窗口变化的 `|mean shift|+2SE` 全部低于在
V1C 结果前写入 E1 readiness 的规划半宽，最大只占 68.5%。这说明继续把 ensemble 均值时间序列
的 ESS 当作独立 seed 总体均值精度会混合两个不同问题。15 seeds 的跨 seed 2SE 在 clustered 的
Moran 和 entropy 上略宽，观察方差对应的最大需求为 20 seeds。

## 冻结运行矩阵

- seeds：`10007, 10037, 10061, 10091, 10103, 10133, 10159, 10181, 10211, 10243,
  10267, 10289, 10313, 10343, 10369, 10391, 10427, 10453, 10477, 10499`；
- timestep 层：smooth/clustered/shuffled × `dt=0.02,0.01,0.005` × 20 seeds，共 180 runs；
- storage-order 层：clustered × canonical/permuted × 3 dt × 20 seeds，共 120 runs；
- 总计 300 runs，`N=1000`、`64×64`、`total_time=4500`、输出间隔 5；
- 分析最后两个相邻且不重叠的 144 帧窗口：前窗约 3065–3780，尾窗约 3785–4500；
- 模型参数、输入匹配、2σ 形状判据、数值误差上限和 CPU reference 与 V1C 相同；
- 8 个 OMP=1 进程并行，单 run 超时 10,800 秒。按 V1C 实测缩放预计约 90.76 CPU 小时、
  11.35 墙钟小时、约 50 GB ignored workspace。

## 分层 Gate

1. **执行与不变量**：300/300 完成、输入匹配、状态有限、财富非负；
2. **尾窗稳态**：六项 ensemble 时间序列在尾窗通过既有 drift 和 2σ reversal 判据；时间 ESS
   继续报告为动力学诊断，但不冒充独立重复精度；
3. **相邻窗口稳定性**：四个有界估计量的配对 `|mean shift|+2SE` 分别不超过预先存在的
   0.05/0.05/0.025/0.025；wealth variance 的变化界除以两窗均值尺度不超过 0.10，
   zero-wealth fraction 的绝对变化界不超过 0.01；
4. **独立 seed 精度**：尾窗每 seed 均值作为独立样本。四个有界估计量 2SE 半宽分别不超过
   0.05/0.05/0.025/0.025；wealth variance 相对 2SE 半宽不超过 0.20；zero-wealth fraction
   绝对 2SE 半宽不超过 0.01；
5. **步长与顺序**：V1C 的 `|mean|+2SE` 收敛、上限和 canonical/permuted Gate 原样保留。

这些 Gate 必须在产生 V1E 数据前写入 runner、测试和最终 config。任一失败均归档为新的有效负结果，
不得删除指标、替换 seed、缩窗或放宽阈值。V1E 全过后才允许生成 Cycle 4 最终参数锁；E1 当前仍阻塞。
