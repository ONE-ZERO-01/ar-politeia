# V1G：参考温度下的存储顺序通道判定（预注册）

**状态**：**已完成判定（2026-09-17）**。于 2026-09-17 在 umi 提交运行（jobctl pid 2149600，
128/128 run 全部完成，墙钟 13717 s ≈ 3.81 h，`temperature = 0.5` 已核对）。判定按 §5 的
预先冻结表回填：**`bounded`**（四项界全部 ≤ 冻结上限），故 S18 关闭为"已量化"，不改任何
阈值、不做 C++ 改动。判定记录见 `research/jobs/V1G-ORDER-THERMAL-C4/`：
`order_thermal_report.json`（完整报告，sha256 `93a01493…`）及其 `result.json`/`manifest.json`
（由 `prepare_cycle4_confirmation.py record-diagnostic` 从报告机械导出，非手抄）。
**两处必须随结论引用**：`occupancy_entropy` 已用掉冻结上限的 88%（四项中最紧），
以及 12/128 个 run 未通过逐 run 稳态窗口检查（按 §6 不参与判定）。
**ID**：`V1G-ORDER-THERMAL-C4`（诊断，不是确认性实验）
**对应台账**：S18 / S10；`research/simulator-remediation-status.md` §4.7
**交付物**：`research/src/experiments/run_v1g_order_thermal.py`、
`research/jobs/V1G-ORDER-THERMAL-C4/config.json`、
`tests/test_v1g_order_thermal.py`（18 项，本地通过）

## 1. 问题（一句话）

V1F 的 `order` 层被**强制**在 `temperature = 0.0` 运行（`run_v1_calibration.py:69-75`
对该层校验 `temperature == 0.0`），所以已冻结的数值误差上限是在**唯一按数组下标消费的
随机源被关掉**的条件下测出来的。而 E1-C4/E2-C4 实际用的参考配置是 `temperature = 0.5`，
此时 Langevin 热噪声按数组槽位从有状态 RNG 抽取——**行序决定了每个粒子拿到哪一条噪声
实现**。这一耦合从未被任何一层覆盖。V1G 就是把这个耦合测出来，并回答：

> 已冻结的 `numerical_resolution_limits` 是否覆盖参考温度下的存储顺序通道？

## 2. 设计：只改一个参数

V1G **就是 V1F 的 order 层，只把温度从 `0.0` 改成 `0.5`**。其余全部保持不变：

| 维度 | 取值 | 为什么不能动 |
|---|---|---|
| 景观 | `clustered` | 与 V1F order 层一致；V1F order 矩阵只有 clustered |
| `dt` | `0.005` | E1-C4/E2-C4 的参考步长，也是 V1F 的最细步长 |
| `total_time` | `4500.0` | V1B/V1D 已证 `1500` 的长窗口仍含瞬态，缩短会让"尾部窗口"不再代表稳态 |
| `output_time_interval` | `5.0` | 决定尾部帧数与时间分辨率 |
| 窗口 | 尾 `144` 帧 | 与 V1F 一致 |
| seeds | **V1F 冻结的 64 个**（`V1F-.../seeds.txt`） | 使两标准误界与冻结界**逐 seed 可比**，且 n 与 V1F 相同（64） |
| 相态输入 | `explicit_phase_state = true` | 见 §3 |
| 交换 | 开（`rate 0.5`、`noise 0.05`、`reversion 1.0`） | 参考配置 |
| 参考配置其余开关 | 与 E1-C4 相同（人口/文化/技术/忠诚/征服/瘟疫/容量/气候/河流/mortality 全关） | 参考配置 |

这些"不能动"的量不是靠注释约束的：`validate_v1g_config` 把每一项与**受控的**
`research/jobs/E1-MATCHED-LANDSCAPES-C4/config.json` 逐字比对，任何一项偏离就直接
fail-fast。**最容易被误设的是 `temperature = 0.0`**——那会静默地重跑一遍 V1F，
什么问题都不回答；因此该值被单独校验（必须等于参考温度）。

## 3. 为什么必须显式相态输入

如果 IC 文件不提供 `px,py`，装载器会用 `dist_p(rng)` 按**行位置**抽初始动量
（`ic_loader.cpp:137-143`）。那样一来"canonical vs permuted"同时改变了两件事：行序
**和**每个粒子的初始动量。为了使比较只测行序通道，两份 IC 必须是**同一物理态**：
按 GID 相同的位置、动量、财富、能力、年龄，只有行序不同。

