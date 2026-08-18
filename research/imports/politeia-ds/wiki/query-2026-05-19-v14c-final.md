# Query: v14c 全量基线终局摘要

> 自动生成: 2026-05-19T21:26:44+08:00

## 运行状态
```
  [20000/20000]  N=59671  Gini=0.8  (async heavy analysis launched)
[Checkpoint] Wrote 59671 particles to examples/genesis_100k_v14b_output/checkpoint_step_20000.bin (7639864 bytes)
  Load: time(max=1423.433ms min=1423.433ms avg=1423.433ms) eff=100.0% particles(max=59671 min=59671)
  Phases: dynamics=5.37% exchange=3.11% culture=4.93% technology=2.57% resources=3.10% population=64.35% migration=0.38% analysis=0.22% io=15.98% 
Step 20000/20000  N=59671  Gini=0.775908  Q=0.956049  H=53  polities=1594(2459b370t251c11s0e)  largest=3386  HHI=0.0191286
[Checkpoint] Wrote 59671 particles to examples/genesis_100k_v14b_output/checkpoint_final_step_20000.bin (7639864 bytes)

Simulation complete. Wall time: 5e+04 s
```

## 终局序参量 (step 20000)

| 指标 | 值 |
|------|-----|
| N | 59671 |
| Gini | 0.776 |
| Q | 0.956 |
| H | **53** |
| largest_polity | 3386 |
| empires | 0 |
| mean_loyalty | 0.759 |

## order_params 时间序列
```csv
step,time,N,Gini,Q,mean_eps,H,C,F,Psi,mean_loyalty,n_attached,Gini_Power
5000,50,75570,0.76903107,0.27102994,1.0364696,57,3888,0.089810771,0.41154232,0.83579135,71682,0.97091448
10000,100,62682,0.77395968,0.44867569,1.0373992,48,2861,0.045228295,0.40831334,0.79923273,59821,0.96512359
15000,150,60208,0.77326512,0.75393807,1.0379883,40,3103,0.043316503,0.40479358,0.75263054,57105,0.95855004
20000,200,59671,0.77590817,0.95604855,1.0391074,53,3038,0.056744482,0.41889685,0.75947639,56633,0.96267956
```

## 人口 (demographics 末行)
```csv
18000,180,58602,9575,9007,34.9473,33.54,0.415088,0.24122,0.169295,0.0096925
19000,190,59183,8714,8133,34.8995,33.28,0.43161,0.226332,0.157883,0.00981701
20000,200,59671,8277,7789,35.4915,33.77,0.443934,0.209448,0.161033,0.00817818
```

## 政体 (polity_summary)
```csv
time,n_polities,n_multi,largest_pop,HHI,mean_pop,bands,tribes,chiefdoms,states,empires
50,3940,1674,6787,0.0351534,19.1802,3306,371,247,13,3
100,2909,1347,5180,0.0221046,21.5476,2414,268,216,10,1
150,3151,1502,3548,0.0147056,19.1076,2522,337,282,10,0
200,3091,1594,3386,0.0191286,19.3048,2459,370,251,11,0
```

### checkpoint step 5000
```
particles=75570
max_depth=57 mean_depth=14.27
depth_gt10=40536
cycle_particles=38028
  depth 8: 2960
  depth 9: 2806
  depth 10: 2636
  depth 11: 2616
  depth 12: 2537
  depth 13: 1774
  depth 14: 1687
  depth 15: 1839
```
### checkpoint step 10000
```
particles=62682
max_depth=64 mean_depth=13.63
depth_gt10=32173
cycle_particles=28894
  depth 8: 2185
  depth 9: 2264
  depth 10: 1845
  depth 11: 2305
  depth 12: 2169
  depth 13: 2024
  depth 14: 2005
  depth 15: 1869
```
### checkpoint step 15000
```
particles=60208
max_depth=52 mean_depth=11.06
depth_gt10=25922
cycle_particles=22077
  depth 8: 2375
  depth 9: 2114
  depth 10: 2178
  depth 11: 1956
  depth 12: 1848
  depth 13: 1697
  depth 14: 1613
  depth 15: 1648
```
### checkpoint step 20000
```
particles=59671
max_depth=53 mean_depth=12.13
depth_gt10=27627
cycle_particles=20996
  depth 8: 2047
  depth 9: 2141
  depth 10: 1997
  depth 11: 1667
  depth 12: 1655
  depth 13: 1466
  depth 14: 1670
  depth 15: 1710
```

## 序参量对照 (v14c vs v16)
```
run        step        N    H     Gini        Q  loyalty   attached
------------------------------------------------------------------------
v14c      20000    59671   53   0.7759   0.9560   0.7595      56633
v16        3000    25954    4   0.6525   0.4932   0.3032      16431
v17      (no data)
```

## v17 验收标准（对照本基线）

| 检查 | v14c @20k | v17 目标 |
|------|-----------|----------|
| H | 53 | ≤10 |
| checkpoint 环 @20k | ~20996 | 0 |
| largest_pop @10k | 5180 | ≥1000 |
| KE/(N·T) | ~1.3 | <2 |

## 相关
- [[query-2026-05-19-hierarchy-baseline]]
- [[reflection-2026-05-19-v5]]
