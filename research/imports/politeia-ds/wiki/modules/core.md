# core — 基础数据层

> 代码路径：`src/core/`
> 物理含义：[[research-proposal#2.2 个体状态向量]]
> SoA 设计：[[DEVELOPMENT_PLAN#1.1 数据布局：SoA（Structure of Arrays）]]

## 职责

存储所有"人"的属性，提供粒子的增删改查。使用 Structure-of-Arrays 布局，使力计算等热点路径可以连续访问同一属性的所有粒子数据，对 CPU 缓存友好。

## 关键文件

### `types.hpp` — 类型别名

| 类型 | 含义 |
|---|---|
| `Real` = `double` | 所有物理量的精度 |
| `Index` = `size_t` | 粒子索引 |
| `Vec2` = `array<Real,2>` | 二维向量（位置、动量） |
| `ParticleStatus` | 粒子状态：Alive/Dead/Pregnant/Nursing |

### `constants.hpp` — 物理常数

| 常量 | 物理含义 | 默认值 |
|---|---|---|
| `DEFAULT_DT` | 时间步长（年） | 0.01 |
| `DEFAULT_TEMPERATURE` | 社会"温度"——随机涨落强度，高温=乱世 | 1.0 |
| `DEFAULT_FRICTION` | 耗散系数 γ——制度损耗率 | 1.0 |
| `DEFAULT_LJ_EPSILON` | LJ 势阱深度——人际吸引强度 | 1.0 |
| `DEFAULT_LJ_SIGMA` | LJ 特征距离——人际"舒适距离" | 1.0 |
| `DEFAULT_LJ_CUTOFF` | LJ 截断距离——超过此距离两人互不影响 | 2.5 |
| `DEFAULT_INITIAL_WEALTH` | 初始人均财富 | 5.0 |
| `DEFAULT_SURVIVAL_THRESHOLD` | 生存阈值——低于此值开始饿死 | 0.1 |
| `DEFAULT_CONSUMPTION_RATE` | 每步资源消耗率——"吃饭"成本 | 0.002 |
| `DEFAULT_PUBERTY_AGE` | 性成熟年龄 | 15.0 |
| `DEFAULT_MENOPAUSE_AGE` | 绝育年龄 | 45.0 |
| `DEFAULT_GESTATION_TIME` | 妊娠期（年） | 0.75 |
| `DEFAULT_NURSING_TIME` | 哺育期（年） | 2.0 |
| `DEFAULT_CULTURE_DIM` | 文化向量维度 | 2 |
| `DEFAULT_ACCIDENT_RATE` | 意外死亡概率/步 | 1e-4 |
| `DEFAULT_GOMPERTZ_BETA` | Gompertz 衰老加速参数 | 0.085 |

### `particle_data.hpp/cpp` — SoA 粒子数据容器

| 数组 | 存储 | 物理含义 |
|---|---|---|
| `x_[N*2]` | 位置 (x,y) 交错 | 这个人在地图上的什么位置 |
| `p_[N*2]` | 动量 (px,py) 交错 | 这个人的移动速度×质量 |
| `w_[N]` | 财富 | 这个人拥有多少可交换的资源 |
| `cv_[N*D]` | 文化向量 | 这个人的知识和文化取向 |
| `eps_[N]` | 能量利用能力 ε | 这个人能利用多少自然能量（技术水平） |
| `age_[N]` | 年龄 | 确定性演化 da/dt=1 |
| `last_birth_time_[N]` | 上次生育时间 | 用于妊娠/哺育冷却期 |
| `status_[N]` | 存活状态 | Alive/Dead/Pregnant/Nursing |
| `force_[N*2]` | 力累加器 | 当前步所有力的合力 |

**关键方法**：
- `add_particle()`: 新生儿出生——在数组末尾添加一个新人
- `mark_dead()`: 标记死亡——设置 status=Dead 但不立即删除（避免打乱索引）
- `compact()`: 压缩数组——移除所有死者，活人索引重排

### `config.hpp/cpp` — 配置文件解析

从 key=value 格式文件读取所有模拟参数。对应研究方案中"可调参数"的集合。

## 依赖关系

- 被所有其他模块依赖（提供基础类型与数据容器）
- 无外部依赖
