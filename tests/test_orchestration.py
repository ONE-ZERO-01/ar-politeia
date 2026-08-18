"""Functional tests for the multi-agent DAG orchestrator."""

import asyncio
import json
import sys
from pathlib import Path

import pytest

from autoresearcher.orchestration.graph import GraphError, load_graph, render_mermaid
from autoresearcher.orchestration.runner import Orchestrator, reset_nodes


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _graph(tmp_path: Path, nodes, **overrides) -> Path:
    prompt = tmp_path / "prompt.md"
    prompt.write_text("Complete the declared node output.", encoding="utf-8")
    data = {
        "schema_version": 1,
        "project_id": "test-project",
        "workspace": ".",
        "state_file": "state.json",
        "logs_dir": "logs",
        "max_parallel": 4,
        "max_cycles": 5,
        "nodes": nodes,
    }
    data.update(overrides)
    path = tmp_path / "graph.json"
    _write_json(path, data)
    return path


def _writer_node(node_id: str, output: str, depends_on=None, delay=0.0):
    script = (
        "import pathlib,sys,time;"
        "time.sleep(float(sys.argv[2]));"
        "pathlib.Path(sys.argv[1]).write_text('done', encoding='utf-8')"
    )
    return {
        "id": node_id,
        "kind": "command",
        "depends_on": depends_on or [],
        "command": [sys.executable, "-c", script, output, str(delay)],
        "outputs": [output],
        "timeout_seconds": 5,
    }


def test_graph_rejects_cycles(tmp_path):
    path = _graph(
        tmp_path,
        [
            {
                "id": "a",
                "kind": "barrier",
                "depends_on": ["b"],
            },
            {
                "id": "b",
                "kind": "barrier",
                "depends_on": ["a"],
            },
        ],
    )
    with pytest.raises(GraphError, match="acyclic"):
        load_graph(path)


def test_graph_rejects_paths_outside_workspace(tmp_path):
    path = _graph(
        tmp_path,
        [
            {
                "id": "unsafe",
                "kind": "command",
                "command": ["true"],
                "outputs": ["../outside.txt"],
            }
        ],
    )
    with pytest.raises(GraphError, match="inside"):
        load_graph(path)


def test_graph_rejects_multiple_output_producers(tmp_path):
    path = _graph(
        tmp_path,
        [
            _writer_node("a", "shared.out"),
            _writer_node("b", "shared.out"),
        ],
    )
    with pytest.raises(GraphError, match="multiple producers"):
        load_graph(path)


def test_state_override_must_stay_in_workspace(tmp_path):
    graph = load_graph(_graph(tmp_path, [_writer_node("a", "a.out")]))
    with pytest.raises(GraphError, match="state override"):
        Orchestrator(graph, state_path=tmp_path.parent / "outside-state.json")


def test_parallel_branches_join_before_downstream(tmp_path):
    path = _graph(
        tmp_path,
        [
            _writer_node("a", "a.out", delay=0.15),
            _writer_node("b", "b.out", delay=0.15),
            {
                "id": "join",
                "kind": "barrier",
                "depends_on": ["a", "b"],
                "inputs": ["a.out", "b.out"],
            },
            _writer_node("after", "after.out", depends_on=["join"]),
        ],
    )
    runner = Orchestrator(load_graph(path))
    state = asyncio.run(runner.run())
    assert state["status"] == "SUCCEEDED"
    assert all(
        state["nodes"][node_id]["status"] == "SUCCEEDED"
        for node_id in ("a", "b", "join", "after")
    )
    events = [(item["event"], item.get("node_id")) for item in state["events"]]
    first_success = min(
        events.index(("node_succeeded", "a")),
        events.index(("node_succeeded", "b")),
    )
    assert events.index(("node_started", "a")) < first_success
    assert events.index(("node_started", "b")) < first_success
    assert events.index(("barrier_satisfied", "join")) > max(
        events.index(("node_succeeded", "a")),
        events.index(("node_succeeded", "b")),
    )


