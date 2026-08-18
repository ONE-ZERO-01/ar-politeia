"""Read-only research-journey timeline renderer.

This module aggregates the *research artifacts* — per-cycle ``plan.json``
(claims, experiments, revision pivots), ``findings.json`` (verdicts and
counter-evidence stories), ``strategy.json`` (decisions and rationale),
``iteration_summary.json`` (abandoned directions, lessons) and per-experiment
``jobs/<id>/result.json`` — into a self-contained HTML narrative: what was
attempted, what worked, what failed and why, and how the direction pivoted.

It is deliberately decoupled from the orchestrator: it never reads or mutates
scheduler state, and it never touches node prompts or contracts. The rendering
layer is isolated behind a plain ``dict`` data model (``build_research_timeline``)
so the HTML can later be swapped for another visualization without touching
the data path.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .graph import GraphError


_VERDICT_META = {
    "supported": ("supported", "证据支持"),
    "contradicted": ("contradicted", "被证据反驳"),
    "inconclusive": ("inconclusive", "证据不足"),
}

_CLAIM_TYPE_LABEL = {
    "core": "核心主张",
    "calibration": "校准",
    "method": "方法",
}

# result.json top-level fields that are metadata, not headline metrics.
_RESULT_META_KEYS = {
    "experiment", "description", "seed", "seeds", "timestamp", "figure",
    "pass", "schema_version", "error",
}
_MAX_METRICS = 8


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    """Best-effort JSON read; malformed or missing files simply yield None."""
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _fmt_number(value: Any) -> str:
    if isinstance(value, float):
        if value == 0:
            return "0"
        if abs(value) >= 1e4 or abs(value) < 1e-3:
            return f"{value:.3g}"
        return f"{value:.4g}"
    return str(value)


def _result_summary(result: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Extract headline info from one result.json without huge arrays."""
    if result is None:
        return {"exists": False, "passed": None, "description": None,
                "timestamp": None, "error": None, "metrics": {}}
    metrics: Dict[str, str] = {}
    for key, value in result.items():
        if key in _RESULT_META_KEYS:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            continue
        if isinstance(value, str) and len(value) > 60:
            continue
        metrics[key] = _fmt_number(value)
        if len(metrics) >= _MAX_METRICS:
            break
    passed = result.get("pass")
    return {
        "exists": True,
        "passed": passed if isinstance(passed, bool) else None,
        "description": result.get("description"),
        "timestamp": result.get("timestamp"),
        "error": result.get("error"),
        "metrics": metrics,
    }


def _experiment_status(summary: Dict[str, Any]) -> str:
    if not summary["exists"]:
        return "pending"
    if summary["passed"] is True:
        return "passed"
    if summary["passed"] is False or summary["error"]:
        return "failed"
    return "done"


_STATUS_LABEL = {
    "passed": "通过",
    "failed": "未通过",
    "done": "已完成",
    "pending": "未运行",
}


def _find_result_path(research_dir: Path, experiment: Dict[str, Any]) -> Optional[Path]:
    """Locate an experiment's result.json via declared artifacts, then by id."""
    for artifact in experiment.get("artifacts", []) or []:
        if isinstance(artifact, str) and artifact.endswith("result.json"):
            candidate = research_dir / artifact
            if candidate.is_file():
                return candidate
    exp_id = experiment.get("id", "")
    fallback = research_dir / "jobs" / exp_id / "result.json"
    return fallback if fallback.is_file() else None


def _load_reviews(reviews_dir: Path) -> List[Dict[str, Any]]:
    reviews: List[Dict[str, Any]] = []
    if not reviews_dir.is_dir():
        return reviews
    for path in sorted(reviews_dir.glob("*.json")):
        data = _read_json(path)
        if data is None:
            continue
        reviews.append({
            "name": path.stem,
            "verdict": data.get("verdict") or data.get("decision") or "—",
        })
    return reviews


def _load_iteration_summary(chapter_dir: Path) -> Optional[Dict[str, Any]]:
    for relative in ("iteration_summary.json", "orchestration/iteration_summary.json"):
        data = _read_json(chapter_dir / relative)
        if data is not None:
            return data
    return None


