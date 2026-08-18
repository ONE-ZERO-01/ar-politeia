# 计划、分析与重规划

## PLAN

PLAN Agent读取研究问题、项目材料、上一版计划、findings 和 reviews，生成 `plan.json`。

计划至少包含：

- `claims[]`：主张、反证条件和关联实验。
- `experiments[]`：实验或已有证据导入任务。
- `budget`：本轮预算假设。
- revision：修改原因、退休或新增的 claim。

Agent 可以重新定义整个计划。PLAN Gate 只检查结构、ID 唯一性和引用关系，不判断研究
想法是否应该改变。

PLAN 后由 EXPERIMENT Agent进一步设计实验，可重排、删除、替换或新增实验。

## ANALYZE

ANALYZE Agent读取通过 Gate 的 manifest，生成 `findings.json`：

- `supported`
- `contradicted`
- `inconclusive`

每个 finding 必须关联计划中的 claim 和真实 evidence。Gate 验证引用、checksum、JSON
有限数值和 artifact 完整性，但不替 Agent进行科学解释。

## STRATEGY

出现 `contradicted` 或 `inconclusive` 时，STRATEGY Agent获得当前计划、findings、历史证据
和剩余预算，自主选择：

- 回到 PLAN 设计最小区分实验。
- 替换、收缩或删除 claim。
- 接受负结果并修改论文叙事。
- 在当前证据足够时继续。
- 请求额外预算、权限或人工判断。

若问题是计算成本而不是科学反证，STRATEGY 可自主选择算法优化、C++/OpenMP/MPI/GPU、
替代算法、快速筛选或混合方案。框架不规定尝试顺序；方法角色和证据边界必须明确，筛选或
近似结果直接支撑核心 claim 时必须提供验证。详见
[计算策略](../rules/computational-strategy.md)。

实验反驳原假设属于科学证据，不是系统故障。`inconclusive` 也不等于失败。

重规划必须保留旧计划、jobs、findings 和论文版本。历史反证不得被覆盖或丢弃。