def test_failure_blocks_only_downstream_branch(tmp_path):
    failing = {
        "id": "bad",
        "kind": "command",
        "command": [sys.executable, "-c", "raise SystemExit(3)"],
        "timeout_seconds": 5,
    }
    path = _graph(
        tmp_path,
        [
            failing,
            _writer_node("blocked_child", "blocked.out", depends_on=["bad"]),
            _writer_node("independent", "independent.out"),
        ],
    )
    state = asyncio.run(Orchestrator(load_graph(path)).run())
    assert state["status"] == "FAILED"
    assert state["nodes"]["bad"]["status"] == "FAILED"
    assert state["nodes"]["blocked_child"]["status"] == "BLOCKED"
    assert state["nodes"]["independent"]["status"] == "SUCCEEDED"
    assert not (tmp_path / "blocked.out").exists()


def test_agent_adapter_receives_isolated_prompt_on_stdin(tmp_path):
    script = (
        "import pathlib,sys;"
        "pathlib.Path(sys.argv[1]).write_text(sys.stdin.read(), encoding='utf-8')"
    )
    path = _graph(
        tmp_path,
        [
            {
                "id": "agent_a",
                "kind": "agent",
                "adapter": "test",
                "prompt_file": "prompt.md",
                "outputs": ["agent.out"],
            }
        ],
        adapters={
            "test": {
                "command": [
                    sys.executable,
                    "-c",
                    script,
                    "{workspace}/agent.out",
                ],
                "prompt_mode": "stdin",
            }
        },
    )
    state = asyncio.run(Orchestrator(load_graph(path)).run())
    assert state["status"] == "SUCCEEDED"
    content = (tmp_path / "agent.out").read_text(encoding="utf-8")
    assert "node_id: agent_a" in content
    assert "Complete the declared node output." in content
    assert "Do not rely on another agent's conversation state." in content


def test_false_condition_skips_branch_and_satisfies_join(tmp_path):
    decision_script = (
        "import pathlib;"
        "pathlib.Path('decision.json').write_text("
        "'{\"action\":\"continue\"}', encoding='utf-8')"
    )
    path = _graph(
        tmp_path,
        [
            {
                "id": "decision",
                "kind": "command",
                "command": [sys.executable, "-c", decision_script],
                "outputs": ["decision.json"],
            },
            {
                "id": "replan",
                "kind": "barrier",
                "depends_on": ["decision"],
                "when": {
                    "path": "decision.json",
                    "field": "action",
                    "equals": "replan",
                },
            },
            {
                "id": "continue",
                "kind": "barrier",
                "depends_on": ["decision"],
                "when": {
                    "path": "decision.json",
                    "field": "action",
                    "equals": "continue",
                },
            },
            {
                "id": "join",
                "kind": "barrier",
                "depends_on": ["replan", "continue"],
            },
        ],
    )
    state = asyncio.run(Orchestrator(load_graph(path)).run())
    assert state["status"] == "SUCCEEDED"
    assert state["nodes"]["replan"]["status"] == "SKIPPED"
    assert state["nodes"]["continue"]["status"] == "SUCCEEDED"
    assert state["nodes"]["join"]["status"] == "SUCCEEDED"


def test_retry_recovers_transient_failure(tmp_path):
    script = (
        "import pathlib,sys;"
        "flag=pathlib.Path('attempt.flag');"
        "first=not flag.exists();"
        "flag.write_text('seen', encoding='utf-8');"
        "pathlib.Path('result.out').write_text('done', encoding='utf-8') "
        "if not first else None;"
        "raise SystemExit(1 if first else 0)"
    )
    path = _graph(
        tmp_path,
        [
            {
                "id": "flaky",
                "kind": "command",
                "command": [sys.executable, "-c", script],
                "outputs": ["result.out"],
                "retries": 1,
                "timeout_seconds": 5,
            }
        ],
    )
    state = asyncio.run(Orchestrator(load_graph(path)).run())
    assert state["status"] == "SUCCEEDED"
    assert state["nodes"]["flaky"]["attempts"] == 2


def test_missing_upstream_output_invalidates_downstream_on_resume(tmp_path):
    path = _graph(
        tmp_path,
        [
            _writer_node("a", "a.out"),
            _writer_node("b", "b.out", depends_on=["a"]),
        ],
    )
    graph = load_graph(path)
    first = asyncio.run(Orchestrator(graph).run())
    assert first["status"] == "SUCCEEDED"
    (tmp_path / "a.out").unlink()

    second = asyncio.run(Orchestrator(graph).run())
    assert second["status"] == "SUCCEEDED"
    assert second["nodes"]["a"]["attempts"] == 2
    assert second["nodes"]["b"]["attempts"] == 2
    reset_events = [
        item for item in second["events"] if item["event"] == "node_reset"
    ]
    assert {item["node_id"] for item in reset_events} >= {"a", "b"}


