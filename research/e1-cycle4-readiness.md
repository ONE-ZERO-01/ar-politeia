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
6. **promotion 已确定化。** `prepare_cycle4_confirmation.py` 分为 `prepare` 和 `finalize`
   两阶段：前者只接受完整通过且哈希一致的 V1F，生成不可执行的 candidate 锁；后者只接受
   umi 干净 checkout 上 Python 与 OpenMP OFF/ON CTest 全过的 V0G，并把新 reference binary
   SHA-256 写入 final 锁与 E1 config。检测到 E1 outcome、已 final 的锁、项目外路径、哈希不符
   或不完整 Gate 时均拒绝重写。
7. **binary 执行绑定已补齐。** E1-C4 runner 在任何数值执行前强制核对 64 位
   `binary_sha256`；缺失或不匹配立即失败，Cycle 3 历史任务的执行接口保持不变。
8. **V1F 归档已确定化。** promotion 的 `archive-v1f` 只有在 jobctl 正常退出、960 个唯一
   run spec 与 960 个成功 marker 精确对应、每个 run 有 health、所有 marker 绑定同一 OMP=1
   reference binary、输入审计通过且 calibration/steady 报告互相一致时，才生成 tracked
   `numerical_calibration.json`、紧凑 `result.json` 和逐产物 SHA manifest。

此前新增 5 项 E1-C4 契约测试；promotion/binary 绑定和干净 checkout Python 路径绑定继续补齐，
总测试为 165/165。V0G runner 现在显式把 `PYTHONPATH` 绑定到当前项目的 `src/` 并写入
`environment.json`，不依赖服务器曾执行 editable install。
尚未关闭的启动缺口是：V1F 必须整体通过、生成并
绑定最终 C4 参数锁，以及在 umi 执行新的 V0G 实现 Gate。样本量和 64 个未见 seeds 已在
`e1-cycle4-design.md` 冻结；它们排除 Cycle 1–3 和所有 Cycle 4 校准 seeds，并禁止
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

## 已冻结的科学效应阈值

数值分辨率由 V1F 给出；科学 SESOI 已在查看 E1-C4 结果前按指标自然范围的 2.5% 独立冻结：

| 指标 | 自然范围 | 冻结 SESOI |
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
3. V1F 完成后先执行 promotion `archive-v1f`；只有归档 verdict 全过才执行 `prepare`，一次生成
   只读 C4 candidate 锁、V0G 声明和带 64 个
   冻结 seeds 的 E1 job 声明；candidate 明确 `confirmatory_execution_authorized=false`；
4. 提交 candidate 研究事件并 push umi，使 V0G 运行于干净 checkout；
5. 在 umi 执行 V0G 实现 Gate，随后由 promotion `finalize` 绑定 V0G result 与 binary 哈希，
   冻结参数锁为 final；
6. E1-C4 在 umi 通过 `--prepare-only` 和 preflight 后才提交确认性作业。
