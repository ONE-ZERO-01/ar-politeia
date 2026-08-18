# 服务器配置（本方案）

本项目数值模拟在 A100 服务器上运行。本文件是服务器、路径、环境与输出纪律的唯一权威描述；
其他平台 Agent 从根目录 [AGENTS.md](../AGENTS.md) 进入本文件。

## 拓扑

```
本地 macOS（git 权威） ──ssh──▶ thu_wwb / zeus（网关，有外网）
                                    │  ProxyJump
                                    ▼
                               umi-wanwb / umi（GPU 节点，A100 × 4）
```

- `thu_wwb`（登录后主机名 `zeus`）：网关节点，可访问外网，用于下载数据、`pip` 安装。
- `umi-wanwb`（登录后主机名 `umi`）：GPU 节点，4 张 A100，用于运行实验。
- 两台机器共享同一 NFS 文件系统（`192.168.0.21:/home`），在任一台看到的文件完全一致，
  无需 `scp`/`rsync`。

## SSH 访问

| 主机 | 命令 | 用途 |
|------|------|------|
| zeus（网关） | `ssh thu_wwb` | 有外网，下载数据、pip 安装 |
| umi（GPU） | `ssh umi-wanwb` | 4 × A100，运行实验 |

`ssh umi-wanwb` 已在本地 `~/.ssh/config` 配置 `ProxyJump thu_wwb`，一条命令直达 GPU 节点，
无需手动两跳。

## 文件系统与项目根目录

- 本项目根目录（`AR_PROJECT_ROOT`）：`/home/wanwb/ONE/ar-politeia`
- 本地 macOS 仓库是代码与研究的 git 权威；服务器目录是它的工作副本（同一套 `research/`、
  `src/`、`orchestration/`、`rules/`）。
- 代码改动：本地 commit → `git push umi`；服务器共享文件系统上 zeus/umi 即时同步。

### 输出路径纪律（强制）

**所有实验产物必须落在项目根目录之内**。本项目目录约定与 foundation 工具一致：

| 内容 | 路径 | git |
|------|------|-----|
| 实验源代码 | `research/src/experiments/<exp_id>.py` | 追踪 |
| 实验声明与配置 | `research/jobs/<exp_id>/`（config、env.txt、seeds.txt、outputs.txt、commit.txt、computational_strategy.json） | 追踪 |
| 重产物 / 中间文件 | `research/jobs/<exp_id>/workspace/` | 忽略 |
| jobctl 运行时记录 | `.autoresearcher/jobs/<exp_id>/`（handle/spec/logs/result） | 忽略 |
| 结果摘要 | `research/jobs/<exp_id>/result.json` | 追踪 |

分析完成后把摘要（`result.json`、csv、小图）放回 `research/jobs/<exp_id>/`；
大体积中间产物保留在 `workspace/` 并记录相对路径。

禁止写入：`/home/wanwb/` 根目录、`$HOME` 下的 ad-hoc 目录、`/mnt/nvme` 等临时盘、
项目根目录外的任何位置。

## Python 环境

- 系统 Python 3.11.2 + pip 23；已内置 numpy 2.4.4、scipy 1.17.1。
- 无 conda、无 spack。按项目需要自建虚拟环境（推荐每个实验方向一个 venv）：

```bash
ssh umi-wanwb
cd /home/wanwb/ONE/ar-politeia
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt   # 若存在
```

- 缺 torch、quimb 等包时，在 **zeus（`ssh thu_wwb`）** 上 `pip install`（有外网）；
  装到 venv 后 zeus/umi 共享同一文件系统，直接可用。

## GPU 使用

GPU 主机为 `umi-wanwb`，可用设备 `0,1,2,3`（4 × NVIDIA A100-PCIE-40GB）。

**提交 GPU 作业前必须：**

1. 实时查询占用：

```bash
ssh umi-wanwb "nvidia-smi --query-gpu=index,name,memory.used,memory.total,utilization.gpu --format=csv,noheader"
```

