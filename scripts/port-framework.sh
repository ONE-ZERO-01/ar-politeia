#!/usr/bin/env bash
# ============================================================
# port-framework.sh — 将 AutoResearcher 框架迁移 / 同步到其他研究项目
#
# 经验来源：auto-researcher-one → AR-Seismic 手工迁移。
#
# 拷贝（框架 + 服务器信息）：
#   src/  orchestration/  rules/  tests/  workflow/
#   AGENTS.md README.md autoresearcher.md SUBMISSION_CHECKLIST.md
#   pyproject.toml 框架设计图* multi-agent-project-map.html
#
# 不拷贝（研究内容 / 生成物）：
#   research/  reviews/  研究专用 scripts（如 run_p1_*.sh）
#   .git/  .pytest_cache/  *.egg-info  .DS_Store  .venv/
#
# 单向边界：
#   SOURCE_ROOT 始终只读；所有写入只能发生在 DEST。
#   .gitignore、.framework-port.json 和本脚本由目标项目管理，sync 不从源覆盖。
#
# 用法：
#   # 首次迁移（默认创建 research/ 脚手架）
#   bash scripts/port-framework.sh migrate /path/to/NewProject \
#     --project-id my-project --title "My Project" \
#     --server-root /home/wanwb/ONE/my-project
#
#   # 后续：框架源仓库有更新时，同步到已迁移项目（不碰 research/）
#   bash scripts/port-framework.sh sync /path/to/NewProject
#   # 或在目标项目内：
#   bash scripts/port-framework.sh sync
#
#   bash scripts/port-framework.sh status [/path/to/Project]
#   bash scripts/port-framework.sh migrate ... --dry-run
#   bash scripts/port-framework.sh migrate ... --no-scaffold
#   bash scripts/port-framework.sh migrate ... --force  # 仅用于明确要覆盖的非空目标
# ============================================================
set -euo pipefail

SCRIPT_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONTROLLER_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# 源仓库根判定：
# 1) 显式 --source
# 2) 目标（或当前目录）的 .framework-port.json → source
# 3) 脚本所在仓库若含 .framework-source 标记（框架权威源）
# 4) 否则脚本上一级目录（需用户确认，migrate 时建议从权威源调用）
PORT_CONFIG_NAME=".framework-port.json"
SOURCE_ROOT=""
SOURCE_EXPLICIT=0

detect_source_root() {
  local candidate port_src
  if [[ -n "$SOURCE_ROOT" && "$SOURCE_EXPLICIT" -eq 1 ]]; then
    echo "$SOURCE_ROOT"
    return
  fi
  # 已迁移项目内的 port 配置
  for candidate in "${DEST:-}" "$(pwd)"; do
    [[ -n "$candidate" && -f "$candidate/$PORT_CONFIG_NAME" ]] || continue
    port_src="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get('source',''))" "$candidate/$PORT_CONFIG_NAME" 2>/dev/null || true)"
    if [[ -n "$port_src" && -d "$port_src/src/autoresearcher" && -f "$port_src/.framework-source" ]]; then
      echo "$port_src"
      return
    fi
    if [[ -n "$port_src" && -d "$port_src/src/autoresearcher" ]]; then
      echo "$port_src"
      return
    fi
  done
  candidate="$(cd "$SCRIPT_DIR/.." && pwd)"
  if [[ -f "$candidate/.framework-source" && -d "$candidate/src/autoresearcher" ]]; then
    echo "$candidate"
    return
  fi
  echo "$candidate"
}
DRY_RUN=0
SCAFFOLD=1
FORCE=0
PROJECT_ID=""
TITLE=""
SERVER_ROOT=""
GITHUB_URL=""
HYPOTHESIS_FILE="research/hypothesis.md"
DEST=""

# ---------- 框架清单（相对源根）----------
FRAMEWORK_DIRS=(
  orchestration
  rules
  src
  tests
  workflow
)

FRAMEWORK_FILES=(
  AGENTS.md
  README.md
  SUBMISSION_CHECKLIST.md
  autoresearcher.md
  multi-agent-project-map.html
  pyproject.toml
  框架图.html
  框架设计图.md
  逻辑结构图.html
)

