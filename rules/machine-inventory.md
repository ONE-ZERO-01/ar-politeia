# 机器速查（Machine Inventory）

面向 Agent 的服务器/账号/算力速查。内容于 2026-08-20（Asia/Shanghai）通过 SSH 实测确认。
完整纪律见 [server-config.md](server-config.md)（权威）、[gpu-allocation.md](gpu-allocation.md)、
[gpu-compute.md](gpu-compute.md)。

## 拓扑

```
本地 macOS（git 权威）
   │ ssh zeus（或 ssh thu_wwb，同一台）
   ▼
zeus —— 控制面（有外网：LLM Provider / 下载 / pip 安装）
   │ ProxyJump
   ▼
umi —— GPU 节点，4 × NVIDIA A100
```

## 主机表

| 主机 | SSH 命令 | 登录后 hostname | 账号 | 用途 |
|------|----------|-----------------|------|------|
| zeus（控制面） | `ssh zeus` 或 `ssh thu_wwb` | `zeus` | `wanwb` | 有外网；orchestrator / LLM Provider / 下载 / pip |
| umi（GPU） | `ssh umi-wanwb`（经 `thu_wwb` 跳板） | `umi` | `wanwb` | 4 × A100，运行数值实验 |

- `zeus` 与 `thu_wwb` 两个别名指向同一台 `166.111.236.27:3330`，登录账号均为 `wanwb`。
- 从本地 mac 到 umi：`ssh umi-wanwb`（已配置 `ProxyJump thu_wwb`）。
- 从 zeus 到 umi：`ssh umi`（`umi` 在 zeus 上可解析；`umi-wanwb` 是本地 mac 别名，zeus 上不存在）。

## 共享文件系统（实测）

- zeus 视角：`192.168.0.21:/home`（nfs4）
- umi 视角：`10.0.0.21:/home`（nfs4）

两者是同一 `/home` NFS 导出（总容量一致，约 54T，69% 已用，剩余约 16T）。IP 不同只是两台机器
经不同网段访问同一 NFS 服务器，文件即时同步，无需 `scp`/`rsync`。

## 项目根目录

`/home/wanwb/ONE/ar-politeia`（即 `AR_PROJECT_ROOT`），zeus 与 umi 上路径一致且已存在。

## GPU（实测 `nvidia-smi`）

- 4 × NVIDIA A100-PCIE-40GB，每卡 40960 MiB，设备号 `0,1,2,3`。

## 外网（实测）

- zeus：`curl https://pypi.org` → HTTP/2 200，外网可用。

## 同步状态（实测 2026-08-20）

- umi 上 `git -C /home/wanwb/ONE/ar-politeia rev-parse --short HEAD` = `e314804`，与本地 `main` 一致。

## 硬约束速记

- orchestrator 在 `zeus`（控制面）上运行，运行态不进 git、不跨设备同步。
- 数值实验只在 `umi` 上运行，本地 mac 不跑任何数值实验脚本。
- 所有产物必须落在 `AR_PROJECT_ROOT` 内，禁止写入 `$HOME` 根目录或项目外临时盘。