def test_reset_node_also_resets_downstream(tmp_path):
    path = _graph(
        tmp_path,
        [
            _writer_node("a", "a.out"),
            _writer_node("b", "b.out", depends_on=["a"]),
        ],
    )
    graph = load_graph(path)
    asyncio.run(Orchestrator(graph).run())
    state = reset_nodes(graph, ["a"])
    assert state["nodes"]["a"]["status"] == "PENDING"
    assert state["nodes"]["b"]["status"] == "PENDING"


def test_mermaid_contains_edges(tmp_path):
    graph = load_graph(
        _graph(
            tmp_path,
            [
                _writer_node("a", "a.out"),
                {"id": "join", "kind": "barrier", "depends_on": ["a"]},
            ],
        )
    )
    diagram = render_mermaid(graph)
    assert "a --> join" in diagram
    assert 'join{{"join<br/>barrier"}}' in diagram


def test_cycle_control_replans_then_converges(tmp_path):
    script = (
        "import json,pathlib;"
        "counter=pathlib.Path('cycle.count');"
        "value=int(counter.read_text())+1 if counter.exists() else 1;"
        "counter.write_text(str(value), encoding='utf-8');"
        "decision='replan' if value == 1 else 'continue';"
        "pathlib.Path('decision.json').write_text("
        "json.dumps({'action': decision}), encoding='utf-8')"
    )
    path = _graph(
        tmp_path,
        [
            {
                "id": "strategy",
                "kind": "command",
                "command": [sys.executable, "-c", script],
                "outputs": ["decision.json"],
            }
        ],
        cycle_control={
            "decision_path": "decision.json",
            "decision_field": "action",
            "repeat_values": ["replan", "revise"],
            "terminal_values": ["continue", "request_human", "stop_request"],
        },
        max_cycles=3,
    )
    state = asyncio.run(Orchestrator(load_graph(path)).run())
    assert state["status"] == "SUCCEEDED"
    assert state["cycle"] == 2
    assert (tmp_path / "cycles" / "cycle-1.state.json").is_file()
    assert any(item["event"] == "cycle_advanced" for item in state["events"])
    # The decision that caused the replan must be archived verbatim, because
    # the live decision file is overwritten by the next cycle.
    decision_archive = tmp_path / "cycles" / "cycle-1.decision.json"
    assert decision_archive.is_file()
    archived = json.loads(decision_archive.read_text(encoding="utf-8"))
    assert archived["action"] == "replan"
    advance = next(
        item for item in state["events"] if item["event"] == "cycle_advanced"
    )
    assert advance["archive_decision"] == str(decision_archive)


def test_agent_retry_receives_previous_error(tmp_path):
    # First attempt exits 3; the retry must see that error in its prompt.
    script = (
        "import pathlib,sys;"
        "data=sys.stdin.read();"
        "m=pathlib.Path('attempt.marker');"
        "done=m.exists();"
        "pathlib.Path('a.out').write_text(data, encoding='utf-8')"
        " if done else m.write_text('x', encoding='utf-8');"
        "sys.exit(0 if done else 3)"
    )
    node = {
        "id": "a",
        "kind": "agent",
        "prompt_file": "prompt.md",
        "prompt_mode": "stdin",
        "command": [sys.executable, "-c", script],
        "outputs": ["a.out"],
        "retries": 1,
        "timeout_seconds": 10,
    }
    state = asyncio.run(Orchestrator(load_graph(_graph(tmp_path, [node]))).run())
    assert state["nodes"]["a"]["status"] == "SUCCEEDED"
    retry_prompt = (tmp_path / "a.out").read_text(encoding="utf-8")
    assert "Previous attempt failed" in retry_prompt
    assert "exited with code 3" in retry_prompt


