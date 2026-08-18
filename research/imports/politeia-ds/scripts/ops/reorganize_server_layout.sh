#!/usr/bin/env bash
# One-time layout cleanup (already applied 2026-06-11 on zeus).
# Safe to re-run: skips missing items.
# Moves files only — nothing is deleted.
set -euo pipefail

PROJ="/home/wanwb/ONE/Politeia-ds"
cd "$PROJ"

echo "=== Politeia-ds layout reorganize @ $(date) ==="

mkdir -p builds logs/build logs/cmake logs/run scripts/ops archive presentations

# --- Build trees → builds/ ---
for d in build build2 build-v11 build-v12 build-v12b; do
    if [[ -d "$d" && ! -L "$d" ]]; then
        echo "move dir: $d → builds/$d"
        mv "$d" "builds/$d"
    fi
done

# Backward-compat symlinks (old scripts expect build/ build2/ at repo root)
ln -sfn builds/build build
ln -sfn builds/build2 build2

# --- Build / cmake logs at repo root → logs/ ---
for f in build2.log build_full.log build_log.txt build_status.txt \
         build_v13.log build_v15_report.txt \
         cmake_configure.log cmake_log.txt cmake_out.log; do
    if [[ -f "$f" ]]; then
        echo "move log: $f → logs/build/"
        mv "$f" "logs/build/$f"
    fi
done

# --- Misc diagnostic dumps → archive/ ---
for f in status.txt progress.txt progress_check.txt restart_report.txt \
         latest.txt debug_env.txt cleanup.txt demo.txt \
         polity_detail.txt polity_events_head.txt run_head.txt; do
    if [[ -f "$f" ]]; then
        echo "move archive: $f"
        mv "$f" "archive/$f"
    fi
done

# --- Root ops shell scripts → scripts/ops/ ---
for f in check_status.sh do_build.sh do_build2.sh push.sh rebuild_v15.sh \
         restart_full_sim.sh run_full_v17.sh run_quick_v15.sh run_quick_v16.sh \
         RUN_ME.sh env.sh; do
    if [[ -f "$f" ]]; then
        echo "move ops: $f → scripts/ops/"
        mv "$f" "scripts/ops/$f"
    fi
done

# --- Presentations ---
for f in *.pptx; do
    if [[ -f "$f" ]]; then
        echo "move pptx: $f → presentations/"
        mv "$f" "presentations/$f"
    fi
done
if [[ -d ppt-template && ! -L ppt-template ]]; then
    echo "move dir: ppt-template → presentations/"
    mv ppt-template presentations/ppt-template
fi

# --- README for new layout ---
cat > LAYOUT.md << 'EOF'
# Politeia-ds 目录布局

> 根目录只保留源码、配置、文档；构建产物与运维脚本分目录存放。

## 根目录（与本地 Politeia-ds 对齐）

| 路径 | 用途 |
|------|------|
| `src/` `tests/` `scripts/` `examples/` | 代码与算例 |
| `docs/` `wiki/` `workflow/` `rules/` | 文档 |
| `data/` `raw/` `checkpoints/` `sweep_results/` | 数据与实验产物 |
| `CMakeLists.txt` `pyproject.toml` `research-proposal.md` 等 | 项目元数据 |
| `build` `build2` | **符号链接** → `builds/build` `builds/build2`（兼容旧脚本） |

## 服务端专用

| 路径 | 用途 |
|------|------|
| `builds/` | 所有 CMake 构建树（build, build2, build-v11…） |
| `logs/build/` | 编译日志（build2.log, cmake_*.log 等） |
| `scripts/ops/` | 运维脚本（do_build, run_full_v17, env.sh 等） |
| `archive/` | 历史状态/调试文本 dump |
| `presentations/` | PPT 与模板 |

## 常用命令

```bash
cd /home/wanwb/ONE/Politeia-ds
source scripts/ops/env.sh
bash scripts/ops/run_full_v17.sh
tail -f logs/build/build2.log
```
EOF

echo "=== Done. Root listing: ==="
ls -la "$PROJ" | head -35
