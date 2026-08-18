#!/bin/bash
# M2.1: 中国 vs 欧洲 大规模制度涌现对比
# 3 seeds × 2 terrains = 6 runs, ~6-12h total on Zeus A100
set -e

BASE=$(dirname "$0")/../../../..
cd "$BASE"
BINARY="./build-pv/src/politeia"

TERRAINS=(china europe)
SEEDS=(42 123 999)

for terrain in "${TERRAINS[@]}"; do
  for seed in "${SEEDS[@]}"; do
    TAG="${terrain}_seed${seed}"
    OUTDIR="research/physics-validation/jobs/M2.1/output/${TAG}"
    CFG="research/physics-validation/jobs/M2.1/run_${TAG}.cfg"

    mkdir -p "$OUTDIR"

    # Generate config from template
    sed -e "s/random_seed = 42/random_seed = ${seed}/" \
        -e "s|output_dir = .*|output_dir = ${OUTDIR}|" \
        "research/physics-validation/jobs/M2.1/m2.1_${terrain}_template.cfg" > "$CFG"

    echo "=== M2.1: ${terrain} seed=${seed} ==="
    echo "  Config: ${CFG}"
    echo "  Output: ${OUTDIR}"
    echo "  Started: $(date)"
    OMP_NUM_THREADS=48 "$BINARY" "$CFG" > "${OUTDIR}/stdout.log" 2> "${OUTDIR}/stderr.log" &

    PID=$!
    echo "  PID: ${PID}"
    echo "${PID} ${TAG} $(date +%s)" >> research/physics-validation/jobs/M2.1/pids.txt
    sleep 1  # pace launches
  done
done

echo ""
echo "All 6 M2.1 jobs launched. Monitor with:"
echo "  ssh zeus 'tail -f research/physics-validation/jobs/M2.1/output/*/stderr.log'"
echo "  ssh zeus 'ps aux | grep politeia | grep -v grep | wc -l'"