def test_agent_budget_blocks_next_agent_node(tmp_path):
    slow = (
        "import pathlib,time;"
        "time.sleep(1.2);"
        "pathlib.Path('a.out').write_text('done', encoding='utf-8')"
    )
    fast = "import pathlib;pathlib.Path('b.out').write_text('done', encoding='utf-8')"
    nodes = [
        {
            "id": "a",
            "kind": "agent",
            "prompt_file": "prompt.md",
            "prompt_mode": "none",
            "command": [sys.executable, "-c", slow],
            "outputs": ["a.out"],
            "timeout_seconds": 10,
        },
        {
            "id": "b",
            "kind": "agent",
            "prompt_file": "prompt.md",
            "prompt_mode": "none",
            "command": [sys.executable, "-c", fast],
            "depends_on": ["a"],
            "outputs": ["b.out"],
            "timeout_seconds": 10,
        },
    ]
    path = _graph(
        tmp_path, nodes, budget={"max_agent_seconds_per_cycle": 1}
    )
    state = asyncio.run(Orchestrator(load_graph(path)).run())
    assert state["nodes"]["a"]["status"] == "SUCCEEDED"
    assert state["nodes"]["b"]["status"] == "BLOCKED"
    assert state["status"] == "BLOCKED"
    assert state["cycle_agent_seconds"] >= 1.0
    assert any(
        item["event"] == "node_budget_blocked" for item in state["events"]
    )


def test_budget_does_not_meter_command_nodes(tmp_path):
    # Non-agent nodes are free: the budget must not block them.
    nodes = [
        _writer_node("a", "a.out", delay=1.2),
        _writer_node("b", "b.out", depends_on=["a"]),
    ]
    path = _graph(
        tmp_path, nodes, budget={"max_agent_seconds_per_cycle": 1}
    )
    state = asyncio.run(Orchestrator(load_graph(path)).run())
    assert state["status"] == "SUCCEEDED"
    assert state["cycle_agent_seconds"] == 0.0


def test_agent_attempt_records_provenance_and_last_message(tmp_path):
    script = (
        "import pathlib;"
        "print('FINAL STATEMENT: outputs complete');"
        "pathlib.Path('a.out').write_text('done', encoding='utf-8')"
    )
    node = {
        "id": "a",
        "kind": "agent",
        "prompt_file": "prompt.md",
        "prompt_mode": "stdin",
        "command": [sys.executable, "-c", script],
        "outputs": ["a.out"],
        "timeout_seconds": 10,
    }
    state = asyncio.run(Orchestrator(load_graph(_graph(tmp_path, [node]))).run())
    assert state["nodes"]["a"]["status"] == "SUCCEEDED"
    attempt_log = state["nodes"]["a"]["logs"][-1]
    # Provenance: the agent command and its CLI version are recorded.
    assert attempt_log["command"][0] == sys.executable
    assert attempt_log["adapter_version"]  # `python --version` output is truthy
    # Final statement: stdout tail is collected, closing the last-message gap.
    last_message = Path(attempt_log["last_message"])
    assert last_message.is_file()
    assert "FINAL STATEMENT" in last_message.read_text(encoding="utf-8")


def test_optional_inputs_do_not_block_node_start(tmp_path):
    node = _writer_node("a", "a.out")
    node["optional_inputs"] = ["missing-feedback.json"]
    state = asyncio.run(Orchestrator(load_graph(_graph(tmp_path, [node]))).run())
    assert state["status"] == "SUCCEEDED"
    assert state["nodes"]["a"]["status"] == "SUCCEEDED"


def test_graph_rejects_schema_for_undeclared_output(tmp_path):
    node = _writer_node("a", "a.out")
    node["output_schemas"] = {"other.out": "schema.json"}
    with pytest.raises(GraphError, match="declared output"):
        load_graph(_graph(tmp_path, [node]))


def test_output_schema_blocks_invalid_contract(tmp_path):
    _write_json(
        tmp_path / "schema.json",
        {
            "type": "object",
            "required": ["action", "rationale"],
            "properties": {
                "action": {"enum": ["continue", "replan"]},
                "rationale": {"type": "string", "minLength": 1},
            },
        },
    )
    script = (
        "import json,pathlib;"
        "pathlib.Path('decision.json').write_text("
        "json.dumps({'action': 'bogus'}), encoding='utf-8')"
    )
    node = {
        "id": "strategy",
        "kind": "command",
        "command": [sys.executable, "-c", script],
        "outputs": ["decision.json"],
        "output_schemas": {"decision.json": "schema.json"},
        "timeout_seconds": 5,
    }
    state = asyncio.run(Orchestrator(load_graph(_graph(tmp_path, [node]))).run())
    assert state["status"] == "FAILED"
    error = state["nodes"]["strategy"]["error"]
    assert "output contract violated" in error
    assert "enum" in error
    assert "rationale" in error


