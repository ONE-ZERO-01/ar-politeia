"""Tests for the research-journey timeline renderer."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from autoresearcher.orchestration import (
    GraphError,
    build_research_timeline,
    render_html,
    write_timeline,
)


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


@pytest.fixture()
def research_dir(tmp_path: Path) -> Path:
    research = tmp_path / "research"

    # ── archived cycle 1 ────────────────────────────────────────────────
    _write_json(research / "versions" / "cycle-1" / "plan.json", {
        "project_id": "demo",
        "cycle": 1,
        "status": "analyzed",
        "summary": "第一轮：检验 no-go。",
        "question": "no-go 是否生效？",
        "claims": [
            {"id": "C1", "text": "校准通过。", "type": "calibration",
             "falsification": "误差 >= 2%。", "experiments": ["E1"]},
            {"id": "C2", "text": "存在非零下界。", "type": "core",
             "falsification": "全区域 S_GS≈0。", "experiments": ["E2", "E3"]},
        ],
        "experiments": [
            {"id": "E1", "claim_ids": ["C1"], "objective": "Page 校准。",
             "priority": "P1", "artifacts": ["jobs/E1/result.json"]},
            {"id": "E2", "claim_ids": ["C2"], "objective": "相图扫描。",
             "priority": "P1", "artifacts": ["jobs/E2/result.json"],
             "failure_policy": "若优化不收敛先增加起点数。"},
            {"id": "E3", "claim_ids": ["C2"], "objective": "对照实验。",
             "priority": "P2", "artifacts": ["jobs/E3/result.json"]},
        ],
    })
    _write_json(research / "versions" / "cycle-1" / "findings.json", {
        "cycle": 1,
        "findings": [
            {"claim_id": "C1", "verdict": "supported", "summary": "校准全部通过。",
             "evidence": ["jobs/E1/result.json"]},
            {"claim_id": "C2", "verdict": "contradicted",
             "summary": "全区域找到 S_GS≈0 的划分，无下界。",
             "note": "原始声称被反驳，触发 replan。",
             "evidence": ["jobs/E2/result.json"]},
        ],
    })
    _write_json(
        research / "versions" / "cycle-1" / "orchestration" / "strategy.json",
        {"action": "replan", "rationale": "C2 被反驳，需要换方向。",
         "unresolved_items": ["d>=16 收敛性未解决。"]},
    )
    _write_json(research / "versions" / "cycle-1" / "iteration_summary.json", {
        "abandoned_directions": [
            {"direction": "非零下界假说", "reason": "被 E2 数值反证。"},
        ],
        "core_lessons": [
            {"id": "L1", "severity": "P0", "lesson": "数值 overclaim。",
             "rule": "数值界必须对照 result.json。"},
        ],
    })
    _write_json(
        research / "versions" / "cycle-1" / "reviews" / "nature-technical.json",
        {"verdict": "minor revision"},
    )

    # ── shared jobs directory ───────────────────────────────────────────
    _write_json(research / "jobs" / "E1" / "result.json", {
        "experiment": "E1",
        "description": "Page calibration",
        "pass": True,
        "timestamp": "2026-08-17T21:07:17+0800",
        "n_samples": 500,
        "rel_tol": 0.02,
        "rows": [{"big": "array"}],
        "long_text": "x" * 200,
    })
    _write_json(research / "jobs" / "E2" / "result.json", {
        "experiment": "E2",
        "pass": False,
        "error": "NaN detected in scan",
    })
    # E3 has no result.json → pending.

    # ── current cycle 2 (freshly planned, stale evidence around) ───────
    _write_json(research / "plan.json", {
        "project_id": "demo",
        "cycle": 2,
        "status": "planned",
        "summary": "第二轮：谱定理方向。",
        "question": "最局域性由什么决定？",
        "claims": [
            # Carried forward verbatim from cycle 1 → must not re-appear
            # in the story stream (no new evidence this cycle).
            {"id": "C1", "text": "校准通过。", "type": "calibration",
             "falsification": "误差 >= 2%。", "experiments": ["E1"]},
            {"id": "C3", "text": "谱定理成立。", "type": "core",
             "experiments": ["E4"]},
        ],
        "experiments": [
            {"id": "E4", "claim_ids": ["C3"], "objective": "谱公式验证。",
             "priority": "P1", "artifacts": ["jobs/E4/result.json"]},
        ],
        "revision": {
            "reason": "C2 反驳后转向谱定理。",
            "retired_claims": ["C2（非零下界）"],
            "new_claims": ["C3（谱定理）"],
        },
    })
    # Stale findings from cycle 1 still sitting at research root.
    _write_json(research / "findings.json", {
        "cycle": 1,
        "findings": [{"claim_id": "C3", "verdict": "supported", "summary": "stale"}],
    })
    # Stale strategy: must be hidden because current plan is only "planned".
    _write_json(research / "orchestration" / "strategy.json",
                {"action": "continue", "rationale": "stale"})
    # Stale iteration summary from cycle 1 lingering at the research root.
    _write_json(research / "orchestration" / "iteration_summary.json", {
        "cycle": 1,
        "core_lessons": [{"id": "L1", "severity": "P0", "lesson": "stale"}],
    })
    # Stale reviews from the previous cycle (no cycle field to filter on).
    _write_json(research / "orchestration" / "reviews" / "prl-broad.json",
                {"verdict": "minor revision"})

    return research


def test_chapters_are_ordered_and_flagged(research_dir: Path) -> None:
    timeline = build_research_timeline(research_dir)
    assert [chapter["cycle"] for chapter in timeline["chapters"]] == [1, 2]
    assert timeline["chapters"][0]["is_current"] is False
    assert timeline["chapters"][1]["is_current"] is True
    assert timeline["current_cycle"] == 2
    assert timeline["question"] == "最局域性由什么决定？"


def test_claim_verdicts_and_failure_note(research_dir: Path) -> None:
    timeline = build_research_timeline(research_dir)
    claims = {claim["id"]: claim for claim in timeline["chapters"][0]["claims"]}
    assert claims["C1"]["verdict"] == "supported"
    assert claims["C2"]["verdict"] == "contradicted"
    assert "触发 replan" in claims["C2"]["note"]
    # Current-cycle claim has no fresh findings → pending.
    current_claim = timeline["chapters"][1]["claims"][0]
    assert current_claim["verdict"] == "pending"


def test_experiment_status_and_metrics(research_dir: Path) -> None:
    timeline = build_research_timeline(research_dir)
    experiments = {
        experiment["id"]: experiment
        for experiment in timeline["chapters"][0]["experiments"]
    }
    assert experiments["E1"]["status"] == "passed"
    assert experiments["E1"]["metrics"] == {"n_samples": "500", "rel_tol": "0.02"}
    assert experiments["E1"]["failure_policy"] is None
    assert experiments["E2"]["status"] == "failed"
    assert experiments["E2"]["error"] == "NaN detected in scan"
    assert "增加起点数" in experiments["E2"]["failure_policy"]
    assert experiments["E3"]["status"] == "pending"


def test_stale_artifacts_are_excluded_from_current_chapter(research_dir: Path) -> None:
    timeline = build_research_timeline(research_dir)
    current = timeline["chapters"][1]
    # findings.json has cycle=1 ≠ plan cycle 2 → not attached.
    assert current["claims"][0]["finding_summary"] is None
    # strategy hidden while the plan is still "planned".
    assert current["strategy"] is None
    # iteration summary belongs to cycle 1 → not attached to cycle 2.
    assert current["lessons"] == []
    # reviews cannot exist for a freshly planned cycle.
    assert current["reviews"] == []
    assert current["revision"]["retired_claims"] == ["C2（非零下界）"]


def test_pivot_lessons_reviews_and_summary_counts(research_dir: Path) -> None:
    timeline = build_research_timeline(research_dir)
    archived = timeline["chapters"][0]
    assert archived["strategy"]["action"] == "replan"
    assert archived["abandoned"][0]["reason"] == "被 E2 数值反证。"
    assert archived["lessons"][0]["severity"] == "P0"
    assert archived["reviews"] == [
        {"name": "nature-technical", "verdict": "minor revision"}
    ]
    summary = timeline["summary"]
    assert summary["cycles"] == 2
    assert summary["claims"] == {
        "supported": 1, "contradicted": 1, "inconclusive": 0, "pending": 2,
    }
    assert summary["experiments"] == {
        "passed": 1, "failed": 1, "done": 0, "pending": 2,
    }
    assert summary["abandoned"] == 1


def test_story_stream_order_and_content(research_dir: Path) -> None:
    timeline = build_research_timeline(research_dir)
    story = timeline["story"]
    kinds = [entry["kind"] for entry in story]
    # cycle 1: opening → 2 attempts → 1 abandoned → decision;
    # cycle 2: opening → pivot (revision) → 1 pending attempt.
    assert kinds == [
        "cycle", "attempt", "attempt", "abandoned", "decision",
        "cycle", "pivot", "attempt",
    ]

    contradicted = story[2]
    assert contradicted["claim_id"] == "C2"
    assert contradicted["verdict"] == "contradicted"
    assert contradicted["hypothesis"] == "存在非零下界。"
    assert "触发 replan" in contradicted["twist"]
    assert [(e["id"], e["status"]) for e in contradicted["experiments"]] == [
        ("E2", "failed"), ("E3", "pending"),
    ]

    abandoned = story[3]
    assert abandoned["direction"] == "非零下界假说"
    assert abandoned["reason"] == "被 E2 数值反证。"

    pivot = story[6]
    assert pivot["reason"] == "C2 反驳后转向谱定理。"
    assert pivot["retired"] == ["C2（非零下界）"]

    pending_attempt = story[7]
    assert pending_attempt["claim_id"] == "C3"
    assert pending_attempt["verdict"] == "pending"
    assert pending_attempt["outcome"] is None

    # Carried-forward C1 (identical hypothesis, no new evidence) is told once.
    attempts = [entry for entry in story if entry["kind"] == "attempt"]
    assert [entry["claim_id"] for entry in attempts].count("C1") == 1


def test_render_html_is_self_contained_and_escaped(research_dir: Path) -> None:
    timeline = build_research_timeline(research_dir)
    timeline["chapters"][0]["claims"][0]["text"] = "evil </script><script>alert(1)"
    html = render_html(timeline)
    assert html.startswith("<!doctype html>")
    assert "</script><script>alert(1)" not in html
    assert "\\u003c/script" in html
    assert "src=" not in html.split("<body>")[0]  # no external assets in head


def test_write_timeline_default_and_custom_output(
    research_dir: Path, tmp_path: Path
) -> None:
    default_target = write_timeline(research_dir)
    assert default_target == research_dir.resolve() / "timeline.html"
    assert "研究历程" in default_target.read_text(encoding="utf-8")

    custom = tmp_path / "out" / "journey.html"
    assert write_timeline(research_dir, output=custom) == custom.resolve()
    assert custom.is_file()


def test_missing_plan_raises(tmp_path: Path) -> None:
    with pytest.raises(GraphError):
        build_research_timeline(tmp_path / "nowhere")
