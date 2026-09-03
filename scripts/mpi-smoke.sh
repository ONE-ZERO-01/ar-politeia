#!/usr/bin/env bash
set -euo pipefail

# Run a minimal two-rank Politeia smoke test. This script is intended for
# hosts where MPI is already available (mpicxx/mpirun). It writes all build and
# run artifacts under research/jobs/MPI-SMOKE/workspace/, which is git-ignored.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if ! command -v mpicxx >/dev/null 2>&1; then
    echo "mpicxx not found; install an MPI implementation and retry" >&2
    exit 2
fi
if ! command -v mpirun >/dev/null 2>&1; then
    echo "mpirun not found; install an MPI implementation and retry" >&2
    exit 2
fi

WORK_DIR="$ROOT_DIR/research/jobs/MPI-SMOKE/workspace"
BUILD_DIR="$WORK_DIR/build"
RUN_DIR="$WORK_DIR/run"
mkdir -p "$RUN_DIR"

cat > "$RUN_DIR/mpi_smoke.cfg" <<'EOF'
domain_xmin = 0
domain_xmax = 100
domain_ymin = 0
domain_ymax = 100
dt = 0.01
total_steps = 20
output_interval = 10
compact_interval = 10
initial_particles = 200
temperature = 0.5
friction = 1.0
social_strength = 0.0
interaction_range = 2.5
exchange_rate = 0.0
exchange_noise_strength = 0.0
terrain_type = flat
terrain_force_enabled = false
terrain_production_enabled = false
culture_enabled = false
technology_enabled = false
loyalty_enabled = false
conquest_enabled = false
plague_enabled = false
carrying_capacity_enabled = false
reproduction_enabled = false
mortality_enabled = false
climate_enabled = false
river_enabled = false
snapshot_binary = false
checkpoint_interval = 0
output_dir = research/jobs/MPI-SMOKE/workspace/run/output
EOF

cmake -S research/src/experiments/politeia \
      -B "$BUILD_DIR" \
      -DCMAKE_BUILD_TYPE=Release \
      -DPOLITEIA_USE_MPI=ON
cmake --build "$BUILD_DIR" -j8

mpirun -np 2 "$BUILD_DIR/src/politeia" "$RUN_DIR/mpi_smoke.cfg"
echo "MPI smoke test passed"