`tests/test_v1g_order_thermal.py::test_probe_inputs_are_one_physical_state_in_two_row_orders`
就是钉住这一点的：对 64 个 seed 逐对检查两份 IC 的**表头相同、行多重集相同、行序确实不同**，
并确认生成的 cfg 是 `temperature = 0.5` / `confirmative_mode = true` / `exchange_enabled = true`。
（该测试已在本地真实调用 `prepare_inputs` 生成 128 个 spec 通过。）

## 4. 估计量与判定规则（预先冻结）

对每个指标 \(m\in\{\)`resource_density_spearman_rho`、`density_morans_i`、
`occupancy_entropy`、`wealth_gini`\(\}\)，按 seed 配对：

\[
d_s = m_s(\text{canonical}) - m_s(\text{permuted}),\quad
B_m = \left|\bar d\right| + 2\,\frac{\mathrm{sd}(d)}{\sqrt{64}}
\]

其中 `sd` 为样本标准差（`ddof=1`）。这与 V1F 的 order 层用的是**同一个**保守原语
（`run_v1_calibration._weak_bound`，直接复用，不重写）。

判定：**当且仅当**对全部四个指标 \(B_m \le \Lambda_m\) 时记为 `bounded`，其中
\(\Lambda_m\) 是从**参数锁**里读出的 `numerical_resolution_limits`
（`resource_density_spearman_rho` 0.00458999、`density_morans_i` 0.00325876、
`occupancy_entropy` 0.000994821、`wealth_gini` 0.00144078）。

阈值不重新推导、不重新舍入、不从脚本常量里取：`load_frozen_bound` 读锁 → 取锁记录的
校准文件路径 → **重算该文件 SHA 并要求与锁里一致** → 从文件与锁**同时**取出上限并要求
两者相等。它还要求 `simulator_validation.binary_sha256` 与
`numerical_calibration.reference_binary_sha256` 一致（S14 的错绑检查），并在启动前校验
待运行 binary 的实际 SHA 等于冻结的参考 binary SHA——**探针只能跑被校准的那个 binary**。

## 5. 结果解读表（先写死，避免事后解释）

| 结果 | 含义 | 后续动作 |
|---|---|---|
| `bounded`（四项全过） | 已冻结的数值上限覆盖参考温度下的存储顺序通道；S18 可关闭为"已量化" | 台账把 S18 从"待实测"改为"已判定：在 64 seed、dt=0.005、尾 144 帧的层面被冻结上限覆盖"；不改任何阈值 |
| `exceeds-frozen-limit`（任一不过） | 参考配置的数值误差界**缺一条腿**：声明为 `T=0` 的界被外推到 `T=0.5` | 把热噪声改为按**稳定 GID** 抽取（S07 对交换噪声已用此法），属 C++ 改动 → 必须重跑校准（S14）→ 必须重做 V1F 与授权链 |

两种结果**都不改**任何已冻结阈值、也不改 E1-C4 的任何结论；E1-C4 的 IC 文件是固定的，
存储顺序不是它的误差来源。V1G 判定的是"误差界这条陈述是否完整"。

## 6. 推断边界（必须随结果一起引用）

- **诊断，不是确认性实验**：不产出任何关于 E1/E2 的科学主张，不得作为其证据引用。
- 结论的作用域是**报告层面**：64 个 seed、dt=0.005、尾 144 帧、四个尾部指标。它不宣称
  `T=0.5` 的一般数值精度，只界定这一条通道。
- n=64 与 V1F 相同，不更强。
- 窗口健康度（逐 run 稳态检查）在报告里记为 `window_caveat`，**不参与判定**：V1G 是两单元
  设计，无法复现校准用的 3×3 condition-ensemble 两窗口 Gate。若出现大量窗口失败，结论
  需带此保留引用。

## 7. 预算与提交

- 规模：64 seeds × 2 orders = **128 runs**，每个 900,000 步、1000 粒子。
- 成本估计：按 V1F 实测 `elapsed_seconds_executed / runs = 1279 s/run`，
  128 × 1279 ≈ 163,700 CPU-秒 ≈ **45.5 CPU-小时**；`parallel = 16` 时约 **2.8 墙钟小时**。
