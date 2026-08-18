# climate — 气候栅格（预留/扩展）

> 代码路径：`src/climate/`
> 理论：[[research-proposal]] 环境分层相关章节

## 职责

`ClimateGrid`：与地形/河流并列的环境场接口，供未来气候—文明耦合实验使用。

## 关键文件

- `climate_grid.hpp/cpp`

## 依赖关系

- 与 `force/terrain_*`、`river/river_field` 同属环境分层；主循环集成程度见 `main.cpp` 当前版本