def test_output_schema_accepts_valid_contract(tmp_path):
    _write_json(
        tmp_path / "schema.json",
        {
            "type": "object",
            "required": ["action", "rationale"],
            "properties": {
                "action": {"enum": ["continue", "replan"]},
                "rationale": {"type": "string", "minLength": 1},
            },
        },
    )
    script = (
        "import json,pathlib;"
        "pathlib.Path('decision.json').write_text("
        "json.dumps({'action': 'continue', 'rationale': 'done'}),"
        " encoding='utf-8')"
    )
    node = {
        "id": "strategy",
        "kind": "command",
        "command": [sys.executable, "-c", script],
        "outputs": ["decision.json"],
        "output_schemas": {"decision.json": "schema.json"},
        "timeout_seconds": 5,
    }
    state = asyncio.run(Orchestrator(load_graph(_graph(tmp_path, [node]))).run())
    assert state["status"] == "SUCCEEDED"


def test_graph_rejects_unknown_repeat_reset_node(tmp_path):
    decision_script = (
        "import pathlib;"
        "pathlib.Path('decision.json').write_text("
        "'{\"action\":\"continue\"}', encoding='utf-8')"
    )
    path = _graph(
        tmp_path,
        [
            {
                "id": "strategy",
                "kind": "command",
                "command": [sys.executable, "-c", decision_script],
                "outputs": ["decision.json"],
            }
        ],
        cycle_control={
            "decision_path": "decision.json",
            "repeat_values": ["replan"],
            "terminal_values": ["continue"],
            "repeat_reset": {"replan": ["ghost"]},
        },
    )
    with pytest.raises(GraphError, match="unknown"):
        load_graph(path)


def test_repeat_reset_only_reruns_declared_subgraph(tmp_path):
    keep_script = (
        "import pathlib;"
        "path=pathlib.Path('keep.count');"
        "runs=path.read_text() + 'x' if path.exists() else 'x';"
        "path.write_text(runs, encoding='utf-8')"
    )
    strategy_script = (
        "import json,pathlib;"
        "counter=pathlib.Path('cycle.count');"
        "value=int(counter.read_text())+1 if counter.exists() else 1;"
        "counter.write_text(str(value), encoding='utf-8');"
        "decision='replan' if value == 1 else 'continue';"
        "pathlib.Path('decision.json').write_text("
        "json.dumps({'action': decision}), encoding='utf-8')"
    )
    path = _graph(
        tmp_path,
        [
            {
                "id": "keep",
                "kind": "command",
                "command": [sys.executable, "-c", keep_script],
                "outputs": ["keep.count"],
                "timeout_seconds": 5,
            },
            {
                "id": "strategy",
                "kind": "command",
                "depends_on": ["keep"],
                "command": [sys.executable, "-c", strategy_script],
                "outputs": ["decision.json"],
                "timeout_seconds": 5,
            },
        ],
        cycle_control={
            "decision_path": "decision.json",
            "repeat_values": ["replan"],
            "terminal_values": ["continue"],
            "repeat_reset": {"replan": ["strategy"]},
        },
        max_cycles=3,
    )
    state = asyncio.run(Orchestrator(load_graph(path)).run())
    assert state["status"] == "SUCCEEDED"
    assert state["cycle"] == 2
    # keep ran exactly once even though the graph cycled twice.
    assert (tmp_path / "keep.count").read_text(encoding="utf-8") == "x"
    assert (tmp_path / "cycle.count").read_text(encoding="utf-8") == "2"
    advance = next(
        item for item in state["events"] if item["event"] == "cycle_advanced"
    )
    assert advance["reset_nodes"] == ["strategy"]


def _foreach_writer_node(node_id, tasks_file="tasks.json", depends_on=None,
                         parallel=2, fail_ids=()):
    fail_literal = ",".join(fail_ids)
    script = (
        "import json,os,pathlib,sys;"
        "task=json.loads(os.environ['AUTORESEARCHER_TASK_JSON']);"
        "path=pathlib.Path(sys.argv[1]);"
        "path.parent.mkdir(parents=True, exist_ok=True);"
        "runs=path.read_text() + 'x' if path.exists() else 'x';"
        "path.write_text(runs, encoding='utf-8');"
        f"sys.exit(1 if task['id'] in '{fail_literal}'.split(',') else 0)"
    )
    return {
        "id": node_id,
        "kind": "foreach",
        "depends_on": depends_on or [],
        "tasks_file": tasks_file,
        "task_parallel": parallel,
        "task_template": {
            "kind": "command",
            "command": [sys.executable, "-c", script, "{task.out}"],
            "outputs": ["{task.out}"],
            "timeout_seconds": 5,
        },
    }


