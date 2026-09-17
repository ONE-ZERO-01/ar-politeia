# Cycle 4 promotion 的 `source_commit` / `promotion_base_commit` 记账缺陷

> 日期：2026-09-17
> 状态：**已确认缺陷，非阻塞**，本轮不修（final 锁已冻结，改动会破坏 binary/锁绑定链）
> 关联：[research/e1-cycle4-readiness.md](../e1-cycle4-readiness.md) ·
> [research/src/experiments/prepare_cycle4_confirmation.py](../src/experiments/prepare_cycle4_confirmation.py)

## 0. 一句话结论

`prepare` 把「当前 HEAD」写进 V0G 声明与 candidate 锁，但 `prepare` 自己的产物只存在于
**下一个** commit。本轮因此产生了一个指向「删除全部声明」那个 commit 的记账字段
（`9424b211…`）。该字段是 **descriptive only**，`finalize` 用 V0G 实况 `HEAD` 覆盖，
**没有影响任何 Gate、绑定或数值校准**。但它是一个真实可复现的设计缺陷，属下一轮待修。

## 1. 现象

最终锁 `research/parameter_lock.cycle4.json`（SHA-256
`bee66e70a1a9406bc4c1712df4fe3317a0856ce0392f7debbe64e69a9826127d`）中三个字段：

| 字段 | 值 | 语义 |
|---|---|---|
| `promotion_base_commit` | `9424b211053642ce8facfe2083c7b632b6a99749` | **指向「作废声明」的 commit** |
| `source_commit` | `b6d24b76a50529965469332644e7bed251c49eb1` | V0G 实况 HEAD（正确） |
| `analysis_commit` | `b6d24b76a50529965469332644e7bed251c49eb1` | 同上 |

`research/jobs/V0G-SIMULATOR-TESTS-C4/config.json` 与 `commit.txt` 仍写着
`source_commit: 9424b211…`，与该作业实际运行的 commit 不一致。

## 2. 证据

本轮 promotion 的 commit 序列（均为 2026-09-17）：

| commit | 时间 (+08:00) | 标题 |
|---|---|---|
| `e397bef` | 08:34:13 | promotion prepare：候选锁 + V0G 验证作业声明（**已被取代**） |
| `149f993` | 09:16:00 | 强制 E1-C4 绑定被校准的 reference binary，并恢复其源码状态 |
| `9424b21` | 09:16:42 | **作废**建立在非校准 binary 上的候选/最终声明 |
| `b6d24b7` | 09:16:59 | 在恢复后的源码上**重新生成**候选锁与 V0G 声明 |
| `9dd8127` | — | finalize：E1-C4 最终参数锁 |

对两个 commit 的树做逐文件核对：

```
$ git ls-tree -r --name-only <commit> | rg "parameter_lock.cycle4|E1-MATCHED|V0G-SIMULATOR"
9424b21 : lock ABSENT, E1 dir ABSENT, V0G dir ABSENT
b6d24b7 : lock 1, E1 dir 8, V0G dir 8
```

`git show --stat 9424b21` 显示它**删除 17 个文件、512 行**，正是 lock 加 V0G/E1 两个
声明目录的全部内容。也就是说 `9424b21` 是一个「声明不存在」的状态，
而 V0G 却声明在该 commit 上运行。若有人照字面 checkout `9424b21` 再跑 V0G，
被测树里没有 candidate 锁、没有 E1 config，验证必然失败。

## 3. 根因

`prepare(root, calibration, result, v1f_config, source_commit)` 把入参 `source_commit`
同时写进 V0G 的 `config.json` / `commit.txt` 和 candidate 锁的 `promotion_base_commit`。
但 `prepare` 的**产物本身**（锁、V0G/E1 声明）是在这次调用中才写出的，
只能在随后的一次 commit 里落地。于是：

- 调用 `prepare` 时能取到的真实 SHA，必然是「还不含本次产物」的那个 commit；
- 声明里写的 commit 与「含声明的 commit」**结构性错位一格**，
  本轮又恰好落在 `9424b21`（删除声明）上，语义上是最坏取值。

代码对此是**知情**的：`_require_real_commit` 的 docstring 写明该字段
"descriptive only"，并依赖 "V0G records its own live `HEAD`" 来纠偏。
`finalize` 确实用 `result["environment"]["source_commit"]` 覆盖，所以
`source_commit` / `analysis_commit` 最终是正确的 `b6d24b7`。

## 4. 为什么非阻塞

已在本地逐项复核，全部一致：

| 绑定 | 值 | 一致 |
|---|---|---|
| `lock.sha256` == `E1 config.parameter_lock_sha256` == `E1 experiment.json.data_checksums.parameter_lock` | `bee66e70…` | ✅ |
| `E1 config.binary_sha256` == `lock.numerical_calibration.reference_binary_sha256` == `E1 experiment.json…reference_binary` | `87eafa4e…ddee3` | ✅ |
| `E1 experiment.json.commit_id` == `lock.source_commit` | `b6d24b7` | ✅ |

V0G 在 umi 的实况记录（`research/jobs/V0G-SIMULATOR-TESTS-C4/workspace/result.json`）：

- `environment.host = umi`、`environment.working_tree_clean = true`；
- `environment.source_commit = b6d24b76…`（即实况 HEAD，而非声明字段）；
- `pytest.returncode = 0`；
- OpenMP OFF / ON 两套构建均 `pass`。

reference binary SHA `87eafa4e…` 与 V1F 数值校准所用二进制**完全一致**，
E1-C4 的 binary 绑定链完整。

**缺陷的实质是审计记录误导，不是 Gate 失效。**

## 5. 建议修法（下一轮，勿在本轮改）

1. `prepare` 不再把入参 `source_commit` 写进 V0G 的 `config.json` / `commit.txt`；
   改为写 `pending`，由 V0G 运行时记录实况 `HEAD` 并回填，与
   `lock.source_commit = "pending clean V0G checkout"` 的既有约定一致。
2. 或：`prepare` 的产出先 commit，再以该 commit 二次调用 `prepare` 只回填声明字段。
   注意这会在 candidate 阶段重写声明，需保留「两次运行输出逐字节相同」的幂等断言。
3. `_require_real_commit` 的校验不足以覆盖此类错误：它只验证 SHA **存在**，
   不验证该 SHA 的树里**有没有**被引用的声明。建议追加一条前置断言：
   `git ls-tree` 检查声明的目标 commit 是否包含 candidate 锁与对应 job 目录。

## 6. 复核命令（可重放）

```bash
git ls-tree -r --name-only 9424b21 | rg "parameter_lock.cycle4|E1-MATCHED|V0G-SIMULATOR"
git show --stat 9424b21 | head -20
python3 -m autoresearcher.foundation.preflight --exp-dir research/jobs/E1-MATCHED-LANDSCAPES-C4
```

preflight 当前为 `status: ok, checks: 8, passed: 8, failed: []`。
