# Politeia-ds 目录布局

> 根目录只保留源码、配置、文档；构建产物与运维脚本分目录存放。  
> 服务端路径：`/home/wanwb/ONE/Politeia-ds`（经 `ssh zeus` 访问，与 `umi-wanwb` 共享文件系统）

## 根目录（本地与服务端对齐）

| 路径 | 用途 |
|------|------|
| `src/` | C++ 模拟器源码 |
| `docs/` `wiki/` `workflow/` `rules/` | 文档与 AutoResearcher 规范 |
| `CMakeLists.txt` `pyproject.toml` `research-proposal.md` 等 | 项目元数据 |
| `autoresearcher.md` `AGENTS.md` `CODE_GUIDE.md` | 研究与协作指南 |

本地精简版不含 `examples/`、`tests/`、`scripts/`（在 HPC 完整检出中保留）。

## 服务端专用（HPC 完整检出）

| 路径 | 用途 |
|------|------|
| `builds/` | 所有 CMake 构建树（`build`, `build2`, `build-v11`…） |
| `build` `build2` | **符号链接** → `builds/build` `builds/build2`（兼容旧脚本） |
| `logs/build/` | 编译日志（`build2.log`, `cmake_*.log` 等） |
| `scripts/ops/` | 运维脚本（`do_build`, `run_full_v17`, `env.sh` 等） |
| `scripts/` | Python 分析/可视化、实验管道脚本 |
| `examples/` `tests/` `data/` `raw/` | 算例、测试、地形与原始数据 |
| `checkpoints/` `sweep_results/` | 检查点与扫描结果 |
| `archive/` | 历史状态/调试文本 dump |
| `presentations/` | PPT 与模板 |

## 常用命令

```bash
# 下载数据 / 装包（zeus，可外网）
ssh zeus
cd /home/wanwb/ONE/Politeia-ds

# 构建与仿真（umi-wanwb，4×A100）
ssh umi-wanwb
cd /home/wanwb/ONE/Politeia-ds
source scripts/ops/env.sh
bash scripts/ops/run_full_v17.sh
tail -f logs/build/build2.log
```

## 连接说明

详见 [[docs/server-config]]。

- **zeus**：跳板/网关，可连外网，用于下载数据、git、pip/conda。
- **umi-wanwb**：A100 GPU 节点（`ssh umi-wanwb`）；与 zeus **共享** `/home/wanwb/ONE/Politeia-ds`。
- **H100**（`ssh h100`）：已停用（2026-06）。
