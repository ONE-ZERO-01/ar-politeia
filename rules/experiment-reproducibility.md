# Experiment Reproducibility Gate

任何 `command` 类型实验提交前必须具备：

1. 非空 `commit_id`，且不得为 `dirty`。
2. 版本化 JSON 配置文件及其 SHA-256。
3. 明确随机种子；P0 默认至少 3 个，除非计划中记录豁免理由。
4. 环境快照路径及 SHA-256。
5. 输入数据版本或 checksum。
6. 声明输出 artifact 路径和机器可判定验收标准。
7. 若使用高性能等价实现或快速筛选方法，必须满足
   [计算策略 Gate](computational-strategy.md)，并把数值一致性报告列入输出 artifact。

`import` 类型实验用于接入既有不可变证据，必须记录源仓库 commit、源路径、
大小和 SHA-256。导入不等于重新计算，也不得改写源文件。

## 输出路径约束

1. 所有 artifact（含 GRTeclyn 的 `plt*`、`chk*`、`run.log`）的路径必须解析后落在
   `$AR_PROJECT_ROOT` 之内。
2. 标准 workspace：
   `.autoresearcher/runs/<run_id>/jobs/<experiment_id>/workspace/`。
3. Preflight 和 jobctl 会拒绝逃逸项目根的相对路径；手动 SSH 提交 GPU 任务同样适用此规则。
4. 启动 AMReX/GRTeclyn 前必须 `cd` 到 workspace；禁止在 `$HOME` 或项目外目录执行
   `mpirun ... main3d.ex params.txt`。
