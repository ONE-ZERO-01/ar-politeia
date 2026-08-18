# GPU 计算资源（A100）使用指南

本文件回答一个面向 Agent 的决策问题：**数值实验计算量大时，是否以及如何把计算搬到 A100 GPU**。
纪律性硬约束见 [gpu-allocation.md](gpu-allocation.md)，服务器拓扑/路径/环境见
[server-config.md](server-config.md)。本文件聚焦「资源规格 → 何时用 → 当前技术栈现状 → 如何迁移 → 声明纪律」。

## 1. 资源规格（实测，2026-08-18）

| 项 | 值 |
|----|----|
| 主机 | `umi-wanwb`（登录后主机名 `umi`，`ssh umi-wanwb` 一条命令直达） |
| GPU | 4 × NVIDIA A100-PCIE-40GB，设备号 `0,1,2,3` |
| 驱动 | 580.105.08 |
| 显存/卡 | 40960 MiB |
| 磁盘 | `/home` 共 51T，剩约 5T（90% 已用，重产物及时清理） |

查询命令：

```bash
ssh umi-wanwb "nvidia-smi --query-gpu=index,name,memory.used,memory.total,utilization.gpu --format=csv,noheader"
```

## 2. 何时用 GPU（决策标准）

本项目当前 P1 阶段（d≤4 小矩阵，numpy/scipy 单机 CPU 已足够）**不需要 GPU**。遇到以下任一
「计算量增大」信号时，应考虑迁移到 A100：

- 矩阵维数增大（d≥16 的 TPS 优化、更高维 Schmidt/Haar 采样）；
- 样本量 / 参数扫描量增大（多起点重启、g 扫描、bootstrap 大规模）；
- 热点是矩阵指数化 `expm`、特征分解 `eigh`、大矩阵乘（`scipy.linalg` 反复调用）；
- 单次实验 CPU 串行时间显著超过 plan.json 声明的 `timeout_seconds`。

判断不是「越大越好」：迁移有固定成本（装库、重写、调试），只有热点足够大才划算。先用
`cProfile`/`time` 定位瓶颈，确认热点是「可向量化/可并行的线性代数」再搬 GPU。

## 3. 当前技术栈现状（如实，2026-08-18）

**A100 硬件可用，但 GPU 软件栈尚未安装**：

- 系统 Python 3.11.2 + pip 23；已内置 numpy 2.4.4、scipy 1.17.1。
- **未安装**：`torch`、`cupy`、`numba`、`jax`（`import` 均报 ModuleNotFoundError）。
- **无 `nvcc`**（CUDA toolkit 不在 PATH）；**无 conda/spack**；**无项目 venv**。
- 因此：**首次使用 GPU 前，必须先在网关 `zeus` 上安装 GPU 库**（见下）。

## 4. 迁移步骤（首次使用前）

1. **在 zeus（有外网）装库**（zeus/umi 共享同一 NFS，装一次即可）：

```bash
ssh thu_wwb
cd /home/wanwb/ONE/ar-politeia
python3 -m venv .venv && source .venv/bin/activate
python3 -m pip install torch --index-url https://download.pytorch.org/whl/cu126   # 或匹配驱动的 CUDA 版本
# 或按需：pip install cupy-cuda12x / numba / "jax[cuda12]"
```

2. **在 umi 验证 GPU 可见**：

```bash
ssh umi-wanwb
source /home/wanwb/ONE/ar-politeia/.venv/bin/activate
python3 -c "import torch; print(torch.cuda.is_available(), torch.cuda.device_count())"
```

3. **迁移实验代码**：把热点从 `scipy`/`numpy` 改写为对应 GPU 库（torch/cupy），
   保持 `result.json` 输出结构与 CPU 版本一致；**CPU 版本保留**作为对照/回退。
4. **声明 GPU 使用**（见第 5 节）。

> 注意：装库前先确认磁盘余量（当前 90% 已用）。torch 全家桶约数 GB，必要时先清理
> `workspace/` 内旧产物。

## 5. 声明与纪律（不可跳过）

GPU 实验必须同时满足：

1. **plan.json** 中该实验 `gpu_count` 字段设为实际使用数（如 `2`），并在
   `computational_strategy` 说明证据角色（GPU 加速是纯工程手段，不改变证据边界）。
2. **提交前实时查询** `nvidia-smi`，按空闲设备显式设置 `CUDA_VISIBLE_DEVICES`
   （例：`CUDA_VISIBLE_DEVICES=0,1 python ...`），并在 `research/jobs/<exp_id>/` 声明记录
   使用的 GPU 编号。
3. 未实时查询或未显式设置 `CUDA_VISIBLE_DEVICES` 的实验将被 **阻断提交**（见
   [gpu-allocation.md](gpu-allocation.md)）。
4. 预计 GPU 小时超过 run 预算时进入 `NEEDS_HUMAN`，交人工决策。

## 6. 与框架的关系

- GPU 只是「计算策略选择」的一种（见 [computational-strategy.md](computational-strategy.md)）：
  Agent 可自主决定用 CPU 还是 GPU，只需诚实声明证据角色与边界；近似/加速结果直接支撑核心
  claim 时必须提供参考验证。
- 数值实验一律只在 `umi` 上运行（铁律，见 [server-config.md](server-config.md)），
  本地 mac 只写代码/计划/看结果。
- 权威产物（`result.json`、图表）由服务器生成后回传 git，GPU 实验同理。
