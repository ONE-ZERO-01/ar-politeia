# 自主性与项目配置

## 自主性边界

Agent 可以自主：

- 新增、删除、替换、收缩或重写 research claim。
- 修改研究计划、实验优先级、方法、参数、baseline 和 ablation。
- 根据 profiling 和预算选择等价性能优化，或采用“快速筛选 + 高保真复核”策略。
- 将负结果或反例作为研究结论，而不是维护原假设。
- 根据新证据重规划、改稿、继续研究或请求人工输入。
- 根据模拟审稿意见补实验、改稿或调整论文定位。

Agent 的策略动作包括：

- `replan`：返回 PLAN，生成新计划。
- `revise`：保留证据，修改论文主张或叙事。
- `continue`：沿当前流程继续。
- `request_human`：请求必要的人工输入或权限。
- `stop_request`：建议停止，等待人类确认。

必须由人类决定：

- 增加超出当前配置的 token、GPU-hour 或周期预算。
- 获取新的账号、数据、主机、许可证或其他外部权限。
- 改变项目明确设定的人工边界。
- 最终投稿、正式终止或对外发布。

初始计划是否需要批准由 `autonomy.require_initial_plan_approval` 控制。正常重规划不应
默认变成人工审批点。

## 项目记录

当前框架由 `autoresearcher.md` 驱动；图模式额外使用 `autoresearcher.orchestration`。
每次只探索一个研究方案，产物平铺在 `research/`：

- `research/project.json`：项目标识、预算和总体状态。
- `research/question.md`：当前研究问题。
- `research/plan.json`：claim、实验、资源和计算策略。
- `research/state.md`：当前 Stage、cycle 和决策摘要。
- `rules/`：复现性、计算策略、GPU 和服务器边界。

迁移到新领域时清空或替换 `research/` 内容，并保留同样的扁平产物协议；领域知识和服务器
路径写入项目研究文档或规则文件，不硬编码进三个 foundation 工具。
