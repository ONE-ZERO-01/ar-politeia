# V1C 独立条件 ensemble 数值校准设计

日期：2026-09-13。前置诊断：`V1BD-ENSEMBLE-DIAGNOSTIC-C4`。V1C 使用全新模拟结果，
不能重写 V1 或 V1B 的失败结论。

## 冻结依据

V1BD 显示 V1B 最后 96 帧的 9 个 landscape×dt ensemble 全部通过稳态，但 6 个条件的时间
ESS 低于 4；限制数值单元按已观察 paired SD 需要 14 个重复。V1C 在执行前固定为 15 个新 seeds、
最后 144 帧和更晚的平衡后区间。条件 ensemble 是数值估计量本身；逐 seed 时间序列仍保存和报告，
但不再把随重复数增加而必然变严的 270 项全合取当成总体均值 Gate。

## 注册设计

- seeds：`9001, 9011, 9029, 9041, 9059, 9071, 9091, 9103, 9127, 9133, 9151, 9161, 9181, 9199, 9209`；
- 步长层：3 个非平坦景观 × 3 个步长 × 15 seeds，共 135 runs；
- 顺序层：clustered × canonical/permuted × 3 个步长 × 15 seeds，共 90 runs；
- 总计 225 runs，人口 1000、网格 `64×64`、`total_time=3000`、每 5 时间单位输出；
- 稳态窗为最后 144 帧，即时间 2285–3000；drift≤0.1、ESS≥4、2σ 形状阈值和各指标绝对
  漂移容差不变；
- 数值上限不变：Spearman/Moran 0.02，entropy/Gini 0.01；
- 8 个单线程 CPU reference 进程并行，单 run 超时 7200 秒。

## Gate

1. 225 个运行全部完成，输入匹配审计通过，严格数值状态有限且财富非负；
2. 每个 landscape×dt 的六项 ensemble 时间序列均通过稳态和 ESS；
3. 三景观 fine-vs-finest 的 `|mean|+2SE` 不超过冻结数值上限，且收敛趋势通过；
4. 最细步长 canonical/permuted 的误差界不超过上限并被离散化界覆盖；
5. 任一 Gate 失败均归档为有效负结果，不替换 seed、不调阈值。

预计约 52.16 CPU 小时、8.2 墙钟小时和 25 GB ignored workspace。用户已授权不限制计算资源；
当前经过验证的模拟器没有 GPU backend，因此继续使用 CPU reference。
