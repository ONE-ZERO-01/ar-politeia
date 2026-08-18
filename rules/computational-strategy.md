# Computational Strategy

Agent 可以自主选择原方法、算法优化、C++/MPI/GPU、替代算法、快速筛选或混合策略。
框架不规定技术路线，只约束证据表述。

## 核心规则

1. 方法或实现发生实质变化时，明确记录采用的策略及证据边界。
2. 快速、近似或筛选结果不得被描述成高保真结果。
3. 筛选方法若要直接支撑核心 claim，必须提供参考方法验证或充分的方法学论证。
4. 不同方法结果冲突时必须保留冲突，不得择优报告；结论应降级为 `inconclusive`
   或返回 PLAN/EXPERIMENT。
5. 不得伪造性能提升、数值一致性或验证结果。

## 最小记录

需要说明计算策略时，可在实验目录保存 `computational_strategy.json`：

```json
{
  "approach": "使用两粒子 Benettin 快速扫描，再用变分方法验证关键点",
  "evidence_role": "screening",
  "supports_core_claim": false,
  "evidence_boundary": "仅用于选择候选参数点，不直接证明 Lyapunov 指数"
}
```

若筛选或近似结果直接支撑核心 claim，再增加：

```json
{
  "reference_validation_required": true,
  "reference_method": "variational Lyapunov equations",
  "validation_points": ["critical point", "largest signal"],
  "agreement": {"metrics": ["lambda"], "rtol": 0.1},
  "validation_artifact": "method_validation.json"
}
```

`validation_artifact` 应列入 `outputs.txt`。其他 profiling、优化尝试、编译和硬件信息均可由
Agent 按研究需要记录，不作为统一强制字段。