- 提交方式（E1-C4 结束后；`jobctl` 提供崩溃恢复与溯源）：

```bash
python3 -m autoresearcher.foundation.jobctl submit \
  --exp-id V1G-ORDER-THERMAL-C4 \
  --config research/jobs/V1G-ORDER-THERMAL-C4/config.json \
  --command /usr/bin/env PYTHONPATH=src:research/src/experiments OMP_NUM_THREADS=1 \
    python3 research/src/experiments/run_v1g_order_thermal.py \
    --config research/jobs/V1G-ORDER-THERMAL-C4/config.json \
    --output-dir research/jobs/V1G-ORDER-THERMAL-C4/workspace \
  --artifact research/jobs/V1G-ORDER-THERMAL-C4/workspace/order_thermal_report.json \
  --seeds 11003,11027,...  # 与 config.json 的 seeds 一致
```

- 完成后：`jobctl reconcile` → `record-diagnostic` 把报告与判定落进 job 目录 →
  把判定回填台账 S18 → 按 §5 的对应行行动。**不运行前不写任何结论。**
  这四步均已于 2026-09-17 完成，判定 `bounded`，记录方式见 §9。

## 8. 提交时序

E1-C4 已结束（128/128，claim supported），因此 V1G 已按本节的条件提交（jobctl pid 2149600）。
提交前的实际步骤：补齐声明集（seeds/env/outputs/data_checksums/computational_strategy/
experiment，冻结身份全部取自已跟踪的最终锁并逐项交叉校验）→ `preflight` 8/8 通过 →
`jobctl submit`。`commit.txt` 指向 `6f39c02c7047949f9c1b7d61d6518add1990fa45`，该 commit 确实
包含 V1G 的脚本、配置与全部声明。

E1-C4 正在 umi 上运行，占用并发槽位；V1G 使用 `parallel = 16`，与 E1-C4 叠加会互相
拖慢并使运行时长估计失真。另外：**在 E1-C4 运行期间不改共享驱动**——崩溃恢复可能重跑
`prepare_inputs`，改动会让已授权实验的生成 cfg 与既存 run 目录不一致（S15 同类风险）。
V1G 的新文件都是新增，不触碰共享路径，因此可以在 E1-C4 结束后立即提交。

## 9. 判定记录与回收（2026-09-17 补记）

`jobctl reconcile` 只**校验**声明产物，不写任何东西；它自己的记录在 git 忽略的
`.autoresearcher/` 下，而 `workspace/` 同样被忽略。所以"数字只存在于 workspace"的诊断
在 git 里不会有任何可审计痕迹。本轮为此新增 `prepare_cycle4_confirmation.py`
的 `record-diagnostic` 子命令，把这一步做成机械的：

```bash
python3 research/src/experiments/prepare_cycle4_confirmation.py record-diagnostic \
  --job-dir research/jobs/V1G-ORDER-THERMAL-C4 \
  --jobctl-dir .autoresearcher/jobs/V1G-ORDER-THERMAL-C4 \
  --conclusion-artifact order_thermal_report.json \
  --workspace-artifact order_thermal_report.json \
  --workspace-artifact replicate_metrics.csv \
  --workspace-artifact matched_input_audit.json
```

它把结论产物原子地复制进 job 目录（复制后校验 sha256 与源相同），并由报告与 jobctl
result **推导**出 `result.json` 与 `manifest.json`，不接受任何外部传入的数字；jobctl 记为
失败或超时的 job 一律拒绝记录，且所有校验在任何写入之前完成，故失败时 job 目录保持原样。
入库的三份记录：

| 文件 | 内容 |
|---|---|
| `order_thermal_report.json` | 完整报告，sha256 `93a014935f9c…`，与 workspace 源逐字节相同 |
| `result.json` | 判定 `bounded`、四项界与其冻结上限、run 数、窗口告警、绑定 SHA（参数锁 / V1F 校准 / 参考 binary） |
| `manifest.json` | jobctl 对账形状，列出三个 workspace 产物各自的 sha256 |

`tests/test_prepare_cycle4_confirmation.py` 有 9 项测试覆盖该步骤，含"改变产物则记录随之
改变"的变异检验（防止记录退化成固定投影）。
