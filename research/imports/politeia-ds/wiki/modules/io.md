# io — 输入输出

> 代码路径：`src/io/`

## 职责

粒子快照输出、能量时间序列、初始条件加载、断点续跑。

## 关键文件

### `csv_writer.hpp/cpp` — 数据输出

- `write_positions()`: 每隔 N 步输出粒子位置快照（用于可视化动画）
- `write_energy()`: 每步输出能量时间序列（动能、LJ 势能、地形势能、总能量）

### `ic_loader.hpp/cpp` — 初始条件加载

从 CSV 文件加载初始粒子：x, y 必填，w/eps/age/sex/culture 可选列。

### `checkpoint.hpp/cpp` — 断点续跑

二进制格式写入/恢复完整粒子状态，支持 `--restart` 继续运行。

## 依赖关系

- 依赖：`core/`（粒子数据、配置）
- 被依赖：`main.cpp`（初始化 + 主循环输出）
