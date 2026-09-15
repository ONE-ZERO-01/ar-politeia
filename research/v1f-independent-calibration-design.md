# V1F 保守样本量独立校准设计

日期：2026-09-15。状态：**设计冻结**。V1F 只解决 V1E 的独立 seed 精度失败，不改变 V1E
负结论，也不使用 E1 效应方向或大小。

## 样本量依据

V1ED 精确复现 V1E Gate。20 seeds 下限制单元的点估计需要 38；对 df=19 的样本 SD 使用单侧
90% 上界后，最大需求为 61。按诊断前固定的“向上取 2 的幂”政策，V1F 使用 64 个全新 seeds。
matched clustered/shuffled 四项有界指标的配对精度保守需求最大为 17，说明 64 seeds 也充分覆盖
未来配对估计的方差需求，但这一计算不构成景观效应证据。

## 冻结矩阵与 Gate

- seeds 为 11003–11633 区间内预先列出的 64 个未用素数；禁止替换；
- timestep：3 landscapes × 3 dt × 64 = 576 runs；
- storage order：clustered × 2 orders × 3 dt × 64 = 384 runs；总计 960 runs；
- `N=1000`、`64×64`、`total_time=4500`、输出间隔 5、两个相邻 144 帧窗口；
- 模型参数、V0E CPU reference、数值误差上限、尾窗稳态、相邻窗口稳定性与独立 seed 精度
  阈值全部原样继承 V1E；时间 ESS 仍只报告；
- 8 个 OMP=1 进程并行，单 run 超时 10,800 秒，整体 timeout 259,200 秒；
- 按 V1E 实测缩放预计 331.23 CPU 小时、41.40 墙钟小时、约 160 GB ignored workspace；
  umi 当前 `/home` 可用约 13 TB。

V1F 必须整体独立执行并通过所有 Gate 才能解除 C1 数值校准阻塞。任何失败都作为有效负结果归档，
不得与 V1E seeds 合并后宣称通过。
