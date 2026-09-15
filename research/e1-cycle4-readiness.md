# E1 Cycle 4 启动就绪审查

日期：2026-09-15。状态：**E1-C4 runner 已实现，阻塞于正在运行的 64-seed V1F 独立校准**。
本文件只准备设计，不授权或启动确认性数据。

## 当前结论

旧 `E1-MATCHED-LANDSCAPES` 与 `research/parameter_lock.json` 属于 Cycle 3，不能直接改名复用。
Cycle 4 已改变模拟器、必需稳态指标、稳态 Gate 单位、物理时长与误差校准方式。V1F 通过后需要
新建 `parameter_lock.cycle4.json` 和 `E1-MATCHED-LANDSCAPES-C4` 作业，保留旧文件作为历史证据。

## 已修复的启动缺口

1. **实验 ID 已独立接线。** `run_landscape_study.py` 已识别 `E1-MATCHED-LANDSCAPES-C4`，
   Cycle 3 四条件分支保持不变；C4 只生成 matched clustered/shuffled 两条件。
2. **稳态 Gate 已重写。** C4 使用两个相邻 144 帧窗口，分别判定尾窗条件 ensemble 稳态、
   跨窗稳定性和独立 seed 精度；逐运行稳态及 temporal ESS 继续输出但不替代独立精度 Gate。
3. **校准 schema 已分离。** C4 只接受通过的 `V1F-NONFLAT-CALIBRATION-C4`，读取
   `numerical_resolution_limits`，并从 config 读取独立冻结的 `scientific_sesoi`。
   数值误差界和科学 SESOI 必须作为两个字段分别绑定，不能把前者改名成后者。
4. **尺度已对齐。** 旧 E1 使用 `N=2000, 128×128`，V1F 校准 `N=1000, 64×64`。
   C4 主确认应先使用已校准尺度；`N=2000/128×128` 应进入 E3 的独立尺度稳健性设计。
5. **旧四条件已经拆分。** C4 E1 主确认矩阵只含 matched clustered/shuffled；flat 与
   no-exchange 不参与主效应 Gate，通道语义留给 E2-C4。

本轮新增 5 项契约测试，总测试为 158/158。尚未关闭的启动缺口是：V1F 必须整体通过、生成并
绑定最终 C4 参数锁、用不含 E1 效应方向的方差依据冻结 seed 数，以及在 umi 执行新的 V0G 实现 Gate。
E1-C4 seeds 必须排除 Cycle 1–3 和所有 Cycle 4 校准 seeds，并禁止
   outcome-dependent replacement。

## 待冻结的 C4 契约

V1F 通过后，新参数锁至少包含：

- simulator/model/source/analysis commit 与 V1F `numerical_calibration.json` SHA-256；
- `N=1000`、`64×64`、`dt=0.005`（V1F 最细步长）、`total_time=4500`、输出间隔 5、
  最后 144 帧、2σ 形状阈值、drift≤0.1、ESS≥4；
- 交换、运动、生产—衰减及随机子流参数，单 rank、OMP=1；
- 条件 ensemble stationarity/precision Gate 和逐运行诊断保留政策；
- clustered/shuffled 的资源总量、直方图、可达面积、初始 GID/位置/动量/财富逐 seed 匹配；
- 配对 bootstrap、配对 sign-flip、三个主空间指标的 Holm FWER=0.05；
- 缺失运行、超时、非有限值、阈值失败和 null/equivalence 结果的固定处理；
- 已授权计算预算与实际并行策略。

## 科学效应阈值候选

数值分辨率由 V1F 给出；科学 SESOI 在查看 E1-C4 结果前独立冻结。建议以指标自然范围的 2.5%
作为最小可解释变化：

| 指标 | 自然范围 | 候选 SESOI |
|---|---:|---:|
| resource-density Spearman rho | [-1, 1] | 0.05 |
| density Moran's I | 约 [-1, 1] | 0.05 |
| occupancy entropy | [0, 1] | 0.025 |
| wealth Gini（次要） | [0, 1] | 0.025 |

主张支持要求配对效应方向确定、Holm 校正通过，并且区间与效应幅度同时越过
`max(V1F numerical limit, scientific SESOI)`。若效应落入该等效区，记录为可解释的 null/等效结果，
不把它当执行失败。

## 启动顺序

1. V1ED 已冻结 64-seed 保守校准样本量；V1F 已通过 preflight 并正在 umi 执行；
2. E1-C4 runner/tests 已完成本地实现，保持不读取 V1F 的中间科学指标；
3. V1F 全过后，生成只读 C4 参数锁候选及 SHA-256，并绑定最终数值分辨率；
4. 依据只使用方差、不使用 E1 效应方向的功效分析冻结配对 seed 数及未见 seed 清单；
5. 在 umi 执行 V0G 实现 Gate，随后冻结参数锁为 final；
6. E1-C4 通过 preflight 后才提交确认性作业。