def test_foreach_runs_all_tasks_and_records_state(tmp_path):
    _write_json(
        tmp_path / "tasks.json",
        {"tasks": [
            {"id": "E1", "out": "jobs/E1/result.txt"},
            {"id": "E2", "out": "jobs/E2/result.txt"},
        ]},
    )
    path = _graph(tmp_path, [_foreach_writer_node("experiments")])
    state = asyncio.run(Orchestrator(load_graph(path)).run())
    assert state["status"] == "SUCCEEDED"
    record = state["nodes"]["experiments"]
    assert record["status"] == "SUCCEEDED"
    assert set(record["tasks"]) == {"E1", "E2"}
    assert all(t["status"] == "SUCCEEDED" for t in record["tasks"].values())
    assert (tmp_path / "jobs/E1/result.txt").read_text() == "x"
    assert (tmp_path / "jobs/E2/result.txt").read_text() == "x"


def test_foreach_task_failure_fails_node_and_blocks_downstream(tmp_path):
    _write_json(
        tmp_path / "tasks.json",
        {"tasks": [
            {"id": "ok", "out": "jobs/ok/result.txt"},
            {"id": "bad", "out": "jobs/bad/result.txt"},
        ]},
    )
    path = _graph(
        tmp_path,
        [
            _foreach_writer_node("experiments", fail_ids=("bad",)),
            _writer_node("analyze", "analyze.out", depends_on=["experiments"]),
        ],
    )
    state = asyncio.run(Orchestrator(load_graph(path)).run())
    assert state["status"] == "FAILED"
    record = state["nodes"]["experiments"]
    assert record["status"] == "FAILED"
    assert "bad" in record["error"]
    assert record["tasks"]["ok"]["status"] == "SUCCEEDED"
    assert record["tasks"]["bad"]["status"] == "FAILED"
    assert state["nodes"]["analyze"]["status"] == "BLOCKED"


def test_foreach_resume_reruns_only_missing_task_outputs(tmp_path):
    _write_json(
        tmp_path / "tasks.json",
        {"tasks": [
            {"id": "E1", "out": "jobs/E1/result.txt"},
            {"id": "E2", "out": "jobs/E2/result.txt"},
        ]},
    )
    graph = load_graph(_graph(tmp_path, [_foreach_writer_node("experiments")]))
    first = asyncio.run(Orchestrator(graph).run())
    assert first["status"] == "SUCCEEDED"
    (tmp_path / "jobs/E2/result.txt").unlink()
    second = asyncio.run(Orchestrator(graph).run())
    assert second["status"] == "SUCCEEDED"
    # E1 skipped (still one run), E2 reran (two runs appended).
    assert (tmp_path / "jobs/E1/result.txt").read_text() == "x"
    assert (tmp_path / "jobs/E2/result.txt").read_text() == "x"
    assert second["nodes"]["experiments"]["tasks"]["E1"]["attempts"] == 1
    assert second["nodes"]["experiments"]["tasks"]["E2"]["attempts"] == 2


def test_foreach_rejects_task_output_escaping_workspace(tmp_path):
    _write_json(
        tmp_path / "tasks.json",
        {"tasks": [{"id": "evil", "out": "../outside.txt"}]},
    )
    path = _graph(tmp_path, [_foreach_writer_node("experiments")])
    state = asyncio.run(Orchestrator(load_graph(path)).run())
    assert state["status"] == "FAILED"
    record = state["nodes"]["experiments"]
    assert record["tasks"]["evil"]["status"] == "FAILED"
    assert "escapes" in record["tasks"]["evil"]["error"]
    assert not (tmp_path.parent / "outside.txt").exists()


