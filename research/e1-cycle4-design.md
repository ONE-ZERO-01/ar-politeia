# E1 Cycle 4 matched-landscape 确认性设计

日期：2026-09-15。状态：**分析、样本量、seed 与科学阈值已冻结；等待 V1F 通过及最终参数锁绑定**。
本设计在 E1-C4 结果产生前写入，不读取或使用 Cycle 3 E1 的效应方向、效应大小或显著性。

## 1. 研究问题与估计量

主问题是在资源总量、资源值直方图、可达格点数、人口及初始完整相态逐 seed 匹配时，资源的
空间聚集方式是否改变稳态空间结构。每个 seed 生成同一 clustered 资源数组及其精确置乱版本，
两条件共享初始 `gid,x,y,px,py,w,eps,age`，估计量为 clustered 减 shuffled 的配对尾窗均值。

主指标 family 为：

- resource-density Spearman rho；
- density Moran's I；
- occupancy entropy。

wealth Gini 是单独的次要 family，不可单独支持核心景观主张。wealth variance 与
zero-wealth fraction 进入稳态和精度 Gate，但不进入景观效应 family。

## 2. 样本量和冻结 seeds

V1ED 只使用 V1E 校准方差，未使用 E1 效应方向或大小。最细步长下四项配对指标的单侧 90%
上界保守需求分别为 14、17、12、3；条件级六指标精度的最大保守需求为 61。为了让 E1 的
条件 ensemble Gate 与配对效应估计同时达到冻结宽度，采用下一 2 的幂 **64 seeds**，共
`64 × 2 = 128 runs`。

冻结 seeds 为：

`11657, 11677, 11681, 11689, 11699, 11701, 11717, 11719, 11731, 11743, 11777, 11779, 11783, 11789, 11801, 11807, 11813, 11821, 11827, 11831, 11833, 11839, 11863, 11867, 11887, 11897, 11903, 11909, 11923, 11927, 11933, 11939, 11941, 11953, 11959, 11969, 11971, 11981, 11987, 12007, 12011, 12037, 12041, 12043, 12049, 12071, 12073, 12097, 12101, 12107, 12109, 12113, 12119, 12143, 12149, 12157, 12161, 12163, 12197, 12203, 12211, 12227, 12239, 12241`

仓库内既有 job config/seeds 全量扫描确认交集为 0。不得替换失败 seed、追加到显著、删减到显著，
也不得把这些结果与任何旧 cycle 或校准 seed 合并。

## 3. 模型和运行契约

V1F 通过时，E1-C4 原样继承其最细已校准过程：

- `N=1000`，网格 `64×64`，边界 `[0,100]×[0,100]`；
- `dt=0.005`，`total_time=4500`，输出物理间隔 5；
- 最后两个相邻的 144 帧窗口；尾窗 144 帧定义效应估计量；
- temperature 0.5、friction 1、social strength 0、interaction range 2.5；
- exchange rate 0.5、noise strength 0.05、reversion rate 1、epsilon log sigma 0.5；
- base production 0.01、consumption 0、wealth decay 0.02；
- terrain force/production scale 均为 1，mean wealth 5，initial wealth log sigma 0.01；
- 单 rank、confirmative mode、strict numerics、OMP=1，8 个进程并行；单 run timeout 10,800 秒。

最终 config 必须绑定通过的 V1F `numerical_calibration.json` SHA-256、最终 Cycle 4 参数锁
SHA-256、reference binary SHA-256 和 runner/source commit。任一哈希不符即在执行前失败。

## 4. 数据质量与稳态 Gate

`analysis_gate_pass` 要求以下各项全部通过：

1. 128/128 runs 完成，财富始终非负、人口保持 1000、总财富变化为有限值；
2. clustered/shuffled 资源 shape、排序后数组、总量、非负有限性和可达格点数逐 seed 相同；
3. 两条件初始完整相态 SHA-256 逐 seed 完全相同；
4. clustered 和 shuffled 各自的尾窗 condition-ensemble 六指标均无剩余漂移或反转形状；
5. 两个相邻窗口的 seed 级均值差满足冻结界；
6. 条件内独立 seed 的两标准误半宽满足冻结界。

绝对半宽为 Spearman 0.05、Moran 0.05、entropy 0.025、Gini 0.025、zero fraction 0.01；
wealth variance 使用相对半宽 0.20。相邻窗口使用相同五项绝对界，wealth variance 相对界 0.10。
temporal ESS 完整报告，但只作动态相关诊断，不能否决已由独立 seed 精度支持的估计量。
逐运行稳态同样保留为诊断，不替代 condition-ensemble Gate。

## 5. 科学阈值与统计判定

科学 SESOI 在结果前冻结为 Spearman 0.05、Moran 0.05、entropy 0.025、wealth Gini 0.025。
每个指标实际使用的等效区半宽为：

`max(V1F numerical_resolution_limit, scientific_sesoi)`。

三个主指标进行配对 bootstrap 95% 区间与配对 sign-flip 检验，并在主 family 内用 Holm 控制
FWER=0.05。至少一个主指标同时满足 Holm 拒绝且整个区间位于对应等效区之外时，核心景观主张
获得支持。若数据质量 Gate 全过但没有主指标越过阈值，则归档为有效 null/等效结果；若任一
数据质量 Gate 失败，结论为未决，不将其解释为 null。Gini 单独校正并只作次要结论。

## 6. 资源估计与启动边界

V1E 最细步长 clustered/shuffled 的 40 个参考 run 平均 1,042 秒，线性估计 128 runs 约
37.06 CPU 小时、8 路理想墙钟 4.63 小时；按实测开销预留 6–8 小时。对应 40 runs 占 6.6 GB，
线性估计 E1 workspace 约 21 GB。计算资源已授权，但只有在以下顺序全部完成后才能提交：

1. V1F 960/960 完成并 reconcile；使用 `prepare_cycle4_confirmation.py archive-v1f` 交叉核对
   960 个 run spec、completion marker、health、jobctl 结果和全部 workspace artifact SHA；
2. 归档结果的所有 Gate 通过后，使用 `prepare_cycle4_confirmation.py prepare` 确定性生成不授权执行的
   candidate 参数锁、V0G 声明和 E1-C4 声明，并核对本文件的 64 seeds；
3. 提交并推送 candidate 声明，使 V0G 在干净的 umi checkout 上运行；
4. V0G 在 umi 通过 Python 全套测试和 OpenMP OFF/ON CTest，产出新的 OpenMP-OFF reference binary；
5. 使用 `prepare_cycle4_confirmation.py finalize` 校验 V0G host、clean checkout、Python/CTest
   两种构建结果并绑定 reference binary SHA-256，随后才把锁改为 final 并授权 E1-C4；
6. E1-C4 在 umi 通过 `--prepare-only` 锁/校准/输入审查和 preflight 8/8。
