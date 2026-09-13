# V1 非平坦数值校准与顺序敏感性验证设计

日期：2026-09-13。实验：`V1-NONFLAT-CALIBRATION-C4`。前置 Gate：`V0C-SIMULATOR-TESTS-C4`。

## 1. 要解决的问题

V0 首次验证证明，多粒子串行原地交换不满足逐 GID 的精确存储重排不变性。该现象来自同一步内的交易按固定次序立即写回财富，后续交易读到的是已经更新的值。稳定 GID 和 seed 修复了交换随机符号的身份绑定，但没有让非交换的原地更新变成数学上的同时更新。

Cycle 3 的平坦场校准也不能界定 `resource_density_spearman_rho`：资源向量恒定时相关系数没有定义。因此 Cycle 4 必须在非平坦资源场上同时回答：

1. 固定物理时长后，确认性统计量在三级步长下是否达到可接受的弱收敛；
2. 只改变粒子存储顺序时，聚合统计量的差异是否随步长缩小，并被同级离散误差覆盖；
3. 财富守恒、非负性、稳态和精度 Gate 是否同时成立；
4. 完整数值校准需要多少 CPU 时间，是否值得进入新的确认性实验。

## 2. 两个验证层及隔离原则

### 2.1 非平坦步长层

使用三类资源场：

- `smooth`：确定性的低频正值场，均值严格为 1；
- `clustered`：高斯混合簇状场；
- `shuffled`：与 clustered 逐格值直方图完全相同、空间排列打乱的场。

每类资源场使用 `dt = 0.02 / 0.01 / 0.005`，保持物理总时长、输出时间间隔、人口、区域、资源总量和全部连续时间率参数不变。温度保持 0.5，并使用至少 3 个独立 seed。不同 dt 消耗的随机数数量不同，所以本层不声称布朗路径逐点耦合；判据是重复样本统计量的弱收敛。

### 2.2 存储顺序层

只在 clustered 场进行 `dt × {canonical, permuted}` 配对。两份初始条件显式写入 `gid,x,y,px,py,w,eps,age`，按 GID 排序后每一列必须逐位相同，仅 CSV 行序不同。

本层把运行温度设为 0，关闭后续 Langevin 热噪声，但保留由独立初始化流生成的同一组非零动量。原因是当前 Langevin 随机踢按数组遍历消费 RNG；在温度非零时重排会同时改变热噪声分配，无法隔离 S08 的交换遍历效应。交换噪声仍启用且由 `(base_seed, step, gid_i, gid_j)` 定址。

该层比较聚合统计量，不要求逐粒子轨迹完全相等。若结果失败，后续修复候选依次为：按稳定 pair key 排序、同一步累积增量后统一提交、随机化 pair 顺序并对顺序分布积分。任何方案都必须重新进行性能和非负性验证。

## 3. 指标和数据契约

数值分辨率指标固定为：

- `resource_density_spearman_rho`
- `density_morans_i`
- `occupancy_entropy`
- `wealth_gini`

所有非平坦单元都要求指标状态为 `valid`。稳态前提还包含 `wealth_variance` 和 `zero_wealth_fraction`。全体运行继续检查：

- 最小财富 `>= -1e-12`；
- 总财富相对漂移绝对值 `<= 1e-8`；
- 步长层每个必需指标通过 stationarity；
- 步长层每个必需指标通过 ESS precision。

逐粒子 RMSE 只可作为诊断，不进入科学结论。混沌动力学中的轨迹分离不等于聚合估计量有偏。

## 4. 弱收敛判据

对每个 landscape × metric，分别计算 coarse−fine 与 fine−finest 的 seed 级差。对 fine−finest 定义：

`B = |mean(delta)| + 2 * sd(delta) / sqrt(n)`。

通过条件为：

1. `B` 不超过配置中预先冻结的绝对数值误差上限；
2. fine−finest 的绝对均值不大于 coarse−fine 的两标准误界再加 fine−finest 的两标准误。

第二条允许有限重复数下的蒙特卡洛波动，但拒绝随 dt 缩小反而明确增大的误差。最终每个指标的数值分辨率取所有非平坦场 fine−finest 界和 finest-dt 顺序界的最大值。

这些值只表示模拟器数值分辨率。E1 的科学最小相关效应必须在看新结果前另行冻结，不能把数值误差上限直接冒充科学相关阈值。

## 5. 顺序敏感性判据

对每个 metric 和 dt，计算 canonical−permuted 的同 seed 弱差异界。通过需同时满足：

1. finest-dt 顺序界不超过该指标的预注册数值误差上限；
2. finest-dt 绝对均值没有明确大于 coarse-dt 的界；
3. finest-dt 顺序界被非平坦 fine−finest 离散误差覆盖，允许两标准误的不确定度。

任一必需指标失败，S08 保持开放，V1 失败，E1/E2 不得启动。不得删除失败指标、换 seed 或事后放宽误差上限。

## 6. 执行阶段

1. `V0C`：因 IC loader 新增显式相态/GID 输入，重新跑本地 Python 契约与 umi OpenMP OFF/ON 全套 CTest。
2. `V1P`：同人口、同网格，只缩短物理时长；各取一个步长、粗糙场和顺序层代表单元。输出每步耗时，按目标 step 数、seed 数和 1.5 安全系数外推。该 pilot 不产生数值或科学证据。
3. 人工预算边界：根据 `runtime_estimate.json` 决定是否授权完整 V1。未授权前不执行完整矩阵。
4. 完整 V1：先执行冻结矩阵，再一次性分析；失败运行全部报告，不做结果依赖的 seed 替换。
5. V1 通过后才生成 Cycle 4 最终参数锁与 E1 设计；V1 失败则修复 S08 或模型数值过程并开启新版本。

## 7. 检查方法

- 输入同一性：对 canonical/permuted CSV 按 gid 排序，检查全部显式状态列逐位相同；检查 GID 唯一、非负。
- 场匹配：clustered/shuffled 必须同 shape、同精确排序值、同总量且全为有限非负数。
- 运行绑定：preflight 绑定 commit/config/env；completion marker 绑定 config、binary SHA 和线程数。
- 环境：只在 umi、单 rank、`OMP_NUM_THREADS=1`；MPI 和 restart 不进入参考模式。
- 结果合法性：JSON 禁止 NaN/Inf；未定义与无效指标分开；任何 required 指标非 valid 即失败。
- 审计：保存 `run_specs.json`、输入 checksum、逐运行 completion、`replicate_metrics.csv`、`stationarity_report.json`、`numerical_calibration.json` 和小型 `result.json`。

## 8. 停止条件与后续修复

- 构建或契约测试失败：停在 V0C，先修实现。
- pilot 发现单 run 超时或外推超过预算：不缩减证据矩阵来迁就预算；先评估减少 I/O、等价的串行优化或申请预算。
- 步长不收敛：缩小 dt 或检查连续时间缩放、随机积分器和资源动力学离散。
- 顺序界超限：实现同步增量或稳定 pair 调度，重跑 V0 与 V1；旧 V1 保留为负结果。
- 稳态失败：增加物理时长并建立新配置版本，不从漂移窗口提取确认性效应。
- 精度失败：增加独立 seed 或稳态窗口长度，并在新版本中记录计算预算。