# 源仓库里「研究方案」痕迹的默认值（替换前）
SRC_PROJECT_ID="diff-entangle-geometry-cosmo"
SRC_TITLE="分化—纠缠—几何宇宙论"
SRC_SERVER_ROOT="/home/wanwb/ONE/autoresearcher-one"
SRC_GITHUB_URL="https://github.com/ONE-ZERO-01/diff-entangle-geometry.git"
SRC_REPO_NAME="diff-entangle-geometry"
SRC_HYPOTHESIS_FILE="research/分化-纠缠-几何宇宙论-研究假说.md"

usage() {
  sed -n '2,35p' "$SCRIPT_PATH" | sed 's/^# \?//'
  exit "${1:-0}"
}

log()  { printf '→ %s\n' "$*"; }
warn() { printf '⚠ %s\n' "$*" >&2; }
die()  { printf '✗ %s\n' "$*" >&2; exit 1; }

run() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    printf '[dry-run] %s\n' "$*"
  else
    "$@"
  fi
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "需要命令: $1"
}

# ---------- 参数解析 ----------
CMD="${1:-}"
[[ -n "$CMD" ]] || usage 1
shift || true

case "$CMD" in
  -h|--help|help) usage 0 ;;
  migrate|sync|status) ;;
  *) die "未知命令: $CMD（migrate | sync | status）" ;;
esac

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project-id)
      [[ -n "${2:-}" ]] || die "--project-id 需要一个值"
      PROJECT_ID="$2"; shift 2
      ;;
    --title)
      [[ -n "${2:-}" ]] || die "--title 需要一个值"
      TITLE="$2"; shift 2
      ;;
    --server-root)
      [[ -n "${2:-}" ]] || die "--server-root 需要一个值"
      SERVER_ROOT="$2"; shift 2
      ;;
    --github-url)
      [[ -n "${2:-}" ]] || die "--github-url 需要一个值"
      GITHUB_URL="$2"; shift 2
      ;;
    --hypothesis-file)
      [[ -n "${2:-}" ]] || die "--hypothesis-file 需要一个值"
      HYPOTHESIS_FILE="$2"; shift 2
      ;;
    --source)
      [[ -n "${2:-}" ]] || die "--source 需要一个值"
      SOURCE_ROOT="$2"
      SOURCE_EXPLICIT=1
      shift 2
      ;;
    --no-scaffold)     SCAFFOLD=0; shift ;;
    --scaffold)        SCAFFOLD=1; shift ;;
    --dry-run)         DRY_RUN=1; shift ;;
    --force)           FORCE=1; shift ;;
    -h|--help)         usage 0 ;;
    -*)                die "未知选项: $1" ;;
    *)
      if [[ -z "$DEST" ]]; then
        DEST="$1"; shift
      else
        die "多余参数: $1"
      fi
      ;;
  esac
done

# 保存 CLI 显式覆盖（避免被 port 配置覆盖）
CLI_PROJECT_ID="$PROJECT_ID"
CLI_TITLE="$TITLE"
CLI_SERVER_ROOT="$SERVER_ROOT"
CLI_GITHUB_URL="$GITHUB_URL"
CLI_HYPOTHESIS_FILE="$HYPOTHESIS_FILE"

# sync/status 无 DEST 时默认当前目录
if [[ -z "$DEST" ]]; then
  if [[ "$CMD" == "migrate" ]]; then
    die "migrate 需要目标路径：migrate <dest-dir> --project-id ..."
  fi
  DEST="$(pwd)"
fi

if [[ "$CMD" == "migrate" ]]; then
  # resolve(strict=False) 只规范化路径，不创建目录，保证 --dry-run 无目标侧写入。
  DEST="$(python3 - "$DEST" <<'PY'
import pathlib, sys
print(pathlib.Path(sys.argv[1]).expanduser().resolve(strict=False))
PY
)"
else
  DEST="$(cd "$DEST" && pwd)" || die "无法进入目标目录: $DEST"
fi