2. 按空闲设备显式设置 `CUDA_VISIBLE_DEVICES`：

```bash
CUDA_VISIBLE_DEVICES=0,1 python train.py
```

3. 在实验声明中记录使用的 GPU 编号。

未实时查询或未显式设置 `CUDA_VISIBLE_DEVICES` 的实验将被阻断提交。详见
[gpu-allocation.md](gpu-allocation.md)。

## Agent 执行实验的标准流程

1. **连接**：`ssh umi-wanwb`（已含 ProxyJump，直接到 GPU 节点）。
2. **定位项目**：`cd /home/wanwb/ONE/ar-politeia`。
3. **准备环境**：激活 venv，或确认系统 numpy/scipy 可用。
4. **查询 GPU**（如需）：`nvidia-smi` 实时查询，确定 `CUDA_VISIBLE_DEVICES`。
5. **存放实验**：代码放 `research/src/experiments/`，声明与配置放 `research/jobs/<exp_id>/`，
   重产物写进该目录下 `workspace/`。
6. **提交并执行**：`jobctl submit`（记录到 `.autoresearcher/jobs/<exp_id>/`）后在 workspace 内运行。
7. **验证与回传**：`jobctl reconcile` 确认完整；摘要复制到 `research/jobs/<exp_id>/result.json`，
   大文件留 workspace 并记录相对路径。

## 注意事项

- 下载、pip 安装等需外网的操作在 **zeus（`ssh thu_wwb`）** 上执行。
- GPU 计算在 **umi（`ssh umi-wanwb`）** 上执行。
- 共享文件系统下，代码修改在 zeus/umi 即时同步。
- 长任务用 `nohup` / `tmux` 避免 SSH 断开中断。
- 磁盘：`/home` 共 51T（剩约 5T，90% 已用），大产物及时清理，勿长期堆积 plotfile。

## orchestrator 运行位置（强制）

多 Agent DAG（`python -m autoresearcher.orchestration run orchestration/research-graph.json`）
**只在服务器 `umi` 上运行**，不在本地 mac 或其他电脑上运行。原因：

1. 运行态（`.autoresearcher/orchestrator/` 下的 `state.json`、`logs/`、锁文件）记录的是
   本机的绝对路径、进程锁和单次 DAG 进度，跨设备同步毫无意义，两台机器同时跑还会互相覆盖；
2. 本地 mac 项目位于 OneDrive 同步目录，orchestrator 每次状态转换都对 `state.json` 做全量
   原子重写（temp + rename），正是 OneDrive 同步冲突的典型触发源；而 macOS OneDrive 无法
   排除项目内子目录，只能靠"运行态不在本地产生"来规避；
3. 算力本身就在服务器上，实验产物统一落在 `$AR_PROJECT_ROOT` 内，与输出路径纪律一致。

本地 mac 只负责写代码、写计划、看结果，跨设备同步研究产物一律通过 git（双远程），
不通过 OneDrive 同步运行态。

## 数值实验运行位置（铁律）

所有数值实验脚本（`research/src/experiments/*.py`，经 `jobctl` 提交运行的）**一律只在
服务器 `umi` 上运行**。包括开发、调试、校准、冒烟测试——本地 mac 不运行任何数值实验。

原因：

1. **统一环境**：数值结果必须与论文声称的算力环境一致（A100、服务器 numpy/scipy 版本），
   本地 mac 的 CPU 架构、BLAS、随机数实现与服务器可能不同，同一脚本可能给出可复现性偏差；
2. **输出纪律**：实验权威产物（`result.json`、图表、`env.txt`、`seeds.txt`）必须由服务器
   生成后回传 git，本地跑出的结果没有"算力声明"这一上下文，后续 audit 无法对齐；
3. **避免本地/服务器双份结果打架**：本地 OneDrive 同步目录里生成结果，再与服务器结果
   混淆，会破坏单一权威来源。

本地 mac 只写实验代码与计划，不执行 `python research/src/experiments/*.py`。代码写好后
`git push umi`，在服务器 `umi` 上运行并生成权威产物。
