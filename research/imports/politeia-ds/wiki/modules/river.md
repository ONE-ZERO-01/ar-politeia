# river — 河流走廊场

> 代码路径：`src/river/`
> 理论：[[research-proposal#5.7.2 已实现：RiverField 河流走廊场]]

## 职责

独立于 DEM 的 `RiverField`：proximity 栅格驱动资源产出、承载力、交换、技术传播及可选河道力/瘟疫增强。

## 关键文件

- `river_field.hpp/cpp` — procedural / ASCII / binary 加载；`proximity()`、`force()`、`discharge` 预留

## 配置

`river_*` 系列项（见 `config.hpp`）；示例 `examples/riverfield_global_snippet.cfg`；数据工具 `scripts/fetch_rivers.py`。

## 依赖关系

- 被 `main.cpp` 主循环调用，与 `force/`、`population/`、`interaction/` 耦合