SOURCE_ROOT="$(detect_source_root)"
SOURCE_ROOT="$(cd "$SOURCE_ROOT" && pwd)" || die "源仓库不存在: $SOURCE_ROOT"
[[ -d "$SOURCE_ROOT/src/autoresearcher" ]] || die "源仓库不像 AutoResearcher 框架: $SOURCE_ROOT"
[[ -f "$SOURCE_ROOT/pyproject.toml" ]] || die "源仓库缺少 pyproject.toml: $SOURCE_ROOT"

# ---------- 读写 .framework-port.json ----------
load_port_config() {
  local cfg="$DEST/$PORT_CONFIG_NAME"
  [[ -f "$cfg" ]] || return 1
  eval "$(python3 - "$cfg" <<'PY'
import json, shlex, sys
c = json.load(open(sys.argv[1]))
for k, env in [
    ("project_id", "PROJECT_ID"),
    ("title", "TITLE"),
    ("server_root", "SERVER_ROOT"),
    ("github_url", "GITHUB_URL"),
    ("hypothesis_file", "HYPOTHESIS_FILE"),
]:
    v = c.get(k)
    if v:
        print(f'{env}={shlex.quote(str(v))}')
# source 仅在未显式 --source 时采用
src = c.get("source") or ""
if src:
    print(f'_PORT_SOURCE={shlex.quote(str(src))}')
PY
)"
  if [[ "$SOURCE_EXPLICIT" -ne 1 && -n "${_PORT_SOURCE:-}" && -d "$_PORT_SOURCE/src/autoresearcher" ]]; then
    SOURCE_ROOT="$(cd "$_PORT_SOURCE" && pwd)"
  fi
  # CLI 覆盖配置文件
  if [[ -n "$CLI_PROJECT_ID" ]]; then PROJECT_ID="$CLI_PROJECT_ID"; fi
  if [[ -n "$CLI_TITLE" ]]; then TITLE="$CLI_TITLE"; fi
  if [[ -n "$CLI_SERVER_ROOT" ]]; then SERVER_ROOT="$CLI_SERVER_ROOT"; fi
  if [[ -n "$CLI_GITHUB_URL" ]]; then GITHUB_URL="$CLI_GITHUB_URL"; fi
  if [[ -n "$CLI_HYPOTHESIS_FILE" ]]; then HYPOTHESIS_FILE="$CLI_HYPOTHESIS_FILE"; fi
  return 0
}

write_port_config() {
  local cfg="$DEST/$PORT_CONFIG_NAME"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    log "[dry-run] 写入 $cfg"
    return
  fi
  PORT_CONFIG_PATH="$cfg" \
  PORT_CONFIG_SOURCE="$SOURCE_ROOT" \
  PORT_CONFIG_PROJECT_ID="$PROJECT_ID" \
  PORT_CONFIG_TITLE="$TITLE" \
  PORT_CONFIG_SERVER_ROOT="$SERVER_ROOT" \
  PORT_CONFIG_GITHUB_URL="$GITHUB_URL" \
  PORT_CONFIG_HYPOTHESIS_FILE="$HYPOTHESIS_FILE" \
  python3 <<'PY'
import json, pathlib
import os

cfg = pathlib.Path(os.environ["PORT_CONFIG_PATH"])
data = {
  "schema_version": 1,
  "source": os.environ["PORT_CONFIG_SOURCE"],
  "project_id": os.environ["PORT_CONFIG_PROJECT_ID"],
  "title": os.environ["PORT_CONFIG_TITLE"],
  "server_root": os.environ["PORT_CONFIG_SERVER_ROOT"],
  "github_url": os.environ["PORT_CONFIG_GITHUB_URL"],
  "hypothesis_file": os.environ["PORT_CONFIG_HYPOTHESIS_FILE"],
  "notes": "由 scripts/port-framework.sh 维护；sync 时按此配置替换研究方案痕迹。",
}
cfg.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"wrote {cfg}")
PY
}