def _human_gate_graph(tmp_path, strategy_actions):
    """strategy writes actions[cycle-1] on each run."""
    actions_literal = json.dumps(strategy_actions)
    script = (
        "import json,pathlib;"
        "counter=pathlib.Path('runs.count');"
        "value=int(counter.read_text())+1 if counter.exists() else 1;"
        "counter.write_text(str(value), encoding='utf-8');"
        f"actions={actions_literal};"
        "action=actions[min(value, len(actions)) - 1];"
        "pathlib.Path('decision.json').write_text("
        "json.dumps({'action': action}), encoding='utf-8')"
    )
    return _graph(
        tmp_path,
        [
            {
                "id": "strategy",
                "kind": "command",
                "command": [sys.executable, "-c", script],
                "outputs": ["decision.json"],
                "timeout_seconds": 5,
            }
        ],
        cycle_control={
            "decision_path": "decision.json",
            "repeat_values": ["replan"],
            "terminal_values": ["continue", "request_human", "stop_request"],
            "human_values": ["request_human"],
            "human_decision_path": "human-decision.json",
        },
        max_cycles=3,
    )


def test_human_gate_pauses_then_replan_resumes(tmp_path):
    graph = load_graph(
        _human_gate_graph(tmp_path, ["request_human", "continue"])
    )
    paused = asyncio.run(Orchestrator(graph).run())
    assert paused["status"] == "AWAITING_HUMAN"
    # Without a decision the graph keeps waiting.
    waiting = asyncio.run(Orchestrator(graph).run())
    assert waiting["status"] == "AWAITING_HUMAN"
    assert (tmp_path / "runs.count").read_text() == "1"
    # Human answers replan → next cycle runs and converges on continue.
    _write_json(tmp_path / "human-decision.json", {"action": "replan"})
    resumed = asyncio.run(Orchestrator(graph).run())
    assert resumed["status"] == "SUCCEEDED"
    assert resumed["cycle"] == 2
    assert (tmp_path / "runs.count").read_text() == "2"
    assert not (tmp_path / "human-decision.json").exists()
    assert (tmp_path / "cycles" / "cycle-1.human-decision.json").is_file()


def test_human_gate_terminal_decision_finishes_without_rerun(tmp_path):
    graph = load_graph(_human_gate_graph(tmp_path, ["request_human"]))
    paused = asyncio.run(Orchestrator(graph).run())
    assert paused["status"] == "AWAITING_HUMAN"
    _write_json(tmp_path / "human-decision.json", {"action": "stop_request"})
    finished = asyncio.run(Orchestrator(graph).run())
    assert finished["status"] == "SUCCEEDED"
    assert (tmp_path / "runs.count").read_text() == "1"


def test_graph_rejects_human_values_outside_terminal(tmp_path):
    path = _graph(
        tmp_path,
        [
            {
                "id": "strategy",
                "kind": "command",
                "command": [sys.executable, "-c", "pass"],
                "outputs": ["decision.json"],
            }
        ],
        cycle_control={
            "decision_path": "decision.json",
            "repeat_values": ["replan"],
            "terminal_values": ["continue"],
            "human_values": ["request_human"],
            "human_decision_path": "human-decision.json",
        },
    )
    with pytest.raises(GraphError, match="subset of"):
        load_graph(path)


def test_state_lock_rejects_second_runner(tmp_path):
    graph = load_graph(_graph(tmp_path, [_writer_node("a", "a.out")]))
    holder = Orchestrator(graph)
    assert holder._acquire_file_lock() is True
    try:
        with pytest.raises(GraphError, match="already holds"):
            asyncio.run(Orchestrator(graph).run())
    finally:
        holder._release_file_lock()
    state = asyncio.run(Orchestrator(graph).run())
    assert state["status"] == "SUCCEEDED"


def test_cycle_control_hard_stops_at_max_cycles(tmp_path):
    script = (
        "import pathlib;"
        "pathlib.Path('decision.json').write_text("
        "'{\"action\":\"replan\"}', encoding='utf-8')"
    )
    path = _graph(
        tmp_path,
        [
            {
                "id": "strategy",
                "kind": "command",
                "command": [sys.executable, "-c", script],
                "outputs": ["decision.json"],
            }
        ],
        cycle_control={
            "decision_path": "decision.json",
            "repeat_values": ["replan"],
            "terminal_values": ["continue"],
        },
        max_cycles=2,
    )
    state = asyncio.run(Orchestrator(load_graph(path)).run())
    assert state["status"] == "BLOCKED"
    assert state["cycle"] == 2
    event = next(
        item for item in state["events"] if item["event"] == "max_cycles_reached"
    )
    assert event["max_cycles"] == 2
