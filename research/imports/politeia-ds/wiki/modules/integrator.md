# integrator — 时间积分

> 代码路径：`src/integrator/`
> 物理框架：[[research-proposal#三、物理框架：Langevin-跳跃扩散社会动力学]]
> Langevin 噪声分布：[[docs/stochastic-distributions#1. 运动方程 — Langevin 噪声]]

## 职责

求解 Langevin 方程，更新粒子的位置和动量。

## 关键文件

### `langevin_integrator.hpp/cpp` — BBK Langevin 积分器

BBK (Brünger-Brooks-Karplus) 积分格式，Velocity-Verlet 的随机力推广：

```
Step 1: p_{n+1/2} = p_n + (dt/2)×F_n − (dt/2)×γ×p_n + σ√(dt/2)×R_n
Step 2: x_{n+1} = x_n + (dt/m)×p_{n+1/2}
Step 3: 边界条件（反射）
Step 4: F_{n+1} = Force(x_{n+1})
Step 5: p_{n+1} = p_{n+1/2} + (dt/2)×F_{n+1} − (dt/2)×γ×p_{n+1/2} + σ√(dt/2)×R_{n+1}
Step 6: KE = Σ p²/(2m)
```

| 参数 | 物理含义 | 社会类比 |
|---|---|---|
| `γ` (friction) | 摩擦系数 | 制度腐化速率、知识遗忘率 |
| `T` (temperature) | 温度 | 社会动荡程度——高温=乱世，低温=治世 |
| `σ = √(2γmkT)` | 噪声幅度 | 随机事件的强度（涨落-耗散关系） |
| `mass` | 粒子质量 | 个体惯性——改变状态的阻力 |

关键性质：γ=0,T=0 时退化为确定性 Velocity-Verlet；γ>0,T>0 时趋向热平衡 ⟨KE⟩=N·T。

## 依赖关系

- 依赖：`core/`、`force/`（Step 4 调用力计算）
- 被依赖：`main.cpp`（主循环 Step 1）