validate_project_config() {
  [[ "$PROJECT_ID" =~ ^[a-z][a-z0-9]*(-[a-z0-9]+)*$ ]] || \
    die "project_id 必须为小写 kebab-case，且以字母开头: $PROJECT_ID"
  [[ -n "$TITLE" ]] || die "title 不能为空"
  [[ "$SERVER_ROOT" == /* ]] || die "server_root 必须是绝对路径: $SERVER_ROOT"
  PORT_HYPOTHESIS_FILE="$HYPOTHESIS_FILE" python3 <<'PY' || exit 1
import os
from pathlib import PurePosixPath

raw = os.environ["PORT_HYPOTHESIS_FILE"]
path = PurePosixPath(raw)
if path.is_absolute() or ".." in path.parts or not path.parts or path.parts[0] != "research":
    raise SystemExit(
        f"✗ hypothesis_file 必须是 research/ 下且不含 .. 的相对路径: {raw}"
    )
PY
}

defaults_from_dest_name() {
  local base
  base="$(basename "$DEST")"
  if [[ -z "$PROJECT_ID" ]]; then
    # 目录名转 kebab-case 小写
    PROJECT_ID="$(printf '%s' "$base" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/-/g; s/--*/-/g; s/^-//; s/-$//')"
  fi
  if [[ -z "$TITLE" ]]; then
    TITLE="$base"
  fi
  if [[ -z "$SERVER_ROOT" ]]; then
    SERVER_ROOT="/home/wanwb/ONE/$PROJECT_ID"
  fi
  if [[ -z "$GITHUB_URL" ]]; then
    GITHUB_URL="https://github.com/<org>/${PROJECT_ID}.git"
  fi
}

# ---------- 拷贝框架 ----------
copy_framework() {
  need_cmd rsync
  local d f
  log "源: $SOURCE_ROOT"
  log "目标: $DEST"

  for d in "${FRAMEWORK_DIRS[@]}"; do
    [[ -d "$SOURCE_ROOT/$d" ]] || die "源缺少目录: $d"
    log "同步目录 $d/"
    if [[ "$DRY_RUN" -eq 1 ]]; then
      if [[ -d "$DEST" ]]; then
        rsync -a --delete --dry-run --itemize-changes \
          --exclude='.git/' \
          --exclude='.autoresearcher/' \
          --exclude='sync_direction_C_remote/' \
          --exclude='.DS_Store' \
          --exclude='*.egg-info' \
          --exclude='__pycache__' \
          --exclude='.pytest_cache' \
          --exclude='research-graph.json' \
          --exclude='test_port_framework.py' \
          "$SOURCE_ROOT/$d/" "$DEST/$d/"
      else
        log "[dry-run] 将新建并复制 $d/"
      fi
    else
      mkdir -p "$DEST/$d"
      # 框架目录以源为准；被 exclude 的目标项目文件不会被 --delete 删除。
      rsync -a --delete \
        --exclude='.git/' \
        --exclude='.autoresearcher/' \
        --exclude='sync_direction_C_remote/' \
        --exclude='.DS_Store' \
        --exclude='*.egg-info' \
        --exclude='__pycache__' \
        --exclude='.pytest_cache' \
        --exclude='research-graph.json' \
        --exclude='test_port_framework.py' \
        "$SOURCE_ROOT/$d/" "$DEST/$d/"
    fi
  done

  for f in "${FRAMEWORK_FILES[@]}"; do
    [[ -f "$SOURCE_ROOT/$f" ]] || { warn "源缺少文件，跳过: $f"; continue; }
    log "拷贝 $f"
    run mkdir -p "$(dirname "$DEST/$f")"
    run cp "$SOURCE_ROOT/$f" "$DEST/$f"
  done

  # 同步器和 .gitignore 是目标侧文件：绝不从只读源覆盖。
  # migrate 新项目时，从当前执行的控制器复制一份；sync 时保留目标现有版本。
  if [[ "$SCRIPT_PATH" != "$DEST/scripts/port-framework.sh" ]]; then
    log "安装目标侧 scripts/port-framework.sh"
    run mkdir -p "$DEST/scripts"
    run cp "$SCRIPT_PATH" "$DEST/scripts/port-framework.sh"
    run chmod +x "$DEST/scripts/port-framework.sh"
  else
    log "保留目标侧 scripts/port-framework.sh"
  fi
  if [[ ! -e "$DEST/.gitignore" && -f "$CONTROLLER_ROOT/.gitignore" ]]; then
    log "初始化目标侧 .gitignore"
    run cp "$CONTROLLER_ROOT/.gitignore" "$DEST/.gitignore"
  else
    log "保留目标侧 .gitignore"
  fi
}

# ---------- 替换研究方案痕迹 ----------
# 从源仓库默认痕迹 → 目标项目配置；并做通用化清理（P1-E 举例等）
apply_substitutions() {
  log "应用项目化替换 (project_id=$PROJECT_ID, server_root=$SERVER_ROOT)"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    log "[dry-run] 跳过文本替换"
    return
  fi
  PORT_DEST="$DEST" \
  PORT_PROJECT_ID="$PROJECT_ID" \
  PORT_TITLE="$TITLE" \
  PORT_SERVER_ROOT="$SERVER_ROOT" \
  PORT_GITHUB_URL="$GITHUB_URL" \
  PORT_HYPOTHESIS_FILE="$HYPOTHESIS_FILE" \
  PORT_SRC_PROJECT_ID="$SRC_PROJECT_ID" \
  PORT_SRC_TITLE="$SRC_TITLE" \
  PORT_SRC_SERVER_ROOT="$SRC_SERVER_ROOT" \
  PORT_SRC_GITHUB_URL="$SRC_GITHUB_URL" \
  PORT_SRC_REPO_NAME="$SRC_REPO_NAME" \
  PORT_SRC_HYPOTHESIS_FILE="$SRC_HYPOTHESIS_FILE" \
  python3 <<'PY'
import os, pathlib, re

root = pathlib.Path(os.environ["PORT_DEST"])
project_id = os.environ["PORT_PROJECT_ID"]
title = os.environ["PORT_TITLE"]
server_root = os.environ["PORT_SERVER_ROOT"]
github_url = os.environ["PORT_GITHUB_URL"]
hypothesis = os.environ["PORT_HYPOTHESIS_FILE"]

src_project_id = os.environ["PORT_SRC_PROJECT_ID"]
src_title = os.environ["PORT_SRC_TITLE"]
src_server_root = os.environ["PORT_SRC_SERVER_ROOT"]
src_github_url = os.environ["PORT_SRC_GITHUB_URL"]
src_repo_name = os.environ["PORT_SRC_REPO_NAME"]
src_hypothesis = os.environ["PORT_SRC_HYPOTHESIS_FILE"]

text_globs = [
    "AGENTS.md", "README.md", "SUBMISSION_CHECKLIST.md", "autoresearcher.md",
    "orchestration/**/*.json", "orchestration/**/*.md",
    "rules/**/*.md", "workflow/**/*.md",
]

replacements = [
    (src_server_root, server_root),
    (src_project_id, project_id),
    (src_hypothesis, hypothesis),
    (src_github_url, github_url),
    (src_repo_name, project_id),
    (src_title, title),
    # 标题在 git-workflow 里有时写成缩短版「分化—纠缠—几何」
    ("分化—纠缠—几何", title),
    ("jobs/P1-Ex/result.json", "jobs/<exp_id>/result.json"),
    ("`jobs/*/workspace/`", "`research/jobs/*/workspace/`"),
    ("experiment(P1-E0): pass — Page calibration",
     "experiment(<exp_id>): pass — <summary>"),
]

specific_schematic = (
    "- Draw a schematic (TikZ or vector figure) for each core mechanism/theorem:\n"
    "  the optimal decomposition `M+N`, the zero-sum subspace `N`, the snake\n"
    "  arrangement, and double centering must be illustrated, not only stated as\n"
    "  formulas."
)
generic_schematic = (
    "- Draw a schematic (TikZ or vector figure) for each core mechanism/theorem,\n"
    "  so the key structure is illustrated, not only stated as formulas."
)

agents_pat = re.compile(
    r"当前研究方案：\*\*.*?\*\*（`project_id = .*?`）。"
)
agents_repl = f"当前研究方案：**{title}**（`project_id = {project_id}`）。"

git_repo_pat = re.compile(
    r"- 仓库名 `[^`]+` 与研究核心.*?`project_id = [^`]+`。"
)
git_repo_repl = (
    f"- 仓库名 `{project_id}` 与研究核心对应，`project_id = {project_id}`。"
)

changed = []
for pattern in text_globs:
    for path in root.glob(pattern):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        orig = text
        for a, b in replacements:
            if a and a in text:
                text = text.replace(a, b)
        if specific_schematic in text:
            text = text.replace(specific_schematic, generic_schematic)
        text2 = agents_pat.sub(agents_repl, text)
        text2 = git_repo_pat.sub(git_repo_repl, text2)
        text2 = re.sub(
            r"(\*\*项目\*\*:\s*)\S+",
            rf"\1{project_id}",
            text2,
            count=1,
        )
        if path.name == "research-graph.example.json":
            text2 = re.sub(
                r'"project_id"\s*:\s*"[^"]*"',
                f'"project_id": "{project_id}"',
                text2,
                count=1,
            )
        if text2 != orig:
            path.write_text(text2, encoding="utf-8")
            changed.append(str(path.relative_to(root)))

print(f"updated {len(changed)} files")
for p in changed:
    print(f"  - {p}")
PY
}

# ---------- research/ 脚手架 ----------
scaffold_research() {
  if [[ "$SCAFFOLD" -ne 1 ]]; then
    log "跳过 research/ 脚手架 (--no-scaffold)"
    return
  fi
  if [[ -e "$DEST/research/project.json" ]]; then
    log "research/ 已存在，保留不覆盖"
    return
  fi
  log "创建 research/ 空脚手架"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    log "[dry-run] mkdir research/{src/experiments,jobs,orchestration/reviews,paper/{comprehensive,nature,prl},versions,notes,plans}"
    return
  fi
  mkdir -p \
    "$DEST/research/src/experiments" \
    "$DEST/research/jobs" \
    "$DEST/research/orchestration/reviews" \
    "$DEST/research/paper/comprehensive" \
    "$DEST/research/paper/nature" \
    "$DEST/research/paper/prl" \
    "$DEST/research/versions" \
    "$DEST/research/notes" \
    "$DEST/research/plans"

  # .gitkeep 让空目录可被 git 追踪
  for d in \
    research/src/experiments \
    research/jobs \
    research/orchestration/reviews \
    research/paper/comprehensive \
    research/paper/nature \
    research/paper/prl \
    research/versions \
    research/notes \
    research/plans
  do
    : > "$DEST/$d/.gitkeep"
  done

  PORT_PROJECT_JSON="$DEST/research/project.json" \
  PORT_PROJECT_ID="$PROJECT_ID" \
  PORT_TITLE="$TITLE" \
  PORT_HYPOTHESIS_FILE="$HYPOTHESIS_FILE" \
  python3 <<'PY'
import json
import os
from pathlib import Path

data = {
    "project_id": os.environ["PORT_PROJECT_ID"],
    "title": os.environ["PORT_TITLE"],
    "hypothesis_file": os.environ["PORT_HYPOTHESIS_FILE"],
    "question_file": "research/question.md",
    "layout": "flat-single-plan",
    "status": "planning",
    "max_cycles": 5,
    "budget": {
        "token_budget": None,
        "gpu_hours": None,
        "notes": "Budget limits are set by the human before high-cost runs.",
    },
    "autonomy": {"require_initial_plan_approval": False},
}
Path(os.environ["PORT_PROJECT_JSON"]).write_text(
    json.dumps(data, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
PY

  cat > "$DEST/research/state.md" <<EOF
# Research state

\`\`\`
current_stage = PLAN
cycle = 1
replan_from =
\`\`\`

This file is a human-readable stage summary for the single research plan under
\`research/\`. Orchestrator truth lives in \`.autoresearcher/orchestrator/state.json\`
and must not be overwritten from here.
EOF

  cat > "$DEST/research/question.md" <<EOF
# 研究问题：$TITLE

## 来源

本问题收缩自 [\`$(basename "$HYPOTHESIS_FILE")\`](./$(basename "$HYPOTHESIS_FILE"))。

## 核心问题

（待填写：把研究纲领压成可形式化、可数值模拟、可证伪的最小问题。）

## 成功判据

（待填写。）
EOF

  local hyp_path="$DEST/$HYPOTHESIS_FILE"
  mkdir -p "$(dirname "$hyp_path")"
  if [[ ! -f "$hyp_path" ]]; then
    cat > "$hyp_path" <<EOF
# $TITLE — 研究假说

（待填写：领域纲领、关键假设、可检验收缩路线。）
EOF
  fi

  log "已写入 research/project.json / question.md / state.md / $(basename "$HYPOTHESIS_FILE")"
}

# ---------- 安全检查 ----------
assert_not_source() {
  if [[ "$DEST" == "$SOURCE_ROOT" ]]; then
    die "目标不能是框架源仓库本身: $DEST"
  fi
}

assert_dest_ok_for_migrate() {
  assert_not_source
  [[ ! -e "$DEST" || -d "$DEST" ]] || die "目标已存在且不是目录: $DEST"
  if [[ -d "$DEST" ]] && [[ -n "$(find "$DEST" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]]; then
    if [[ "$FORCE" -ne 1 ]]; then
      die "目标目录非空；为避免覆盖已有项目已停止。确认后重试 --force: $DEST"
    fi
    warn "--force 已启用：将覆盖框架文件，但不删除 research/"
  fi
}

assert_dest_ok_for_sync() {
  assert_not_source
  [[ -f "$DEST/$PORT_CONFIG_NAME" ]] || die "目标缺少 $PORT_CONFIG_NAME，请先 migrate 或手动创建配置"
  [[ -d "$DEST/src/autoresearcher" ]] || die "目标不像已迁移的框架项目: $DEST"
}

# ---------- 命令 ----------
cmd_migrate() {
  defaults_from_dest_name
  validate_project_config
  [[ -n "$PROJECT_ID" && -n "$TITLE" && -n "$SERVER_ROOT" ]] || die "内部错误：缺少项目参数"
  assert_dest_ok_for_migrate
  log "migrate → project_id=$PROJECT_ID title=$TITLE"
  log "         server_root=$SERVER_ROOT"
  copy_framework
  apply_substitutions
  scaffold_research
  write_port_config
  log "完成。下一步："
  echo "  cd $DEST"
  echo "  python3 -m pip install -e ."
  echo "  python -m pytest -q"
  echo "  # 编辑 research/question.md 与 $HYPOTHESIS_FILE"
  echo "  # 需要时: git init && 配置双远程（见 rules/git-workflow.md）"
}

cmd_sync() {
  load_port_config || die "无法读取 $DEST/$PORT_CONFIG_NAME"
  defaults_from_dest_name
  validate_project_config
  SOURCE_ROOT="$(cd "$SOURCE_ROOT" && pwd)" || die "源仓库不存在: $SOURCE_ROOT"
  assert_dest_ok_for_sync
  if [[ "$SOURCE_ROOT" == "$DEST" ]]; then
    die "源与目标相同。请在 $PORT_CONFIG_NAME 中设置正确的 source，或传 --source"
  fi
  log "sync ← $SOURCE_ROOT"
  log "     → $DEST  (project_id=$PROJECT_ID)"
  # sync 绝不重建/覆盖 research 内容
  SCAFFOLD=0
  copy_framework
  apply_substitutions
  write_port_config
  log "同步完成（research/ 未改动）。"
}

cmd_status() {
  echo "SOURCE_ROOT=$SOURCE_ROOT"
  echo "DEST=$DEST"
  if [[ -f "$DEST/$PORT_CONFIG_NAME" ]]; then
    echo "--- $PORT_CONFIG_NAME ---"
    python3 -m json.tool "$DEST/$PORT_CONFIG_NAME"
  else
    echo "(无 $PORT_CONFIG_NAME — 尚未 migrate)"
  fi
  echo "--- 框架目录是否存在 ---"
  local d
  for d in "${FRAMEWORK_DIRS[@]}"; do
    if [[ -d "$DEST/$d" ]]; then echo "  OK  $d/"; else echo "  --  $d/"; fi
  done
  if [[ -d "$DEST/research" ]]; then echo "  OK  research/"; else echo "  --  research/"; fi
}

case "$CMD" in
  migrate) cmd_migrate ;;
  sync)    cmd_sync ;;
  status)  cmd_status ;;
esac
