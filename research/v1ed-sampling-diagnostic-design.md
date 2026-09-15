# V1ED 独立重复采样诊断

日期：2026-09-15。V1ED 只读取 V1E 已固定的汇总产物，不改变 V1E 的精度 Gate 负结论。

诊断首先用 SHA-256 绑定 `steady_estimand_report.json`、`replicate_metrics.csv` 和
`numerical_calibration.json`，并精确复现 V1E 的四层 verdict。随后对每个 condition×metric
计算维持当前均值与 SD 时的点估计样本量，以及用 df=19 卡方分布得到的单侧 90% SD 上界样本量。
新设计采用全部单元中最大的保守需求，再向上取 2 的幂，避免再次以刚好通过的点估计配置运行。

同时只使用 matched clustered/shuffled 差值的样本 SD 计算 E1 规划精度，不读取或解释效应方向和
大小。该部分仅检查未来配对设计能否受益于共同 seed；不能作为 C2 效应证据。所有输出均为诊断，
任何新 Gate 或样本量必须在新模拟数据生成前冻结并用全新 seeds 检验。
