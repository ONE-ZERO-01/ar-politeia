# GPU Allocation Gate

- H100 主机自 2026-06-01 起处于禁用状态，配置恢复前必须硬阻断。
- A100 主机为 `umi-wanwb`（登录后主机名 `umi`，`ssh umi-wanwb` 直达），允许设备为 `0,1,2,3`。
- 提交 GPU 作业前必须实时查询设备占用并显式记录 `CUDA_VISIBLE_DEVICES`。
- 未实现或未通过实时查询时，系统必须阻断，而不是假设 GPU 空闲。
- 预计 GPU 小时超过 run 预算时进入 `NEEDS_HUMAN`。

服务器拓扑、项目根目录与输出纪律见 [server-config.md](server-config.md)。

