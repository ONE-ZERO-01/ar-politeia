"""Command-line interface for the AutoResearcher multi-agent orchestrator."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from .graph import GraphError, load_graph, render_mermaid
from .runner import Orchestrator, reset_nodes
from .timeline import write_timeline


def _summary(state: Dict[str, Any]) -> Dict[str, Any]:
    counts: Dict[str, int] = {}
    for record in state.get("nodes", {}).values():
        status = record.get("status", "UNKNOWN")
        counts[status] = counts.get(status, 0) + 1
    return {
        "project_id": state.get("project_id"),
        "status": state.get("status"),
        "cycle": state.get("cycle"),
        "state_file": state.get("state_file"),
        "node_counts": counts,
    }


def _state_override(value: Optional[str]) -> Optional[Path]:
    return Path(value).expanduser() if value else None


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Execute crash-resumable multi-agent research DAGs"
    )
    subparsers = parser.add_subparsers(dest="action", required=True)

    validate_parser = subparsers.add_parser("validate", help="validate graph schema")
    validate_parser.add_argument("graph")

    render_parser = subparsers.add_parser("render", help="render graph as Mermaid")
    render_parser.add_argument("graph")
    render_parser.add_argument("--output")

    run_parser = subparsers.add_parser("run", help="run or resume a graph")
    run_parser.add_argument("graph")
    run_parser.add_argument("--state")
    run_parser.add_argument("--max-parallel", type=int)

    status_parser = subparsers.add_parser("status", help="show persisted graph state")
    status_parser.add_argument("graph")
    status_parser.add_argument("--state")
    status_parser.add_argument("--full", action="store_true")

    reset_parser = subparsers.add_parser(
        "reset", help="reset nodes and, by default, their downstream consumers"
    )
    reset_parser.add_argument("graph")
    reset_parser.add_argument("--state")
    reset_parser.add_argument("--node", action="append", required=True)
    reset_parser.add_argument("--no-downstream", action="store_true")

    timeline_parser = subparsers.add_parser(
        "timeline",
        help="render the research journey (claims, experiments, pivots, failures) as HTML",
    )
    timeline_parser.add_argument(
        "--research-dir",
        default="research",
        help="research artifacts directory (default: research)",
    )
    timeline_parser.add_argument(
        "--output",
        help="output HTML path (default: <research-dir>/timeline.html)",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.action == "timeline":
            output = Path(args.output).expanduser().resolve() if args.output else None
            target = write_timeline(Path(args.research_dir), output=output)
            print(json.dumps({"status": "ok", "timeline_html": str(target)}, ensure_ascii=False, indent=2))
            return
        graph = load_graph(Path(args.graph))
        if args.action == "validate":
            result = {
                "status": "ok",
                "project_id": graph.project_id,
                "nodes": len(graph.nodes),
                "graph_sha256": graph.graph_sha256,
            }
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return
        if args.action == "render":
            text = render_mermaid(graph)
            if args.output:
                output = Path(args.output).expanduser().resolve()
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(text, encoding="utf-8")
            else:
                print(text, end="")
            return
        if args.action == "run":
            runner = Orchestrator(
                graph,
                state_path=_state_override(args.state),
                max_parallel=args.max_parallel,
            )
            state = asyncio.run(runner.run())
            summary = _summary(state)
            summary["state_file"] = str(runner.state_path)
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            if state["status"] != "SUCCEEDED":
                raise SystemExit(1)
            return
        if args.action == "status":
            runner = Orchestrator(graph, state_path=_state_override(args.state))
            state = runner.prepare()
            result = state if args.full else _summary(state)
            if not args.full:
                result["state_file"] = str(runner.state_path)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return
        if args.action == "reset":
            state = reset_nodes(
                graph,
                args.node,
                state_path=_state_override(args.state),
                include_downstream=not args.no_downstream,
            )
            print(json.dumps(_summary(state), ensure_ascii=False, indent=2))
            return
    except GraphError as exc:
        print(
            json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False),
            file=sys.stderr,
        )
        raise SystemExit(2)


if __name__ == "__main__":
    main()