def _build_chapter(
    research_dir: Path,
    plan: Dict[str, Any],
    findings: Optional[Dict[str, Any]],
    strategy: Optional[Dict[str, Any]],
    iteration: Optional[Dict[str, Any]],
    reviews: List[Dict[str, Any]],
    *,
    is_current: bool,
) -> Dict[str, Any]:
    finding_map: Dict[str, Dict[str, Any]] = {}
    if findings:
        for item in findings.get("findings", []) or []:
            claim_id = item.get("claim_id")
            if isinstance(claim_id, str):
                finding_map[claim_id] = item

    claims: List[Dict[str, Any]] = []
    for claim in plan.get("claims", []) or []:
        claim_id = claim.get("id", "?")
        finding = finding_map.get(claim_id)
        verdict = "pending"
        verdict_label = "待验证"
        finding_summary = None
        note = None
        if finding:
            raw = str(finding.get("verdict", ""))
            verdict, verdict_label = _VERDICT_META.get(raw, ("pending", raw or "待验证"))
            finding_summary = finding.get("summary")
            note = finding.get("note")
        claim_type = str(claim.get("type", ""))
        claims.append({
            "id": claim_id,
            "text": claim.get("text", ""),
            "type": claim_type,
            "type_label": _CLAIM_TYPE_LABEL.get(claim_type, claim_type),
            "falsification": claim.get("falsification"),
            "experiments": claim.get("experiments", []) or [],
            "verdict": verdict,
            "verdict_label": verdict_label,
            "finding_summary": finding_summary,
            "note": note,
        })

    experiments: List[Dict[str, Any]] = []
    for experiment in plan.get("experiments", []) or []:
        result_path = _find_result_path(research_dir, experiment)
        summary = _result_summary(_read_json(result_path) if result_path else None)
        status = _experiment_status(summary)
        experiments.append({
            "id": experiment.get("id", "?"),
            "claim_ids": experiment.get("claim_ids", []) or [],
            "objective": experiment.get("objective", ""),
            "priority": experiment.get("priority"),
            "status": status,
            "status_label": _STATUS_LABEL[status],
            "description": summary["description"],
            "timestamp": summary["timestamp"],
            "error": summary["error"],
            "metrics": summary["metrics"],
            "failure_policy": experiment.get("failure_policy") if status != "passed" else None,
        })

    revision = plan.get("revision")
    revision_block = None
    if isinstance(revision, dict) and revision.get("reason"):
        revision_block = {
            "reason": revision.get("reason", ""),
            "retired_claims": revision.get("retired_claims", []) or [],
            "new_claims": revision.get("new_claims", []) or [],
        }

    strategy_block = None
    if isinstance(strategy, dict) and strategy.get("action"):
        strategy_block = {
            "action": strategy.get("action"),
            "rationale": strategy.get("rationale", ""),
            "unresolved_items": strategy.get("unresolved_items", []) or [],
        }

    abandoned: List[Dict[str, Any]] = []
    lessons: List[Dict[str, Any]] = []
    if iteration:
        for item in iteration.get("abandoned_directions", []) or []:
            if isinstance(item, dict):
                abandoned.append({
                    "direction": item.get("direction", ""),
                    "reason": item.get("reason", ""),
                })
        for item in iteration.get("core_lessons", []) or []:
            if isinstance(item, dict):
                lessons.append({
                    "id": item.get("id", ""),
                    "severity": item.get("severity", ""),
                    "lesson": item.get("lesson", ""),
                    "rule": item.get("rule", ""),
                })

    return {
        "cycle": plan.get("cycle"),
        "is_current": is_current,
        "status": plan.get("status", ""),
        "summary": plan.get("summary", ""),
        "question": plan.get("question", ""),
        "revision": revision_block,
        "strategy": strategy_block,
        "reviews": reviews,
        "abandoned": abandoned,
        "lessons": lessons,
        "claims": claims,
        "experiments": experiments,
    }


