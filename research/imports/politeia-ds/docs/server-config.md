# 服务器配置与远程开发

> 相关：[[docs/build-network-umi-zeus]]（UMI 无外网时的 CMake / 依赖拉取）；GPU 提交硬性规则见 [gpu-allocation.md](../rules/gpu-allocation.md)。  
> 姊妹项目参考：LR-Bifurcation-Dynamics 的 `SERVER-DEV-GUIDE.md`（同一套 zeus / umi-wanwb 基础设施）。

## 拓扑

```
本地机器 ──ssh──▶ zeus（跳板/网关，可连外网）
                    │
                    └──ssh──▶ umi-wanwb（GPU 节点，4×A100）
```

| 主机 | SSH 别名 | 用途 |
|------|----------|------|
| zeus | `ssh zeus` | 网关，**可访问外网**；下载数据、git clone、pip/conda 安装、首次 CMake FetchContent |
| umi-wanwb | `ssh umi-wanwb` | GPU 计算节点，4 张 NVIDIA A100-PCIE-40GB；运行编译、仿真与 GPU 实验 |

zeus 与 umi-wanwb **共享同一文件系统**（NFS 挂载）。在任一台机器上修改 `/home/wanwb/ONE/Politeia-ds` 下的文件，另一台立即可见，**无需 scp/rsync 同步代码**。

## SSH 配置

在本地 `~/.ssh/config` 中添加（主机名/IP 按实际环境填写）：

```ssh-config
Host zeus
  HostName 166.111.236.27
  Port 3330
  User wanwb
  IdentityFile ~/.ssh/id_rsa

Host umi-wanwb
  HostName <umi-ip>
  User wanwb
  ProxyJump zeus
  IdentityFile ~/.ssh/id_rsa
```

使用方式：

```bash
# 登录跳板（下载数据、装包）
ssh zeus

# 登录 GPU 节点（跑实验）
ssh umi-wanwb
```

从 zeus 上也可直接 `ssh umi-wanwb`（同一内网，通常已配置免密）。

## 项目路径

| 环境 | 路径 |
|------|------|
| 本地 MacBook | `/Users/ruo/Library/CloudStorage/OneDrive-个人(2)/oneresearch/Politeia-ds` |
| zeus / umi-wanwb（共享） | `/home/wanwb/ONE/Politeia-ds` |

Agent 读取路径的单一真相源：`servers.toml`。

## 分工原则

| 操作 | 在哪台机器执行 |
|------|----------------|
| 下载地形/数据集、git clone、`pip install`、`conda install` | **zeus** |
| 首次 CMake + FetchContent（拉 googletest 等） | **zeus**（见 [[docs/build-network-umi-zeus]]） |
| `cmake --build`、C++ 仿真、GPU 计算、`nvidia-smi` | **umi-wanwb** |
| 编辑代码（共享盘） | 任一台均可；长任务建议在 umi-wanwb 上 `nohup`/`tmux` |

## 包管理（spack）

使用 **spack** 管理编译安装的软件包和库。

```bash
spack load <package>    # 加载环境
spack find              # 查看已安装包
spack list              # 查看可用包
```

涉及 CUDA、MPI、nccl 等 GPU/HPC 依赖时，优先通过 spack 加载，确保与 A100 驱动兼容。服务端常用入口：

```bash
ssh umi-wanwb
cd /home/wanwb/ONE/Politeia-ds
source scripts/ops/env.sh
```

## GPU 使用

GPU 主机为 `umi-wanwb`，设备编号 `0,1,2,3`。

**提交 GPU 作业前必须：**

1. 实时查询占用：

```bash
ssh umi-wanwb "nvidia-smi --query-gpu=index,name,memory.used,memory.total,utilization.gpu --format=csv,noheader"
```

2. 根据空闲设备显式设置 `CUDA_VISIBLE_DEVICES`：

```bash
CUDA_VISIBLE_DEVICES=0,1 ./build/politeia ...
```

3. 在实验声明中记录使用的 GPU 编号。

未通过实时查询或未显式设置 `CUDA_VISIBLE_DEVICES` 的实验将被阻断提交。详见 [gpu-allocation.md](../rules/gpu-allocation.md)。

## 常用命令

### 代码同步（本地 → 服务器，可选）

共享盘上通常不需要；本地有未推送改动时可用 rsync：

```bash
rsync -avz --exclude='builds/' --exclude='build/' --exclude='.git/' \
  "/Users/ruo/Library/CloudStorage/OneDrive-个人(2)/oneresearch/Politeia-ds/" \
  umi-wanwb:/home/wanwb/ONE/Politeia-ds/
```

### 在 zeus 上下载数据

```bash
ssh zeus
cd /home/wanwb/ONE/Politeia-ds
# 例：python scripts/fetch_terrain.py ...
```

### 在 umi-wanwb 上构建与运行

```bash
ssh umi-wanwb
cd /home/wanwb/ONE/Politeia-ds
source scripts/ops/env.sh
bash scripts/ops/run_full_v17.sh
tail -f logs/build/build2.log
```

### 后台长任务

```bash
ssh umi-wanwb "cd /home/wanwb/ONE/Politeia-ds && source scripts/ops/env.sh && \
  nohup bash scripts/ops/run_full_v17.sh > logs/build/run.log 2>&1 &"
```

### 查看 GPU

```bash
ssh umi-wanwb "nvidia-smi"
```

## Agent 执行实验的标准流程

1. **读配置**：`servers.toml` → 项目路径与主机别名。
2. **外网操作**（如需）：`ssh zeus`，下载数据或安装依赖。
3. **GPU 实验**：`ssh umi-wanwb`，`cd /home/wanwb/ONE/Politeia-ds`。
4. **加载环境**：`source scripts/ops/env.sh` 或 `spack load ...`。
5. **查询 GPU**：`nvidia-smi`，确定 `CUDA_VISIBLE_DEVICES`。
6. **执行实验**：产物写入 `.autoresearcher/runs/<run_id>/jobs/<experiment_id>/workspace/`。
7. **验证产物**：`python -m autoresearcher.foundation.jobctl reconcile ...`。

## 旧服务器（H100，已停用）

| 项目 | 内容 |
|------|------|
| SSH 别名 | `h100` |
| 状态 | 2026-06 起停用；历史环境独立于 zeus/umi 共享盘 |

新实验一律使用 zeus + umi-wanwb，勿再配置 ZTS / h100 跳板。

## 注意事项

- 数据下载、pip/conda 安装等需要外网的操作一律在 **zeus** 上执行。
- GPU 计算一律在 **umi-wanwb** 上执行。
- 共享文件系统意味着代码修改即时同步；仅本地独有改动才需 rsync。
- 长任务使用 `nohup`、`screen` 或 `tmux`，避免 SSH 断开导致中断。
