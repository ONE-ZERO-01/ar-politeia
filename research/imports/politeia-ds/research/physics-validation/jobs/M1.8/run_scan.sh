#!/bin/bash
# M1.8: 涨落-耗散定理验证 — T×γ 参数扫描
# 16 组合: T=0.1,0.5,1.0,2.0 × γ=0.1,0.5,1.0,2.0

cd "$(dirname "$0")/../../../.."
BINARY="./build-pv/src/politeia"
TEMPLATE="research/physics-validation/jobs/M1.8/m1.8_template.cfg"

mkdir -p research/physics-validation/jobs/M1.8/output

for T in 0.1 0.5 1.0 2.0; do
  for GAMMA in 0.1 0.5 1.0 2.0; do
    TAG="T${T}_g${GAMMA}"
    CFG="research/physics-validation/jobs/M1.8/run_${TAG}.cfg"
    OUT="research/physics-validation/jobs/M1.8/output/${TAG}"

    mkdir -p "$OUT"

    sed -e "s/T_PLACEHOLDER/${T}/g" \
        -e "s/GAMMA_PLACEHOLDER/${GAMMA}/g" \
        -e "s|OUTPUT_PLACEHOLDER|${OUT}|g" \
        "$TEMPLATE" > "$CFG"

    echo "=== M1.8: T=${T} γ=${GAMMA} ==="
    OMP_NUM_THREADS=48 timeout 60 "$BINARY" "$CFG" 2>&1 | tail -3
  done
done

echo "=== M1.8 Energy Summary ==="
for f in research/physics-validation/jobs/M1.8/output/T*/energy.csv; do
  tag=$(echo "$f" | grep -o 'T[0-9.]*_g[0-9.]*')
  last_ke=$(tail -1 "$f" 2>/dev/null | cut -d',' -f3)
  last_total=$(tail -1 "$f" 2>/dev/null | cut -d',' -f6)
  echo "$tag  KE=$last_ke  Total=$last_total"
done
