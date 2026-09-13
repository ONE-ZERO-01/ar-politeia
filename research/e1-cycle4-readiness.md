# E1 Cycle 4 启动就绪审查

日期：2026-09-13。状态：**阻塞于 V1C 数值校准**。本文件只准备设计，不授权或启动确认性数据。

## 当前结论

旧 `E1-MATCHED-LANDSCAPES` 与 `research/parameter_lock.json` 属于 Cycle 3，不能直接改名复用。
Cycle 4 已改变模拟器、必需稳态指标、稳态 Gate 单位、物理时长与误差校准方式。V1C 通过后需要
新建 `parameter_lock.cycle4.json` 和 `E1-MATCHED-LANDSCAPES-C4` 作业，保留旧文件作为历史证据。

## 已发现的启动缺口

1. **实验 ID 尚未接线。** `run_landscape_study.py` 的条件生成、参数锁验证、聚合分支仍只识别
   `E1-MATCHED-LANDSCAPES`；C4 ID 当前会被拒绝。
2. **旧 E1 使用逐运行全合取稳态且没有独立 precision Gate。** C4 必须复用 V1C 验证后的
   landscape×condition ensemble 稳态/ESS，同时继续输出逐运行诊断。
3. **校准 schema 不同。** 旧 `load_e0_calibration` 读取
   `sesoi_frozen_before_confirmatory_analysis`；V1C 输出的是 `numerical_resolution_limits`。
   数值误差界和科学 SESOI 必须作为两个字段分别绑定，不能把前者改名成后者。
4. **尺度不匹配。** 旧 E1 使用 `N=2000, 128×128`，V1C 校准 `N=1000, 64×64`。
   C4 主确认应先使用已校准尺度；`N=2000/128×128` 应进入 E3 的独立尺度稳健性设计。
5. **旧四条件混入机制诊断。** C4 E1 的主确认矩阵应只含 matched clustered/shuffled；flat 与
   no-exchange 不参与主效应 Gate，通道语义交给 E2-C4 的独立设计。
6. **旧 seeds 已见结果。** C4 E1 必须排除 Cycle 1–3、V1/V1B/V1C 的所有 seeds，并禁止
   outcome-dependent replacement。

## 待冻结的 C4 契约

V1C 通过后，新参数锁至少包含：

- simulator/model/source/analysis commit 与 V1C `numerical_calibration.json` SHA-256；
- `N=1000`、`64×64`、`dt=0.005`（V1C 最细步长）、`total_time=3000`、输出间隔 5、
  最后 144 帧、2σ 形状阈值、drift≤0.1、ESS≥4；
- 交换、运动、生产—衰减及随机子流参数，单 rank、OMP=1；
- 条件 ensemble stationarity/precision Gate 和逐运行诊断保留政策；
- clustered/shuffled 的资源总量、直方图、可达面积、初始 GID/位置/动量/财富逐 seed 匹配；
- 配对 bootstrap、配对 sign-flip、三个主空间指标的 Holm FWER=0.05；
- 缺失运行、超时、非有限值、阈值失败和 null/equivalence 结果的固定处理；
- 已授权计算预算与实际并行策略。

## 科学效应阈值候选

数值分辨率由 V1C 给出；科学 SESOI 在查看 E1-C4 结果前独立冻结。建议以指标自然范围的 2.5%
作为最小可解释变化：

| 指标 | 自然范围 | 候选 SESOI |
|---|---:|---:|
| resource-density Spearman rho | [-1, 1] | 0.05 |
| density Moran's I | 约 [-1, 1] | 0.05 |
| occupancy entropy | [0, 1] | 0.025 |
| wealth Gini（次要） | [0, 1] | 0.025 |

主张支持要求配对效应方向确定、Holm 校正通过，并且区间与效应幅度同时越过
`max(V1C numerical limit, scientific SESOI)`。若效应落入该等效区，记录为可解释的 null/等效结果，
不把它当执行失败。

## 启动顺序

1. 等待 V1C 225/225 完成并通过 reconcile；
2. V1C 任一 Gate 失败则停止 E1，归档负结果并进入独立诊断；
3. V1C 全过后，生成只读 C4 参数锁候选与 SHA-256，补齐 E1-C4 runner/tests；
4. 在 umi 执行新的实现 Gate，随后冻结参数锁为 final；
5. 依据只使用方差、不使用 E1 效应方向的功效分析冻结配对 seed 数；
6. E1-C4 通过 preflight 后才提交确认性作业。
