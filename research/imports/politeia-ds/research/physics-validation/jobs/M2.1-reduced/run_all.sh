#!/bin/bash
# M2.1-reduced v2: China vs Europe 对照实验
# 锁定 M1.16 全套 STATE 参数, 10K×10000步×3 seeds×2 地形 = 6 runs

set -euo pipefail
BASE="/home/wanwb/ONE/Politeia-ds/research/physics-validation/jobs/M2.1-reduced"
mkdir -p "$BASE/cfgs" "$BASE/output"

BASE_CFG() {
cat <<ENDCFG
initial_particles = 10000
total_steps = 10000
dt = 0.01
output_interval = 500
compact_interval = 500
network_window_factor = 5

temperature = 0.3
friction = 1.0

social_strength = 3.0
social_distance = 1.0
interaction_range = 3.0

terrain_scale = 0.5

carrying_capacity_base = 20.0
density_radius = 5.0
max_fertility = 1e-4
nursing_time = 1.5

exchange_rate = 0.003
ability_saturation_w = 5.0
wealth_decay_rate = 0.02
attachment_threshold = 0.05

tax_rate = 0.05
tax_efficiency = 0.5
loyalty_protection_gain = 0.03
loyalty_tax_drain = 0.1

assimilation_rate = 0.005
hierarchy_assimilation_rate = 0.3

conquest_base_prob = 1.0
conquest_power_ratio = 0.8

deterrence_enabled = true
deterrence_ratio = 2.0

loyalty_enabled = true
conquest_enabled = true
culture_enabled = true
technology_enabled = true
plague_enabled = true
reproduction_enabled = true
carrying_capacity_enabled = true
gender_enabled = true
age_pyramid = true
culture_dim = 4

max_hierarchy_depth = 10
hierarchy_repair_interval = 500
succession_heir_loyalty_cap = 0.9
succession_loyalty_factor = 0.95
ENDCFG
}

EXE=/home/wanwb/ONE/Politeia-ds/builds/build-v13/src/politeia
COUNT=0
SUCES=0

for terrain in china europe; do
  for seed in 42 123 456; do
    tag="${terrain}_s${seed}"
    cfg="$BASE/cfgs/${tag}.cfg"
    {
      BASE_CFG
      echo "terrain_type = $terrain"
      echo "random_seed = $seed"
      echo "output_dir = $BASE/output/${tag}"
    } > "$cfg"
    mkdir -p "$BASE/output/${tag}"
    COUNT=$((COUNT + 1))
    echo "$(date '+%H:%M:%S') [$COUNT/6] $tag ..."
    "$EXE" "$cfg" > "$BASE/output/${tag}/stdout.log" 2>"$BASE/output/${tag}/stderr.log"
    rc=$?
    if [ $rc -eq 0 ]; then
      SUCES=$((SUCES + 1))
      echo "$(date '+%H:%M:%S') [$COUNT/6] $tag ✅ (rc=$rc)"
    else
      echo "$(date '+%H:%M:%S') [$COUNT/6] $tag ❌ (rc=$rc)"
    fi
  done
done

echo "=============================="
echo "$(date '+%H:%M:%S') M2.1-reduced DONE: $SUCES/$COUNT success"

echo ""
echo "=== 结果摘要 ==="
for terrain in china europe; do
  for seed in 42 123 456; do
    tag="${terrain}_s${seed}"
    sum="$BASE/output/${tag}/polity_summary.csv"
    demo="$BASE/output/${tag}/demographics.csv"
    if [ -f "$sum" ] && [ -s "$sum" ]; then
      last_sum=$(tail -1 "$sum")
      last_demo=$(tail -1 "$demo" | cut -d',' -f1,3)
      echo "  $tag: $last_sum | N_end=$(tail -1 $demo | cut -d',' -f3)"
    else
      echo "  $tag: MISSING"
    fi
  done
done