def _build_story(chapters: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Flatten chapters into a narrative event stream for the story view.

    Each entry answers one of: what was attempted, which hypothesis was
    tested, what the outcome was, and why it failed / pivoted.

    Carried-forward claims that bring nothing new (same claim id with the
    same verdict as an earlier cycle, or re-listed without fresh evidence)
    are skipped so the story only tells new developments; wording drift in
    carried-forward texts must not resurface old news.
    """
    story: List[Dict[str, Any]] = []
    told_verdicts: Dict[str, set] = {}
    for chapter in chapters:
        story.append({
            "kind": "cycle",
            "cycle": chapter["cycle"],
            "is_current": chapter["is_current"],
            "status": chapter["status"],
            "question": chapter["question"],
        })
        if chapter["revision"]:
            story.append({
                "kind": "pivot",
                "cycle": chapter["cycle"],
                "reason": chapter["revision"]["reason"],
                "retired": chapter["revision"]["retired_claims"],
                "fresh": chapter["revision"]["new_claims"],
            })
        experiment_map = {
            experiment["id"]: experiment for experiment in chapter["experiments"]
        }
        for claim in chapter["claims"]:
            seen = told_verdicts.setdefault(claim["id"], set())
            if claim["verdict"] in seen:
                continue
            if claim["verdict"] == "pending" and seen:
                continue
            seen.add(claim["verdict"])
            experiments = []
            for exp_id in claim["experiments"]:
                experiment = experiment_map.get(exp_id)
                experiments.append({
                    "id": exp_id,
                    "status": experiment["status"] if experiment else "pending",
                    "status_label": (
                        experiment["status_label"] if experiment else "未运行"
                    ),
                    "objective": experiment["objective"] if experiment else "",
                })
            story.append({
                "kind": "attempt",
                "cycle": chapter["cycle"],
                "claim_id": claim["id"],
                "verdict": claim["verdict"],
                "verdict_label": claim["verdict_label"],
                "hypothesis": claim["text"],
                "experiments": experiments,
                "outcome": claim["finding_summary"],
                "twist": claim["note"],
            })
        for item in chapter["abandoned"]:
            story.append({
                "kind": "abandoned",
                "cycle": chapter["cycle"],
                "direction": item["direction"],
                "reason": item["reason"],
            })
        if chapter["strategy"]:
            story.append({
                "kind": "decision",
                "cycle": chapter["cycle"],
                "action": chapter["strategy"]["action"],
                "rationale": chapter["strategy"]["rationale"],
            })
    return story


def build_research_timeline(research_dir: Path) -> Dict[str, Any]:
    """Assemble the research journey from artifacts under ``research_dir``."""
    research_dir = research_dir.expanduser().resolve()
    current_plan = _read_json(research_dir / "plan.json")
    if current_plan is None:
        raise GraphError(f"no readable plan.json under {research_dir}")

    chapters: List[Dict[str, Any]] = []
    versions_dir = research_dir / "versions"
    if versions_dir.is_dir():
        cycle_dirs = []
        for path in versions_dir.iterdir():
            match = re.fullmatch(r"cycle-(\d+)", path.name)
            if match and path.is_dir():
                cycle_dirs.append((int(match.group(1)), path))
        for _, chapter_dir in sorted(cycle_dirs):
            plan = _read_json(chapter_dir / "plan.json")
            if plan is None:
                continue
            chapters.append(_build_chapter(
                research_dir,
                plan,
                _read_json(chapter_dir / "findings.json"),
                _read_json(chapter_dir / "orchestration" / "strategy.json"),
                _load_iteration_summary(chapter_dir),
                _load_reviews(chapter_dir / "reviews"),
                is_current=False,
            ))

    archived_cycles = {chapter["cycle"] for chapter in chapters}
    if current_plan.get("cycle") not in archived_cycles:
        # A freshly planned cycle may sit next to stale artifacts from the
        # previous cycle; only attach evidence files that match this cycle.
        current_cycle = current_plan.get("cycle")
        findings = _read_json(research_dir / "findings.json")
        if findings is not None and findings.get("cycle") != current_cycle:
            findings = None
        freshly_planned = str(current_plan.get("status", "")) == "planned"
        strategy = None if freshly_planned else _read_json(
            research_dir / "orchestration" / "strategy.json"
        )
        iteration = _load_iteration_summary(research_dir)
        if iteration is not None and iteration.get("cycle") not in (None, current_cycle):
            iteration = None
        reviews = [] if freshly_planned else _load_reviews(
            research_dir / "orchestration" / "reviews"
        )
        chapters.append(_build_chapter(
            research_dir,
            current_plan,
            findings,
            strategy,
            iteration,
            reviews,
            is_current=True,
        ))

    all_claims = [claim for chapter in chapters for claim in chapter["claims"]]
    all_experiments = [
        experiment for chapter in chapters for experiment in chapter["experiments"]
    ]
    verdict_counts = {"supported": 0, "contradicted": 0, "inconclusive": 0, "pending": 0}
    for claim in all_claims:
        verdict_counts[claim["verdict"]] = verdict_counts.get(claim["verdict"], 0) + 1
    experiment_counts = {"passed": 0, "failed": 0, "done": 0, "pending": 0}
    for experiment in all_experiments:
        experiment_counts[experiment["status"]] += 1

    return {
        "project_id": current_plan.get("project_id", ""),
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "current_cycle": current_plan.get("cycle"),
        "current_status": current_plan.get("status", ""),
        "question": current_plan.get("question", ""),
        "summary": {
            "cycles": len(chapters),
            "claims": verdict_counts,
            "claims_total": len(all_claims),
            "experiments": experiment_counts,
            "experiments_total": len(all_experiments),
            "abandoned": sum(len(chapter["abandoned"]) for chapter in chapters),
            "lessons": sum(len(chapter["lessons"]) for chapter in chapters),
        },
        "story": _build_story(chapters),
        "chapters": chapters,
    }


def render_html(timeline: Dict[str, Any]) -> str:
    """Render a self-contained HTML document from the data model."""
    payload = json.dumps(timeline, ensure_ascii=False, sort_keys=True)
    payload = payload.replace("<", "\\u003c")
    return _HTML_TEMPLATE.replace("__TIMELINE_DATA__", payload)


def write_timeline(research_dir: Path, *, output: Optional[Path] = None) -> Path:
    """Build and write the research-journey HTML, returning the output path."""
    timeline = build_research_timeline(research_dir)
    html = render_html(timeline)
    target = (
        output.expanduser().resolve()
        if output
        else research_dir.expanduser().resolve() / "timeline.html"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(html, encoding="utf-8")
    return target


_HTML_TEMPLATE = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>研究历程 · AutoResearcher</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f3f6fb;
      --surface: #ffffff;
      --surface-2: #f8fafc;
      --text: #132238;
      --muted: #607089;
      --border: #d9e1ec;
      --ok: #1e8449;
      --ok-soft: #e7f6ec;
      --bad: #c0392b;
      --bad-soft: #fdecea;
      --warn: #c17a18;
      --warn-soft: #fff7e8;
      --info: #4667d9;
      --info-soft: #eef2ff;
      --pivot: #7a4db4;
      --pivot-soft: #f6efff;
      --neutral: #8796aa;
      --neutral-soft: #eef1f5;
      --shadow: 0 10px 30px rgba(34, 53, 84, 0.08);
    }
    @media (prefers-color-scheme: dark) {
      :root {
        color-scheme: dark;
        --bg: #0e1521;
        --surface: #151f2d;
        --surface-2: #111a27;
        --text: #e9eff8;
        --muted: #a3b0c1;
        --border: #2b3a4e;
        --ok: #5fd08a;
        --ok-soft: #16281d;
        --bad: #f08383;
        --bad-soft: #402425;
        --warn: #f1b457;
        --warn-soft: #3a2c18;
        --info: #86a0ff;
        --info-soft: #202d52;
        --pivot: #c39aee;
        --pivot-soft: #342548;
        --neutral: #60728a;
        --neutral-soft: #1e2836;
        --shadow: 0 12px 36px rgba(0, 0, 0, 0.24);
      }
    }

    * { box-sizing: border-box; }
    body {
      margin: 0;
      background:
        radial-gradient(circle at 12% 0%, color-mix(in srgb, var(--info) 8%, transparent), transparent 26rem),
        radial-gradient(circle at 90% 0%, color-mix(in srgb, var(--pivot) 8%, transparent), transparent 28rem),
        var(--bg);
      color: var(--text);
      font-family: Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      line-height: 1.6;
    }
    .page { width: min(1080px, calc(100% - 32px)); margin: 0 auto; padding: 34px 0 72px; }

    h1 { margin: 0 0 6px; font-size: clamp(24px, 3vw, 36px); font-weight: 650; letter-spacing: -0.02em; }
    .project-id { color: var(--muted); font-size: 13px; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
    .question {
      margin: 14px 0 0;
      padding: 14px 18px;
      border: 1px solid color-mix(in srgb, var(--info) 30%, var(--border));
      border-left: 4px solid var(--info);
      border-radius: 12px;
      background: var(--info-soft);
      font-size: 14px;
    }
    .question b { display: block; margin-bottom: 4px; font-size: 12px; color: var(--info); letter-spacing: 0.05em; }

    .summary-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin: 18px 0 30px; }
    .summary-card {
      padding: 14px 16px;
      border: 1px solid var(--border);
      border-radius: 14px;
      background: color-mix(in srgb, var(--surface) 94%, transparent);
      box-shadow: var(--shadow);
    }
    .summary-label { display: block; margin-bottom: 5px; color: var(--muted); font-size: 12px; }
    .summary-value { font-size: 22px; font-weight: 650; font-variant-numeric: tabular-nums; }
    .summary-note { display: block; margin-top: 2px; color: var(--muted); font-size: 12px; }
    .summary-value .neg { color: var(--bad); }

    /* ── 章节（cycle）───────────────────── */
    .journey { position: relative; }
    .journey::before {
      content: ""; position: absolute; left: 13px; top: 8px; bottom: 8px; width: 2px;
      background: linear-gradient(var(--border), color-mix(in srgb, var(--pivot) 40%, var(--border)));
    }
    .chapter { position: relative; padding: 0 0 34px 44px; }
    .chapter-marker {
      position: absolute; left: 0; top: 2px; width: 28px; height: 28px;
      display: grid; place-items: center;
      border-radius: 50%;
      background: var(--pivot);
      color: #fff;
      font-size: 13px; font-weight: 700;
      box-shadow: 0 0 0 4px color-mix(in srgb, var(--pivot) 20%, transparent);
    }
    .chapter.current .chapter-marker { background: var(--info); box-shadow: 0 0 0 4px color-mix(in srgb, var(--info) 22%, transparent); }

    .chapter-head { display: flex; flex-wrap: wrap; gap: 8px 12px; align-items: baseline; margin-bottom: 4px; }
    .chapter-title { font-size: 19px; font-weight: 650; }
    .chip {
      display: inline-flex; align-items: center; gap: 5px;
      padding: 3px 10px; border-radius: 999px;
      border: 1px solid var(--border);
      background: var(--surface-2);
      font-size: 12px; color: var(--muted);
      white-space: nowrap;
    }
    .chip.ok { color: var(--ok); border-color: color-mix(in srgb, var(--ok) 40%, var(--border)); background: var(--ok-soft); }
    .chip.bad { color: var(--bad); border-color: color-mix(in srgb, var(--bad) 40%, var(--border)); background: var(--bad-soft); }
    .chip.warn { color: var(--warn); border-color: color-mix(in srgb, var(--warn) 40%, var(--border)); background: var(--warn-soft); }
    .chip.info { color: var(--info); border-color: color-mix(in srgb, var(--info) 40%, var(--border)); background: var(--info-soft); }
    .chip.pivot { color: var(--pivot); border-color: color-mix(in srgb, var(--pivot) 40%, var(--border)); background: var(--pivot-soft); }

    .chapter-summary { margin: 6px 0 14px; color: var(--muted); font-size: 13.5px; }

    .block {
      margin: 0 0 14px;
      border: 1px solid var(--border);
      border-radius: 14px;
      background: var(--surface);
      box-shadow: var(--shadow);
      overflow: hidden;
    }
    .block-head {
      display: flex; align-items: baseline; gap: 10px;
      padding: 11px 16px;
      border-bottom: 1px solid var(--border);
      background: var(--surface-2);
      font-size: 13px; font-weight: 650;
    }
    .block-head .count { color: var(--muted); font-weight: 400; font-size: 12px; }
    .block-body { padding: 8px 16px 14px; }

    /* 转向 / 放弃方向 —— 失败叙事重点 */
    .pivot-block { border-left: 4px solid var(--pivot); }
    .pivot-block .block-head { color: var(--pivot); }
    .abandon-block { border-left: 4px solid var(--bad); }
    .abandon-block .block-head { color: var(--bad); }
    .pivot-reason { margin: 10px 0 4px; font-size: 13.5px; }
    .tag-list { display: flex; flex-wrap: wrap; gap: 6px; margin: 8px 0 2px; }
    .tag { padding: 3px 9px; border-radius: 8px; font-size: 12px; border: 1px solid var(--border); background: var(--surface-2); }
    .tag.retired { color: var(--bad); background: var(--bad-soft); border-color: color-mix(in srgb, var(--bad) 30%, var(--border)); text-decoration: line-through; }
    .tag.fresh { color: var(--ok); background: var(--ok-soft); border-color: color-mix(in srgb, var(--ok) 30%, var(--border)); }
    .tag-label { font-size: 12px; color: var(--muted); margin-top: 8px; display: block; }

    .abandon-item { margin: 10px 0; padding: 10px 13px; border-radius: 10px; background: var(--bad-soft); border: 1px solid color-mix(in srgb, var(--bad) 22%, var(--border)); }
    .abandon-item .dir { font-size: 13.5px; font-weight: 650; }
    .abandon-item .why { margin-top: 4px; font-size: 13px; color: var(--muted); }
    .abandon-item .why b { color: var(--bad); }

    /* 主张卡 */
    .claim { margin: 12px 0; padding: 12px 14px; border: 1px solid var(--border); border-radius: 12px; background: var(--surface-2); }
    .claim-head { display: flex; flex-wrap: wrap; gap: 6px 10px; align-items: center; }
    .claim-id { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12.5px; font-weight: 700; }
    .verdict { padding: 2px 9px; border-radius: 999px; font-size: 12px; font-weight: 650; }
    .verdict.supported { color: var(--ok); background: var(--ok-soft); }
    .verdict.contradicted { color: var(--bad); background: var(--bad-soft); }
    .verdict.inconclusive { color: var(--warn); background: var(--warn-soft); }
    .verdict.pending { color: var(--muted); background: var(--neutral-soft); }
    .claim-text { margin: 7px 0 0; font-size: 13.5px; }
    .claim-finding { margin: 8px 0 0; padding: 9px 12px; border-radius: 9px; background: color-mix(in srgb, var(--ok-soft) 60%, var(--surface)); font-size: 13px; }
    .claim.contradicted .claim-finding { background: color-mix(in srgb, var(--bad-soft) 60%, var(--surface)); }
    .claim-note {
      margin: 8px 0 0; padding: 9px 12px;
      border-left: 3px solid var(--warn);
      border-radius: 0 9px 9px 0;
      background: var(--warn-soft);
      font-size: 13px;
    }
    .claim-note b { color: var(--warn); }

    /* 实验卡 */
    .exp-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 10px; margin-top: 10px; }
    .exp {
      padding: 11px 13px;
      border: 1px solid var(--border);
      border-left: 3px solid var(--neutral);
      border-radius: 11px;
      background: var(--surface-2);
    }
    .exp.passed { border-left-color: var(--ok); }
    .exp.failed { border-left-color: var(--bad); }
    .exp.pending { border-left-color: var(--neutral); opacity: 0.85; }
    .exp-head { display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; }
    .exp-id { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-weight: 700; font-size: 13px; }
    .exp-status { margin-left: auto; font-size: 12px; font-weight: 650; }
    .exp.passed .exp-status { color: var(--ok); }
    .exp.failed .exp-status { color: var(--bad); }
    .exp.pending .exp-status, .exp.done .exp-status { color: var(--muted); }
    .exp-objective { margin: 6px 0 0; font-size: 12.5px; color: var(--muted); }
    .exp-error { margin: 7px 0 0; padding: 7px 10px; border-radius: 8px; background: var(--bad-soft); color: var(--bad); font-size: 12.5px; }
    .exp-fallback { margin: 7px 0 0; padding: 7px 10px; border-radius: 8px; background: var(--warn-soft); font-size: 12px; }
    .exp-fallback b { color: var(--warn); }
    .exp-metrics { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 8px; }
    .metric { padding: 2px 8px; border-radius: 7px; background: var(--surface); border: 1px solid var(--border); font-size: 11.5px; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; color: var(--muted); }

    /* 决策 / 审稿 / 教训 */
    .decision { font-size: 13.5px; }
    .decision-action { font-weight: 700; }
    .decision-action.continue { color: var(--ok); }
    .decision-action.replan, .decision-action.revise { color: var(--pivot); }
    details { margin-top: 8px; }
    summary { cursor: pointer; font-size: 12.5px; color: var(--info); user-select: none; }
    details > div { margin-top: 8px; font-size: 13px; color: var(--muted); }
    .unresolved li { margin: 4px 0; font-size: 12.5px; color: var(--muted); }

    .review-chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }

    .lesson { margin: 9px 0; padding: 9px 12px; border-radius: 9px; background: var(--surface-2); border: 1px solid var(--border); font-size: 12.5px; }
    .lesson .sev { font-weight: 700; margin-right: 6px; }
    .lesson .sev.P0 { color: var(--bad); }
    .lesson .sev.P1 { color: var(--warn); }
    .lesson .sev.P2, .lesson .sev.P3 { color: var(--muted); }
    .lesson .rule { display: block; margin-top: 4px; color: var(--muted); }
    .lesson .rule b { color: var(--text); }

    .footer-note { margin-top: 18px; color: var(--muted); font-size: 12px; text-align: center; }

    /* ── 研究故事线（中轴交错时间线）───────────────── */
    .section-title { margin: 30px 0 16px; font-size: 17px; font-weight: 650; }
    .section-title small { margin-left: 8px; color: var(--muted); font-weight: 400; font-size: 12.5px; }

    .story-track { position: relative; padding: 6px 0 24px; }
    .story-track::before {
      content: ""; position: absolute; left: 50%; top: 0; bottom: 0; width: 2px;
      transform: translateX(-50%);
      background: linear-gradient(
        color-mix(in srgb, var(--info) 45%, var(--border)),
        color-mix(in srgb, var(--pivot) 45%, var(--border)));
    }
    .story-item { position: relative; width: calc(50% - 36px); margin: 0 0 18px; }
    .story-item.left { margin-right: auto; }
    .story-item.right { margin-left: auto; }
    .story-item::after {
      content: ""; position: absolute; top: 24px; width: 24px; height: 2px;
      background: var(--border);
    }
    .story-item.left::after { right: -25px; }
    .story-item.right::after { left: -25px; }
    .story-dot {
      position: absolute; top: 18px; width: 14px; height: 14px; border-radius: 50%;
      background: var(--neutral);
      box-shadow: 0 0 0 3px var(--bg), 0 0 0 6px color-mix(in srgb, var(--neutral) 22%, transparent);
      z-index: 1;
    }
    .story-item.left .story-dot { right: -43px; }
    .story-item.right .story-dot { left: -43px; }
    .story-dot.supported { background: var(--ok); box-shadow: 0 0 0 3px var(--bg), 0 0 0 6px color-mix(in srgb, var(--ok) 25%, transparent); }
    .story-dot.contradicted, .story-dot.abandoned { background: var(--bad); box-shadow: 0 0 0 3px var(--bg), 0 0 0 6px color-mix(in srgb, var(--bad) 25%, transparent); }
    .story-dot.inconclusive { background: var(--warn); box-shadow: 0 0 0 3px var(--bg), 0 0 0 6px color-mix(in srgb, var(--warn) 25%, transparent); }
    .story-dot.pivot { background: var(--pivot); border-radius: 4px; box-shadow: 0 0 0 3px var(--bg), 0 0 0 6px color-mix(in srgb, var(--pivot) 25%, transparent); }
    .story-dot.abandoned { border-radius: 4px; }
    .story-dot.decision { background: var(--info); box-shadow: 0 0 0 3px var(--bg), 0 0 0 6px color-mix(in srgb, var(--info) 25%, transparent); }

    .story-milestone { display: flex; justify-content: center; margin: 4px 0 22px; position: relative; z-index: 1; }
    .story-milestone-inner {
      max-width: 76%; text-align: center; padding: 10px 22px;
      border: 1px solid color-mix(in srgb, var(--info) 35%, var(--border));
      border-radius: 16px; background: var(--info-soft); box-shadow: var(--shadow);
      font-size: 13px;
    }
    .story-milestone-inner b { font-size: 14.5px; }
    .story-milestone-inner .milestone-q { margin-top: 3px; color: var(--muted); font-size: 12.5px; }

    .story-card {
      border: 1px solid var(--border); border-top: 3px solid var(--neutral);
      border-radius: 14px; background: var(--surface); box-shadow: var(--shadow);
      padding: 12px 15px 13px; cursor: pointer;
    }
    .story-card.tone-ok { border-top-color: var(--ok); }
    .story-card.tone-bad { border-top-color: var(--bad); }
    .story-card.tone-warn { border-top-color: var(--warn); }
    .story-card.tone-pivot { border-top-color: var(--pivot); }
    .story-card.tone-info { border-top-color: var(--info); }
    .story-head { display: flex; flex-wrap: wrap; align-items: center; gap: 7px; margin-bottom: 4px; }
    .story-kind { font-size: 11px; font-weight: 700; letter-spacing: 0.08em; color: var(--muted); }
    .srow { display: grid; grid-template-columns: 40px 1fr; gap: 9px; margin: 8px 0 0; font-size: 13px; }
    .slabel { padding-top: 2px; font-size: 11px; font-weight: 700; letter-spacing: 0.06em; color: var(--muted); }
    .srow.twist .slabel { color: var(--warn); }
    .srow.fail .slabel { color: var(--bad); }
    .srow.twist .stext { padding: 6px 10px; border-left: 3px solid var(--warn); border-radius: 0 8px 8px 0; background: var(--warn-soft); }
    .srow.fail .stext { padding: 6px 10px; border-left: 3px solid var(--bad); border-radius: 0 8px 8px 0; background: var(--bad-soft); }
    .stext.pending-text { color: var(--muted); font-style: italic; }
    .exp-chips { display: flex; flex-wrap: wrap; gap: 5px; }
    .clamp { display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
    .story-card.expanded .clamp { display: block; -webkit-line-clamp: unset; overflow: visible; }
    .expand-hint { margin-top: 8px; font-size: 11px; color: var(--info); }
    .story-card.expanded .expand-hint .when-closed { display: none; }
    .story-card:not(.expanded) .expand-hint .when-open { display: none; }

    @media (max-width: 860px) {
      .story-track::before { left: 13px; transform: none; }
      .story-item { width: auto; margin-left: 40px; }
      .story-item.left { margin-right: 0; }
      .story-item.left .story-dot, .story-item.right .story-dot { left: -33px; right: auto; }
      .story-item.left::after, .story-item.right::after { left: -19px; right: auto; width: 14px; }
      .story-milestone { justify-content: flex-start; margin-left: 40px; }
      .story-milestone-inner { max-width: none; text-align: left; }
    }

    @media (max-width: 760px) {
      .summary-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .exp-grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <main class="page">
    <header>
      <h1>研究历程</h1>
      <div class="project-id" id="project-id"></div>
      <div class="question" id="question"><b>当前研究问题</b><span id="question-text"></span></div>
      <section class="summary-grid" id="summary"></section>
    </header>
    <h2 class="section-title">研究故事线<small>每张卡片 = 一次尝试：假设 → 验证 → 结果 → 转折 · 点击卡片展开全文</small></h2>
    <section class="story-track" id="story"></section>
    <h2 class="section-title">分轮详细档案<small>主张判定 · 实验明细 · 审稿 · 决策 · 经验教训</small></h2>
    <section class="journey" id="journey"></section>
    <p class="footer-note" id="footer-note"></p>
  </main>

  <script>
    window.__TIMELINE__ = __TIMELINE_DATA__;
  </script>
  <script>
    (() => {
      const data = window.__TIMELINE__;

      const esc = (value) => String(value ?? "")
        .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;");

      document.getElementById("project-id").textContent =
        `${data.project_id} · 当前第 ${data.current_cycle} 轮（${data.current_status}） · 生成于 ${new Date(data.generated_at).toLocaleString("zh-CN", { hour12: false })}`;
      document.getElementById("question-text").textContent = data.question;

      const s = data.summary;
      document.getElementById("summary").innerHTML = [
        { label: "研究轮次", value: String(s.cycles), note: "cycle（含当前）" },
        { label: "研究主张", value: `${s.claims.supported}<span class="neg">${s.claims.contradicted ? " / " + s.claims.contradicted : ""}</span> / ${s.claims_total}`,
          note: `支持${s.claims.contradicted ? " / 被反驳" : ""} / 总数 · 待验证 ${s.claims.pending}` },
        { label: "数值实验", value: `${s.experiments.passed + s.experiments.done} / ${s.experiments_total}`,
          note: `完成 / 总数 · 未通过 ${s.experiments.failed} · 未运行 ${s.experiments.pending}` },
        { label: "转折与教训", value: `${s.abandoned} + ${s.lessons}`, note: "放弃的方向 + 记录的教训" },
      ].map((card) => `
        <div class="summary-card">
          <span class="summary-label">${card.label}</span>
          <span class="summary-value">${card.value}</span>
          <span class="summary-note">${card.note}</span>
        </div>`).join("");

      const ACTION_LABEL = {
        continue: "continue · 证据许可，进入收尾/审计",
        replan: "replan · 回到计划，补实验或换方向",
        revise: "revise · 保留证据，修改论文叙事",
        request_human: "request_human · 请求人工决策",
        stop_request: "stop_request · 建议停止",
      };

      // ── 研究故事线 ─────────────────────────────
      const EXP_CHIP_CLASS = { passed: "ok", failed: "bad", pending: "", done: "" };
      const HINT = `<div class="expand-hint"><span class="when-closed">展开全文 ▾</span><span class="when-open">收起 ▴</span></div>`;

      function storyAttempt(item) {
        const tone = { supported: "ok", contradicted: "bad", inconclusive: "warn" }[item.verdict] || "";
        const chips = item.experiments.map((experiment) =>
          `<span class="chip ${EXP_CHIP_CLASS[experiment.status] || ""}" title="${esc(experiment.objective)}">${esc(experiment.id)} · ${esc(experiment.status_label)}</span>`
        ).join("");
        return `<div class="story-card ${tone ? "tone-" + tone : ""}">
          <div class="story-head">
            <span class="story-kind">尝试 · 第 ${item.cycle} 轮</span>
            <span class="claim-id">${esc(item.claim_id)}</span>
            <span class="verdict ${item.verdict}">${esc(item.verdict_label)}</span>
          </div>
          <div class="srow"><span class="slabel">假设</span><div class="stext clamp">${esc(item.hypothesis)}</div></div>
          ${chips ? `<div class="srow"><span class="slabel">验证</span><div class="stext"><div class="exp-chips">${chips}</div></div></div>` : ""}
          <div class="srow"><span class="slabel">结果</span><div class="stext clamp ${item.outcome ? "" : "pending-text"}">${item.outcome ? esc(item.outcome) : "待验证——实验尚未运行或证据尚未判定"}</div></div>
          ${item.twist ? `<div class="srow twist"><span class="slabel">转折</span><div class="stext clamp">${esc(item.twist)}</div></div>` : ""}
          ${HINT}
        </div>`;
      }

      function storyPivot(item) {
        const retired = item.retired.map((entry) => `<span class="tag retired">${esc(entry)}</span>`).join("");
        const fresh = item.fresh.map((entry) => `<span class="tag fresh">${esc(entry)}</span>`).join("");
        return `<div class="story-card tone-pivot">
          <div class="story-head">
            <span class="story-kind">方向调整 · 第 ${item.cycle} 轮</span>
            <span class="chip pivot">为什么重来</span>
          </div>
          <div class="srow"><span class="slabel">原因</span><div class="stext clamp">${esc(item.reason)}</div></div>
          ${retired ? `<div class="srow fail"><span class="slabel">退役</span><div class="stext"><div class="tag-list">${retired}</div></div></div>` : ""}
          ${fresh ? `<div class="srow"><span class="slabel">新立</span><div class="stext"><div class="tag-list">${fresh}</div></div></div>` : ""}
          ${HINT}
        </div>`;
      }

      function storyAbandoned(item) {
        return `<div class="story-card tone-bad">
          <div class="story-head"><span class="story-kind">放弃的方向 · 第 ${item.cycle} 轮</span></div>
          <div class="srow"><span class="slabel">尝试</span><div class="stext clamp">${esc(item.direction)}</div></div>
          <div class="srow fail"><span class="slabel">失败</span><div class="stext clamp">${esc(item.reason)}</div></div>
          ${HINT}
        </div>`;
      }

      function storyDecision(item) {
        return `<div class="story-card ${item.action === "continue" ? "tone-ok" : "tone-pivot"}">
          <div class="story-head">
            <span class="story-kind">本轮决策 · 第 ${item.cycle} 轮</span>
            <span class="decision-action ${esc(item.action)}">${esc(ACTION_LABEL[item.action] || item.action)}</span>
          </div>
          <div class="srow"><span class="slabel">理由</span><div class="stext clamp">${esc(item.rationale)}</div></div>
          ${HINT}
        </div>`;
      }

      function storyDotClass(item) {
        if (item.kind === "attempt") return item.verdict;
        if (item.kind === "pivot") return "pivot";
        if (item.kind === "abandoned") return "abandoned";
        if (item.kind === "decision") return "decision";
        return "";
      }

      function renderStory() {
        const rows = [];
        let side = 0;
        for (const item of data.story) {
          if (item.kind === "cycle") {
            side = 0;
            rows.push(`<div class="story-milestone"><div class="story-milestone-inner">
              <b>第 ${item.cycle} 轮${item.is_current ? " · 当前" : ""}${item.status ? ` · ${esc(item.status)}` : ""}</b>
              <div class="milestone-q">${esc(item.question)}</div>
            </div></div>`);
            continue;
          }
          const sideClass = side++ % 2 === 0 ? "left" : "right";
          const card =
            item.kind === "attempt" ? storyAttempt(item)
            : item.kind === "pivot" ? storyPivot(item)
            : item.kind === "abandoned" ? storyAbandoned(item)
            : storyDecision(item);
          rows.push(`<div class="story-item ${sideClass}"><span class="story-dot ${storyDotClass(item)}"></span>${card}</div>`);
        }
        document.getElementById("story").innerHTML = rows.join("");
      }

      function renderClaim(claim) {
        const noteHtml = claim.note
          ? `<div class="claim-note"><b>转折：</b>${esc(claim.note)}</div>` : "";
        const findingHtml = claim.finding_summary
          ? `<div class="claim-finding">${esc(claim.finding_summary)}</div>` : "";
        const falsHtml = claim.falsification
          ? `<details><summary>证伪条件</summary><div>${esc(claim.falsification)}</div></details>` : "";
        return `<div class="claim ${claim.verdict}">
          <div class="claim-head">
            <span class="claim-id">${esc(claim.id)}</span>
            ${claim.type_label ? `<span class="chip">${esc(claim.type_label)}</span>` : ""}
            <span class="verdict ${claim.verdict}">${esc(claim.verdict_label)}</span>
            ${claim.experiments.length ? `<span class="chip">实验 ${claim.experiments.map(esc).join(" · ")}</span>` : ""}
          </div>
          <p class="claim-text">${esc(claim.text)}</p>
          ${findingHtml}${noteHtml}${falsHtml}
        </div>`;
      }

      function renderExperiment(experiment) {
        const metrics = Object.entries(experiment.metrics || {})
          .map(([key, value]) => `<span class="metric">${esc(key)}=${esc(value)}</span>`).join("");
        return `<div class="exp ${experiment.status}">
          <div class="exp-head">
            <span class="exp-id">${esc(experiment.id)}</span>
            ${experiment.priority ? `<span class="chip">${esc(experiment.priority)}</span>` : ""}
            <span class="exp-status">${esc(experiment.status_label)}</span>
          </div>
          <p class="exp-objective">${esc(experiment.objective)}</p>
          ${experiment.error ? `<div class="exp-error">失败原因：${esc(experiment.error)}</div>` : ""}
          ${experiment.status !== "passed" && experiment.failure_policy
            ? `<div class="exp-fallback"><b>失败预案：</b>${esc(experiment.failure_policy)}</div>` : ""}
          ${metrics ? `<div class="exp-metrics">${metrics}</div>` : ""}
        </div>`;
      }

      function renderChapter(chapter) {
        const parts = [];

        parts.push(`<div class="chapter-head">
          <span class="chapter-title">第 ${chapter.cycle} 轮</span>
          ${chapter.is_current ? `<span class="chip info">当前</span>` : `<span class="chip">已归档</span>`}
          ${chapter.status ? `<span class="chip">${esc(chapter.status)}</span>` : ""}
          ${chapter.strategy ? `<span class="chip ${chapter.strategy.action === "continue" ? "ok" : "pivot"}">决策 ${esc(chapter.strategy.action)}</span>` : ""}
        </div>`);
        if (chapter.summary) parts.push(`<p class="chapter-summary">${esc(chapter.summary)}</p>`);

        if (chapter.revision) {
          const retired = chapter.revision.retired_claims.map((item) => `<span class="tag retired">${esc(item)}</span>`).join("");
          const fresh = chapter.revision.new_claims.map((item) => `<span class="tag fresh">${esc(item)}</span>`).join("");
          parts.push(`<div class="block pivot-block">
            <div class="block-head">方向调整 · 为什么重来</div>
            <div class="block-body">
              <p class="pivot-reason">${esc(chapter.revision.reason)}</p>
              ${retired ? `<span class="tag-label">退役的主张</span><div class="tag-list">${retired}</div>` : ""}
              ${fresh ? `<span class="tag-label">新立的主张</span><div class="tag-list">${fresh}</div>` : ""}
            </div>
          </div>`);
        }

        if (chapter.claims.length) {
          parts.push(`<div class="block">
            <div class="block-head">研究主张与证据判定 <span class="count">${chapter.claims.length} 项</span></div>
            <div class="block-body">${chapter.claims.map(renderClaim).join("")}</div>
          </div>`);
        }

        if (chapter.experiments.length) {
          parts.push(`<div class="block">
            <div class="block-head">数值实验 <span class="count">${chapter.experiments.length} 项</span></div>
            <div class="block-body"><div class="exp-grid">${chapter.experiments.map(renderExperiment).join("")}</div></div>
          </div>`);
        }

        if (chapter.abandoned.length) {
          parts.push(`<div class="block abandon-block">
            <div class="block-head">放弃的方向 · 失败原因 <span class="count">${chapter.abandoned.length} 项</span></div>
            <div class="block-body">${chapter.abandoned.map((item) => `
              <div class="abandon-item">
                <div class="dir">${esc(item.direction)}</div>
                <div class="why"><b>原因：</b>${esc(item.reason)}</div>
              </div>`).join("")}</div>
          </div>`);
        }

        if (chapter.strategy) {
          const unresolved = chapter.strategy.unresolved_items.map((item) => `<li>${esc(item)}</li>`).join("");
          parts.push(`<div class="block">
            <div class="block-head">本轮决策</div>
            <div class="block-body decision">
              <span class="decision-action ${esc(chapter.strategy.action)}">${esc(ACTION_LABEL[chapter.strategy.action] || chapter.strategy.action)}</span>
              <details><summary>决策理由</summary><div>${esc(chapter.strategy.rationale)}</div></details>
              ${unresolved ? `<details><summary>遗留问题（${chapter.strategy.unresolved_items.length}）</summary><ul class="unresolved">${unresolved}</ul></details>` : ""}
            </div>
          </div>`);
        }

        if (chapter.reviews.length) {
          parts.push(`<div class="block">
            <div class="block-head">模拟审稿 <span class="count">${chapter.reviews.length} 份</span></div>
            <div class="block-body"><div class="review-chips">${chapter.reviews.map((review) => {
              const verdictClass = /reject|major/i.test(review.verdict) ? "bad" : (/minor|accept/i.test(review.verdict) ? "ok" : "warn");
              return `<span class="chip ${verdictClass}">${esc(review.name)} · ${esc(review.verdict)}</span>`;
            }).join("")}</div></div>
          </div>`);
        }

        if (chapter.lessons.length) {
          parts.push(`<div class="block">
            <div class="block-head">经验教训 <span class="count">${chapter.lessons.length} 条</span></div>
            <div class="block-body">${chapter.lessons.map((lesson) => `
              <div class="lesson">
                <span class="sev ${esc(lesson.severity)}">${esc(lesson.severity)} ${esc(lesson.id)}</span>${esc(lesson.lesson)}
                ${lesson.rule ? `<span class="rule"><b>规则：</b>${esc(lesson.rule)}</span>` : ""}
              </div>`).join("")}</div>
          </div>`);
        }

        return `<article class="chapter ${chapter.is_current ? "current" : ""}">
          <div class="chapter-marker">${chapter.cycle}</div>
          ${parts.join("")}
        </article>`;
      }

      renderStory();
      document.getElementById("story").addEventListener("click", (event) => {
        if (event.target.closest("a, details, summary")) return;
        const card = event.target.closest(".story-card");
        if (card) card.classList.toggle("expanded");
      });

      document.getElementById("journey").innerHTML =
        data.chapters.map(renderChapter).join("");
      document.getElementById("footer-note").textContent =
        "数据来源：research/ 下的 plan.json · findings.json · strategy.json · iteration_summary.json · jobs/*/result.json（只读聚合，不改动任何研究产物）";
    })();
  </script>
</body>
</html>
"""
