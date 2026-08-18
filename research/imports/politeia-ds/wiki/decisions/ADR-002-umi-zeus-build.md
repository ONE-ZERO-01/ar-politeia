# ADR-002: UMI 无外网时的 Zeus 构建流程

> 日期：2026-04-19  
> 状态：已接受  
> 来源：[[wiki/log#2026-04-19] decision | UMI/Zeus 构建流程]  
> 操作文档：[[docs/build-network-umi-zeus]]

## 背景

在 UMI 集群上开发时节点无外网，CMake `FetchContent` 无法从 GitHub 拉取 googletest 等依赖，导致首次配置失败。

## 选项

| 选项 | 说明 |
|------|------|
| A. 预打包 vendor 依赖进仓库 | 体积大、升级麻烦 |
| B. 在 Zeus（可联网共享盘）完成首次 cmake，UMI 复用 build 目录 | 一次配置、多机复用 |
| C. 禁用测试 | 损失 CI 价值 |

## 决定

采用 **B**：在 Zeus 上完成首次 `cmake` 与依赖下载；UMI 挂载同一 build 目录或同步已填充的 `_deps`。

## 理由

- 不污染主仓库体积
- 保留 GoogleTest / CTest 工作流
- 与现有 HPC 双集群使用方式一致

## 后果

- 操作步骤沉淀在 `docs/build-network-umi-zeus.md`
- 新成员 onboarding 须读该文档
- 依赖版本变更时需在 Zeus 侧重跑配置
