"""Async, crash-resumable execution of multi-agent research DAGs."""

from __future__ import annotations

import asyncio
import fcntl
import json
import os
import shutil
import signal
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, IO, Iterable, List, Mapping, Optional, Set, Tuple

from .contracts import validate_file
from .graph import (
    TASK_ID_RE,
    AdapterSpec,
    GraphError,
    GraphSpec,
    NodeSpec,
    TaskTemplateSpec,
)


PENDING = "PENDING"
RUNNING = "RUNNING"
SUCCEEDED = "SUCCEEDED"
FAILED = "FAILED"
BLOCKED = "BLOCKED"
SKIPPED = "SKIPPED"
AWAITING_HUMAN = "AWAITING_HUMAN"
SATISFIED = {SUCCEEDED, SKIPPED}
TERMINAL = {SUCCEEDED, FAILED, BLOCKED, SKIPPED}


def _substitute_task(text: str, task: Mapping[str, Any]) -> str:
    """Replace `{task.<key>}` and `{task_id}` placeholders with task values."""
    result = text.replace("{task_id}", str(task.get("id", "")))
    for key, value in task.items():
        if isinstance(value, (str, int, float)) and not isinstance(value, bool):
            result = result.replace("{task." + key + "}", str(value))
    return result


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="milliseconds")


def _atomic_write_json(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(str(temp), str(path))


def _read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise GraphError(f"state must be a JSON object: {path}")
    return data


def _artifact_valid(path: Path) -> bool:
    if path.is_file():
        return path.stat().st_size > 0
    if path.is_dir():
        try:
            next(path.iterdir())
        except StopIteration:
            return False
        return True
    return False


def _lookup_field(data: Any, field_name: str) -> Any:
    current = data
    for part in field_name.split("."):
        if not isinstance(current, dict) or part not in current:
            raise GraphError(f"condition field does not exist: {field_name}")
        current = current[part]
    return current


class Orchestrator:
    """Execute independent nodes concurrently and persist every transition."""

    def __init__(
        self,
        graph: GraphSpec,
        *,
        state_path: Optional[Path] = None,
        max_parallel: Optional[int] = None,
    ) -> None:
        self.graph = graph
        if state_path is not None:
            resolved_state = state_path.expanduser().resolve()
            if (
                resolved_state != graph.workspace
                and graph.workspace not in resolved_state.parents
            ):
                raise GraphError("state override must stay inside graph workspace")
            self.state_path = resolved_state
        else:
            self.state_path = graph.resolve_path(graph.state_file)
        self.logs_dir = graph.resolve_path(graph.logs_dir)
        self.max_parallel = max_parallel or graph.max_parallel
        if self.max_parallel < 1:
            raise GraphError("max_parallel must be positive")
        self.state: Dict[str, Any] = {}
        self._lock: Optional[asyncio.Lock] = None
        self._flock_handle: Optional[IO[bytes]] = None
        self._version_cache: Dict[str, Optional[str]] = {}
        self._children = self._build_children()

    def _build_children(self) -> Dict[str, Set[str]]:
        children: Dict[str, Set[str]] = {node.id: set() for node in self.graph.nodes}
        for node in self.graph.nodes:
            for dependency in node.depends_on:
                children[dependency].add(node.id)
        return children

    def _new_state(self) -> Dict[str, Any]:
        timestamp = _now()
        return {
            "schema_version": 1,
            "project_id": self.graph.project_id,
            "graph_sha256": self.graph.graph_sha256,
            "graph_file": str(self.graph.graph_path),
            "status": PENDING,
            "cycle": 1,
            "cycle_agent_seconds": 0.0,
            "max_cycles": self.graph.max_cycles,
            "created_at": timestamp,
            "updated_at": timestamp,
            "nodes": {
                node.id: {
                    "status": PENDING,
                    "attempts": 0,
                    "started_at": None,
                    "finished_at": None,
                    "exit_code": None,
                    "error": None,
                    "logs": [],
                }
                for node in self.graph.nodes
            },
            "events": [],
        }

    def _save(self) -> None:
        self.state["updated_at"] = _now()
        _atomic_write_json(self.state_path, self.state)

    def _charge_agent_seconds(self, kind: str, duration: float) -> None:
        """Accumulate wall-clock seconds spent inside agent executions.

        Callers must hold self._lock and call self._save() afterwards. Only
        agent kinds are metered: they are the LLM invocations that cost money.
        """
        if kind != "agent":
            return
        self.state["cycle_agent_seconds"] = float(
            self.state.get("cycle_agent_seconds", 0.0)
        ) + duration

    def _agent_budget_exceeded(self, node: NodeSpec) -> bool:
        """True when the per-cycle agent budget forbids starting this node."""
        budget = self.graph.budget
        if budget is None or budget.max_agent_seconds_per_cycle is None:
            return False
        kind = node.kind
        if kind == "foreach" and node.task_template is not None:
            kind = node.task_template.kind
        if kind != "agent":
            return False
        spent = float(self.state.get("cycle_agent_seconds", 0.0))
        return spent >= budget.max_agent_seconds_per_cycle

    def _event(self, event: str, node_id: Optional[str] = None, **detail: Any) -> None:
        record: Dict[str, Any] = {"timestamp": _now(), "event": event}
        if node_id is not None:
            record["node_id"] = node_id
        record.update(detail)
        events = self.state.setdefault("events", [])
        events.append(record)
        if len(events) > 2000:
            del events[:-2000]

    def _descendants(self, roots: Iterable[str]) -> Set[str]:
        result: Set[str] = set()
        queue = list(roots)
        while queue:
            current = queue.pop()
            for child in self._children[current]:
                if child not in result:
                    result.add(child)
                    queue.append(child)
        return result

    def _reset_node_record(self, node_id: str, reason: str) -> None:
        record = self.state["nodes"][node_id]
        record.update(
            {
                "status": PENDING,
                "started_at": None,
                "finished_at": None,
                "exit_code": None,
                "error": reason,
            }
        )
        self._event("node_reset", node_id, reason=reason)

    def prepare(self) -> Dict[str, Any]:
        """Load state, recover interrupted nodes, and invalidate stale descendants."""
        if self.state_path.exists():
            self.state = _read_json(self.state_path)
            if self.state.get("graph_sha256") != self.graph.graph_sha256:
                raise GraphError(
                    "graph changed since this state was created; use a new state file "
                    "or reset it explicitly"
                )
            state_nodes = self.state.get("nodes")
            if not isinstance(state_nodes, dict):
                raise GraphError("state.nodes must be an object")
            if set(state_nodes) != set(self.graph.node_map):
                raise GraphError("state node ids do not match graph node ids")
        else:
            self.state = self._new_state()
            self._event("graph_created")

        invalid_roots: Set[str] = set()
        for node in self.graph.nodes:
            record = self.state["nodes"][node.id]
            status = record.get("status")
            if status == RUNNING:
                invalid_roots.add(node.id)
                self._reset_node_record(node.id, "recovered after interrupted runner")
            elif status == SUCCEEDED:
                missing = self._missing_outputs(node)
                if not missing and node.kind == "foreach":
                    missing = self._missing_task_outputs(record)
                if missing:
                    invalid_roots.add(node.id)
                    self._reset_node_record(
                        node.id,
                        f"declared outputs disappeared: {', '.join(missing)}",
                    )
        for node_id in sorted(self._descendants(invalid_roots)):
            if self.state["nodes"][node_id].get("status") in TERMINAL:
                self._reset_node_record(
                    node_id, "upstream output was invalidated during recovery"
                )
        self._save()
        return self.state

    def _missing_task_outputs(self, record: Mapping[str, Any]) -> List[str]:
        """Collect previously recorded per-task outputs that disappeared."""
        missing: List[str] = []
        for task_record in record.get("tasks", {}).values():
            for relative in task_record.get("outputs", []):
                try:
                    resolved = self.graph.resolve_path(relative)
                except GraphError:
                    missing.append(relative)
                    continue
                if not _artifact_valid(resolved):
                    missing.append(relative)
        return missing

    def _missing_inputs(self, node: NodeSpec) -> List[str]:
        return [
            relative
            for relative in node.inputs
            if not _artifact_valid(self.graph.resolve_path(relative))
        ]

    def _missing_outputs(self, node: NodeSpec) -> List[str]:
        return [
            relative
            for relative in node.outputs
            if not _artifact_valid(self.graph.resolve_path(relative))
        ]

    def _condition_matches(self, node: NodeSpec) -> bool:
        if node.when is None:
            return True
        condition_path = self.graph.resolve_path(node.when.path)
        if not condition_path.is_file():
            raise GraphError(
                f"node {node.id!r} condition file is missing: {node.when.path}"
            )
        try:
            data = _read_json(condition_path)
        except (OSError, json.JSONDecodeError) as exc:
            raise GraphError(
                f"node {node.id!r} condition file is invalid: {exc}"
            ) from exc
        actual = _lookup_field(data, node.when.field)
        return actual in node.when.values

    async def _transition(
        self, node_id: str, status: str, event: str, **updates: Any
    ) -> None:
        if self._lock is None:  # pragma: no cover - internal API guard
            raise RuntimeError("orchestrator lock is not initialized")
        async with self._lock:
            record = self.state["nodes"][node_id]
            record["status"] = status
            record.update(updates)
            self._event(event, node_id, **updates)
            self._save()

    def _build_prompt(
        self,
        node: NodeSpec,
        task: Optional[Mapping[str, Any]] = None,
        prior_error: Optional[str] = None,
    ) -> str:
        assert node.prompt_file is not None
        prompt_path = self.graph.resolve_path(node.prompt_file)
        prompt_body = prompt_path.read_text(encoding="utf-8")
        envelope = [
            "# AutoResearcher isolated agent node",
            "",
            f"- node_id: {node.id}",
            f"- project_id: {self.graph.project_id}",
            f"- cycle: {self.state.get('cycle', 1)}",
            f"- responsibility: {node.description or node.kind}",
            f"- workspace: {self.graph.workspace}",
            f"- workdir: {self.graph.resolve_path(node.workdir)}",
            f"- declared inputs: {json.dumps(node.inputs, ensure_ascii=False)}",
            f"- optional inputs (read when present): "
            f"{json.dumps(node.optional_inputs, ensure_ascii=False)}",
            f"- required outputs: {json.dumps(node.outputs, ensure_ascii=False)}",
        ]
        if task is not None:
            envelope.extend(
                [
                    f"- task: {json.dumps(task, ensure_ascii=False)}",
                    "",
                    "This node instance executes exactly one task from the "
                    "declared tasks file. Do not work on other tasks.",
                ]
            )
        if prior_error:
            envelope.extend(
                [
                    "",
                    "# Previous attempt failed",
                    "",
                    f"The previous attempt of this node failed with: {prior_error}",
                    "Diagnose that failure first and fix its cause; then produce "
                    "every required output. Do not repeat the same mistake.",
                ]
            )
        envelope.extend(
            [
                "",
                "Work only on this node's responsibility. Read declared inputs from disk. "
                "Do not rely on another agent's conversation state. Before finishing, "
                "create every required output as a non-empty file or directory. Do not "
                "start downstream work.",
                "",
                "# Role instructions",
                "",
                prompt_body.rstrip(),
                "",
            ]
        )
        return "\n".join(envelope)

    def _command_for(
        self, node: NodeSpec, prompt: str, last_message: Path
    ) -> Tuple[Tuple[str, ...], str, Mapping[str, str]]:
        adapter: Optional[AdapterSpec] = None
        if node.adapter is not None:
            adapter = self.graph.adapters[node.adapter]
        template = node.command or (adapter.command if adapter is not None else ())
        prompt_mode = node.prompt_mode or (
            adapter.prompt_mode if adapter is not None else "none"
        )
        values = {
            "workspace": str(self.graph.workspace),
            "workdir": str(self.graph.resolve_path(node.workdir)),
            "node_id": node.id,
            "prompt": prompt,
            "state_file": str(self.state_path),
            "output_last_message": str(last_message),
        }
        command_items: List[str] = []
        for item in template:
            expanded = item
            # Replace only the framework's exact placeholders. str.format
            # cannot be used because legitimate commands and inline Python
            # frequently contain unrelated JSON/dict braces.
            for key, value in values.items():
                expanded = expanded.replace("{" + key + "}", value)
            command_items.append(expanded)
        command = tuple(command_items)
        adapter_env = adapter.env if adapter is not None else {}
        env = dict(adapter_env)
        env.update(node.env)
        return command, prompt_mode, env

    async def _terminate_process(self, process: asyncio.subprocess.Process) -> None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        try:
            await asyncio.wait_for(process.wait(), timeout=5)
        except asyncio.TimeoutError:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            await process.wait()

    async def _probe_adapter_version(
        self, command: Tuple[str, ...]
    ) -> Optional[str]:
        """Best-effort ``<executable> --version`` probe, cached per executable.

        Never raises and never blocks a node: a missing or non-cooperating
        CLI simply yields None. This closes the provenance gap so artifacts
        carry which agent CLI generated them.
        """
        if not command:
            return None
        executable = command[0]
        if executable in self._version_cache:
            return self._version_cache[executable]
        try:
            process = await asyncio.create_subprocess_exec(
                executable,
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                start_new_session=True,
            )
        except (FileNotFoundError, OSError):
            self._version_cache[executable] = None
            return None
        try:
            output, _ = await asyncio.wait_for(process.communicate(), timeout=10)
        except asyncio.TimeoutError:
            await self._terminate_process(process)
            self._version_cache[executable] = None
            return None
        for line in output.decode("utf-8", errors="replace").splitlines():
            stripped = line.strip()
            if stripped:
                self._version_cache[executable] = stripped
                return stripped
        self._version_cache[executable] = None
        return None

    def _collect_last_message(self, stdout_path: Path, last_message: Path) -> None:
        """Persist the tail of agent stdout as the node's final statement."""
        try:
            text = stdout_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return
        tail = text.strip()
        if not tail:
            return
        if len(tail) > 2000:
            tail = tail[-2000:]
        last_message.write_text(tail + "\n", encoding="utf-8")

    async def _execute_attempt(
        self,
        node: NodeSpec,
        attempt: int,
        task: Optional[Mapping[str, Any]] = None,
        prior_error: Optional[str] = None,
    ) -> Tuple[int, Optional[str], Dict[str, Any]]:
        cycle = int(self.state.get("cycle", 1))
        node_logs = self.logs_dir / f"cycle-{cycle}" / node.id
        node_logs.mkdir(parents=True, exist_ok=True)
        stdout_path = node_logs / f"attempt-{attempt}.stdout.log"
        stderr_path = node_logs / f"attempt-{attempt}.stderr.log"
        last_message = node_logs / f"attempt-{attempt}.last-message.txt"
        prompt = (
            self._build_prompt(node, task, prior_error)
            if node.prompt_file is not None
            else ""
        )
        command, prompt_mode, declared_env = self._command_for(
            node, prompt, last_message
        )
        if not command:
            return 2, "node resolved to an empty command", {
                "stdout": str(stdout_path),
                "stderr": str(stderr_path),
            }

        env = os.environ.copy()
        env.update(
            {
                "AUTORESEARCHER_NODE_ID": node.id,
                "AUTORESEARCHER_PROJECT_ID": self.graph.project_id,
                "AUTORESEARCHER_WORKSPACE": str(self.graph.workspace),
                "AUTORESEARCHER_STATE_FILE": str(self.state_path),
                "AUTORESEARCHER_INPUTS_JSON": json.dumps(node.inputs),
                "AUTORESEARCHER_OUTPUTS_JSON": json.dumps(node.outputs),
            }
        )
        if task is not None:
            env["AUTORESEARCHER_TASK_JSON"] = json.dumps(task, ensure_ascii=False)
        env.update(declared_env)
        input_bytes = prompt.encode("utf-8") if prompt_mode == "stdin" else None
        logs: Dict[str, Any] = {"stdout": str(stdout_path), "stderr": str(stderr_path)}
        if node.kind == "agent":
            # Provenance: record which adapter/command produced this attempt so
            # artifacts carry their "researcher" identity, not just their sha.
            logs["adapter"] = node.adapter
            logs["command"] = list(command)
            if command:
                version = await self._probe_adapter_version(command)
                if version is not None:
                    logs["adapter_version"] = version
        try:
            with stdout_path.open("wb") as stdout_handle, stderr_path.open(
                "wb"
            ) as stderr_handle:
                process = await asyncio.create_subprocess_exec(
                    *command,
                    cwd=str(self.graph.resolve_path(node.workdir)),
                    env=env,
                    stdin=(
                        asyncio.subprocess.PIPE
                        if prompt_mode == "stdin"
                        else asyncio.subprocess.DEVNULL
                    ),
                    stdout=stdout_handle,
                    stderr=stderr_handle,
                    start_new_session=True,
                )
                try:
                    await asyncio.wait_for(
                        process.communicate(input=input_bytes),
                        timeout=node.timeout_seconds,
                    )
                except asyncio.TimeoutError:
                    await self._terminate_process(process)
                    return (
                        124,
                        f"timed out after {node.timeout_seconds} seconds",
                        logs,
                    )
                returncode = process.returncode
        except FileNotFoundError as exc:
            return 127, f"executable not found: {exc.filename}", logs
        except OSError as exc:
            return 126, f"could not start command: {exc}", logs

        if returncode != 0:
            return returncode or 1, f"command exited with code {returncode}", logs
        missing = self._missing_outputs(node)
        if missing:
            return 1, f"declared outputs missing or empty: {', '.join(missing)}", logs
        schema_errors = self._schema_violations(node)
        if schema_errors:
            return (
                1,
                "output contract violated: " + "; ".join(schema_errors[:20]),
                logs,
            )
        self._collect_last_message(stdout_path, last_message)
        logs["last_message"] = str(last_message)
        return 0, None, logs

    def _schema_violations(self, node: NodeSpec) -> List[str]:
        violations: List[str] = []
        for output_path, schema_relative in node.output_schemas.items():
            artifact = self.graph.resolve_path(output_path)
            schema_file = self.graph.resolve_path(schema_relative)
            for message in validate_file(artifact, schema_file):
                violations.append(f"{output_path}: {message}")
        return violations

    def _load_tasks(self, node: NodeSpec) -> List[Dict[str, Any]]:
        assert node.tasks_file is not None
        tasks_path = self.graph.resolve_path(node.tasks_file)
        try:
            raw = json.loads(tasks_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise GraphError(f"tasks file is invalid: {node.tasks_file}: {exc}")
        items = raw.get("tasks") if isinstance(raw, dict) else raw
        if not isinstance(items, list) or not items:
            raise GraphError(
                f"tasks file must contain a non-empty task array: {node.tasks_file}"
            )
        seen: Set[str] = set()
        tasks: List[Dict[str, Any]] = []
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                raise GraphError(f"task[{index}] must be an object")
            task_id = item.get("id")
            if not isinstance(task_id, str) or not TASK_ID_RE.fullmatch(task_id):
                raise GraphError(
                    f"task[{index}].id must match {TASK_ID_RE.pattern!r}"
                )
            if task_id in seen:
                raise GraphError(f"duplicate task id: {task_id!r}")
            seen.add(task_id)
            tasks.append(item)
        return tasks

    def _task_node(self, node: NodeSpec, task: Mapping[str, Any]) -> NodeSpec:
        """Build a synthetic NodeSpec for one task by placeholder substitution."""
        template: TaskTemplateSpec = node.task_template  # type: ignore[assignment]
        assert template is not None
        command = tuple(_substitute_task(item, task) for item in template.command)
        outputs = tuple(_substitute_task(item, task) for item in template.outputs)
        output_schemas = {
            _substitute_task(output, task): schema
            for output, schema in template.output_schemas.items()
        }
        env = {
            key: _substitute_task(value, task)
            for key, value in template.env.items()
        }
        for relative in outputs:
            # resolve_path raises GraphError when a substituted path escapes.
            self.graph.resolve_path(relative)
        return NodeSpec(
            id=f"{node.id}--{task['id']}",
            kind=template.kind,
            depends_on=(),
            command=command,
            adapter=template.adapter,
            prompt_file=template.prompt_file,
            prompt_mode=template.prompt_mode,
            workdir=template.workdir,
            inputs=node.inputs,
            optional_inputs=node.optional_inputs,
            outputs=outputs,
            output_schemas=output_schemas,
            timeout_seconds=template.timeout_seconds,
            retries=template.retries,
            env=env,
            description=f"{node.description or node.kind} [task {task['id']}]",
        )

    async def _run_foreach_task(
        self,
        node: NodeSpec,
        task: Mapping[str, Any],
        semaphore: asyncio.Semaphore,
    ) -> bool:
        if self._lock is None:  # pragma: no cover - internal API guard
            raise RuntimeError("orchestrator lock is not initialized")
        task_id = str(task["id"])
        try:
            synthetic = self._task_node(node, task)
        except GraphError as exc:
            async with self._lock:
                tasks_state = self.state["nodes"][node.id].setdefault("tasks", {})
                tasks_state[task_id] = {
                    "status": FAILED,
                    "attempts": 0,
                    "exit_code": 2,
                    "error": str(exc),
                    "outputs": [],
                    "logs": [],
                }
                self._save()
            return False
        async with self._lock:
            tasks_state = self.state["nodes"][node.id].setdefault("tasks", {})
            record = tasks_state.setdefault(
                task_id,
                {
                    "status": PENDING,
                    "attempts": 0,
                    "exit_code": None,
                    "error": None,
                    "outputs": list(synthetic.outputs),
                    "logs": [],
                },
            )
            record["outputs"] = list(synthetic.outputs)
            already_done = record.get("status") == SUCCEEDED and not [
                relative
                for relative in synthetic.outputs
                if not _artifact_valid(self.graph.resolve_path(relative))
            ]
            if not already_done:
                record["status"] = RUNNING
                self._save()
        if already_done:
            return True

        for _ in range(synthetic.retries + 1):
            async with self._lock:
                record["attempts"] = int(record.get("attempts", 0)) + 1
                attempt = record["attempts"]
                prior_error = record.get("error")
                self._save()
            attempt_started = time.monotonic()
            async with semaphore:
                exit_code, error, logs = await self._execute_attempt(
                    synthetic, attempt, task=task, prior_error=prior_error
                )
            duration = time.monotonic() - attempt_started
            async with self._lock:
                record["logs"].append(logs)
                record["exit_code"] = exit_code
                record["error"] = error
                record["status"] = SUCCEEDED if exit_code == 0 else FAILED
                self._charge_agent_seconds(synthetic.kind, duration)
                self._event(
                    "task_finished",
                    node.id,
                    task_id=task_id,
                    status=record["status"],
                    exit_code=exit_code,
                    error=error,
                )
                self._save()
            if exit_code == 0:
                return True
            if record["attempts"] <= synthetic.retries:
                await asyncio.sleep(min(2 ** (record["attempts"] - 1), 10))
        return False

    async def _run_foreach(self, node: NodeSpec) -> bool:
        await self._transition(
            node.id,
            RUNNING,
            "node_started",
            attempts=int(self.state["nodes"][node.id].get("attempts", 0)) + 1,
            started_at=_now(),
            finished_at=None,
            exit_code=None,
            error=None,
        )
        try:
            tasks = self._load_tasks(node)
        except GraphError as exc:
            await self._transition(
                node.id,
                FAILED,
                "node_failed",
                exit_code=2,
                error=str(exc),
                finished_at=_now(),
            )
            return False
        semaphore = asyncio.Semaphore(node.task_parallel)
        results = await asyncio.gather(
            *[self._run_foreach_task(node, task, semaphore) for task in tasks]
        )
        failed = [
            str(task["id"])
            for task, ok in zip(tasks, results)
            if not ok
        ]
        if failed:
            await self._transition(
                node.id,
                FAILED,
                "node_failed",
                exit_code=1,
                error=f"tasks failed: {', '.join(failed)}",
                finished_at=_now(),
            )
            return False
        missing = self._missing_outputs(node)
        if missing:
            await self._transition(
                node.id,
                FAILED,
                "node_failed",
                exit_code=1,
                error=f"declared outputs missing or empty: {', '.join(missing)}",
                finished_at=_now(),
            )
            return False
        await self._transition(
            node.id,
            SUCCEEDED,
            "node_succeeded",
            exit_code=0,
            error=None,
            finished_at=_now(),
        )
        return True

    async def _run_node(self, node: NodeSpec) -> bool:
        if node.kind == "foreach":
            return await self._run_foreach(node)
        last_error: Optional[str] = None
        for _ in range(node.retries + 1):
            current_attempt = int(self.state["nodes"][node.id].get("attempts", 0)) + 1
            await self._transition(
                node.id,
                RUNNING,
                "node_started",
                attempts=current_attempt,
                started_at=_now(),
                finished_at=None,
                exit_code=None,
                error=None,
            )
            attempt_started = time.monotonic()
            exit_code, error, logs = await self._execute_attempt(
                node, current_attempt, prior_error=last_error
            )
            duration = time.monotonic() - attempt_started
            if self._lock is None:  # pragma: no cover - internal API guard
                raise RuntimeError("orchestrator lock is not initialized")
            async with self._lock:
                self.state["nodes"][node.id].setdefault("logs", []).append(logs)
                self._charge_agent_seconds(node.kind, duration)
                self._save()
            if exit_code == 0:
                await self._transition(
                    node.id,
                    SUCCEEDED,
                    "node_succeeded",
                    exit_code=0,
                    error=None,
                    finished_at=_now(),
                )
                return True
            await self._transition(
                node.id,
                FAILED,
                "node_attempt_failed",
                exit_code=exit_code,
                error=error,
                finished_at=_now(),
            )
            last_error = error
            if current_attempt <= node.retries:
                await self._transition(
                    node.id,
                    PENDING,
                    "node_retry_scheduled",
                    error=error,
                )
                await asyncio.sleep(min(2 ** (current_attempt - 1), 10))
        return False

    def _acquire_file_lock(self) -> bool:
        """Take an exclusive advisory lock so two runners cannot share a state."""
        if self._flock_handle is not None:
            return False
        lock_path = self.state_path.parent / (self.state_path.name + ".lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = lock_path.open("ab")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            raise GraphError(
                f"another orchestrator already holds this state: {self.state_path}"
            )
        self._flock_handle = handle
        return True

    def _release_file_lock(self) -> None:
        if self._flock_handle is None:
            return
        try:
            fcntl.flock(self._flock_handle.fileno(), fcntl.LOCK_UN)
        finally:
            self._flock_handle.close()
            self._flock_handle = None

    async def run(self) -> Dict[str, Any]:
        """Run or resume the graph until all reachable nodes are terminal."""
        acquired = self._acquire_file_lock()
        try:
            return await self._run_locked()
        finally:
            if acquired:
                self._release_file_lock()

    async def _run_locked(self) -> Dict[str, Any]:
        # asyncio primitives bind to the active loop on Python 3.9. Create the
        # lock here so one Orchestrator can be constructed outside asyncio.run
        # and can also be resumed in a later event loop.
        self._lock = asyncio.Lock()
        self.prepare()
        gate = self._resolve_human_gate()
        if gate in {"wait", "done"}:
            return self.state
        self.state["status"] = RUNNING
        self._event("graph_started", max_parallel=self.max_parallel)
        self._save()

        running: Dict[asyncio.Task[bool], Tuple[str, Set[str]]] = {}
        held_resources: Set[str] = set()
        node_map = self.graph.node_map

        while True:
            progress = False
            for node in self.graph.nodes:
                record = self.state["nodes"][node.id]
                if record["status"] != PENDING:
                    continue
                dependency_states = [
                    self.state["nodes"][dependency]["status"]
                    for dependency in node.depends_on
                ]
                if any(status in {FAILED, BLOCKED} for status in dependency_states):
                    await self._transition(
                        node.id,
                        BLOCKED,
                        "node_blocked",
                        error="one or more dependencies failed",
                        finished_at=_now(),
                    )
                    progress = True
                    continue
                if not all(status in SATISFIED for status in dependency_states):
                    continue
                try:
                    matches = self._condition_matches(node)
                except GraphError as exc:
                    await self._transition(
                        node.id,
                        FAILED,
                        "node_failed",
                        exit_code=2,
                        error=str(exc),
                        finished_at=_now(),
                    )
                    progress = True
                    continue
                if not matches:
                    await self._transition(
                        node.id,
                        SKIPPED,
                        "node_skipped",
                        error="when condition evaluated to false",
                        finished_at=_now(),
                    )
                    progress = True
                    continue
                missing_inputs = self._missing_inputs(node)
                if missing_inputs:
                    await self._transition(
                        node.id,
                        FAILED,
                        "node_failed",
                        exit_code=2,
                        error=(
                            "declared inputs missing or empty: "
                            + ", ".join(missing_inputs)
                        ),
                        finished_at=_now(),
                    )
                    progress = True
                    continue
                if node.kind == "barrier":
                    await self._transition(
                        node.id,
                        SUCCEEDED,
                        "barrier_satisfied",
                        exit_code=0,
                        error=None,
                        started_at=_now(),
                        finished_at=_now(),
                    )
                    progress = True
                    continue
                if self._agent_budget_exceeded(node):
                    await self._transition(
                        node.id,
                        BLOCKED,
                        "node_budget_blocked",
                        error=(
                            "cycle agent budget exhausted: "
                            f"{self.state.get('cycle_agent_seconds', 0.0):.0f}s "
                            f"spent of "
                            f"{self.graph.budget.max_agent_seconds_per_cycle}s"
                        ),
                        finished_at=_now(),
                    )
                    progress = True
                    continue
                if len(running) >= self.max_parallel:
                    continue
                resources = set(node.exclusive_resources)
                if resources & held_resources:
                    continue
                task = asyncio.create_task(self._run_node(node))
                running[task] = (node.id, resources)
                held_resources.update(resources)
                progress = True

            if running:
                done, _ = await asyncio.wait(
                    running, return_when=asyncio.FIRST_COMPLETED
                )
                for task in done:
                    node_id, resources = running.pop(task)
                    held_resources.difference_update(resources)
                    try:
                        task.result()
                    except Exception as exc:  # pragma: no cover - defensive boundary
                        await self._transition(
                            node_id,
                            FAILED,
                            "node_failed",
                            exit_code=1,
                            error=f"internal runner error: {exc}",
                            finished_at=_now(),
                        )
                continue

            pending = [
                node_id
                for node_id, record in self.state["nodes"].items()
                if record["status"] == PENDING
            ]
            if pending:
                for node_id in pending:
                    await self._transition(
                        node_id,
                        BLOCKED,
                        "node_blocked",
                        error="scheduler stalled; dependencies cannot be satisfied",
                        finished_at=_now(),
                    )
                break
            if not progress:
                break

        statuses = {
            node_id: record["status"]
            for node_id, record in self.state["nodes"].items()
        }
        if any(status == FAILED for status in statuses.values()):
            final_status = FAILED
        elif any(status == BLOCKED for status in statuses.values()):
            final_status = BLOCKED
        else:
            final_status = SUCCEEDED
        self.state["status"] = final_status
        self.state["finished_at"] = _now()
        self._event("graph_finished", status=final_status)
        self._save()
        if final_status == SUCCEEDED and self.graph.cycle_control is not None:
            cycle_control = self.graph.cycle_control
            decision_path = self.graph.resolve_path(cycle_control.decision_path)
            try:
                decision_data = _read_json(decision_path)
                decision = _lookup_field(
                    decision_data, cycle_control.decision_field
                )
            except (OSError, json.JSONDecodeError, GraphError) as exc:
                self.state["status"] = FAILED
                self._event("cycle_decision_failed", error=str(exc))
                self._save()
                return self.state
            if decision in cycle_control.human_values:
                self.state["status"] = AWAITING_HUMAN
                self._event(
                    "human_required",
                    decision=decision,
                    decision_file=cycle_control.human_decision_path,
                )
                self._save()
                return self.state
            if decision in cycle_control.repeat_values:
                if not self._advance_cycle(decision):
                    return self.state
                return await self._run_locked()
            if decision not in cycle_control.terminal_values:
                self.state["status"] = FAILED
                self._event(
                    "cycle_decision_failed",
                    error=f"unknown cycle decision: {decision!r}",
                )
                self._save()
        return self.state

    def _advance_cycle(self, decision: Any) -> bool:
        """Archive the finished cycle and reset the configured subgraph."""
        cycle_control = self.graph.cycle_control
        assert cycle_control is not None
        cycle = int(self.state.get("cycle", 1))
        if cycle >= self.graph.max_cycles:
            self.state["status"] = BLOCKED
            self._event(
                "max_cycles_reached",
                cycle=cycle,
                decision=decision,
                max_cycles=self.graph.max_cycles,
            )
            self._save()
            return False
        archive_path = (
            self.state_path.parent / "cycles" / f"cycle-{cycle}.state.json"
        )
        _atomic_write_json(archive_path, self.state)
        # The agent decision file (rationale, unresolved items, next scope) is
        # overwritten by the next cycle, so archive a copy alongside the state
        # snapshot — symmetric with cycle-N.human-decision.json. Copy, do not
        # move: the next cycle's planning node still reads the live file.
        decision_archive: Optional[str] = None
        decision_file = self.graph.resolve_path(cycle_control.decision_path)
        if decision_file.is_file():
            decision_archive_path = (
                self.state_path.parent
                / "cycles"
                / f"cycle-{cycle}.decision.json"
            )
            decision_archive_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(decision_file, decision_archive_path)
            decision_archive = str(decision_archive_path)
        reset_roots = (
            cycle_control.repeat_reset.get(decision)
            if isinstance(decision, str)
            else None
        )
        if reset_roots is None:
            reset_targets = {node.id for node in self.graph.nodes}
        else:
            reset_targets = set(reset_roots) | self._descendants(reset_roots)
        for node in self.graph.nodes:
            if node.id not in reset_targets:
                continue
            record = self.state["nodes"][node.id]
            record.update(
                {
                    "status": PENDING,
                    "attempts": 0,
                    "started_at": None,
                    "finished_at": None,
                    "exit_code": None,
                    "error": None,
                    "logs": [],
                    "tasks": {},
                }
            )
        self.state["cycle"] = cycle + 1
        self.state["status"] = PENDING
        self.state["cycle_agent_seconds"] = 0.0
        self.state.pop("finished_at", None)
        self._event(
            "cycle_advanced",
            from_cycle=cycle,
            to_cycle=cycle + 1,
            decision=decision,
            reset_nodes=sorted(reset_targets),
            archive=str(archive_path),
            archive_decision=decision_archive,
        )
        self._save()
        return True

    def _resolve_human_gate(self) -> str:
        """Consume a pending human decision. Returns wait / done / resumed / none."""
        cycle_control = self.graph.cycle_control
        if (
            self.state.get("status") != AWAITING_HUMAN
            or cycle_control is None
            or cycle_control.human_decision_path is None
        ):
            return "none"
        decision_file = self.graph.resolve_path(
            cycle_control.human_decision_path
        )
        if not decision_file.is_file():
            self._event(
                "human_pending",
                decision_file=cycle_control.human_decision_path,
            )
            self._save()
            return "wait"
        try:
            data = _read_json(decision_file)
            action = _lookup_field(data, cycle_control.decision_field)
        except (OSError, json.JSONDecodeError, GraphError) as exc:
            self._event("human_decision_invalid", error=str(exc))
            self._save()
            return "wait"
        if action in cycle_control.human_values or (
            action not in cycle_control.repeat_values
            and action not in cycle_control.terminal_values
        ):
            self._event(
                "human_decision_invalid",
                error=f"human decision must resolve the gate: {action!r}",
            )
            self._save()
            return "wait"
        cycle = int(self.state.get("cycle", 1))
        archive_path = (
            self.state_path.parent
            / "cycles"
            / f"cycle-{cycle}.human-decision.json"
        )
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        os.replace(str(decision_file), str(archive_path))
        self._event(
            "human_decision_applied",
            action=action,
            archive=str(archive_path),
        )
        if action in cycle_control.repeat_values:
            if not self._advance_cycle(action):
                return "done"
            return "resumed"
        self.state["status"] = SUCCEEDED
        self.state["finished_at"] = _now()
        self._save()
        return "done"


def reset_nodes(
    graph: GraphSpec,
    node_ids: Iterable[str],
    *,
    state_path: Optional[Path] = None,
    include_downstream: bool = True,
) -> Dict[str, Any]:
    """Reset selected nodes in a persisted state so they can be rerun."""
    runner = Orchestrator(graph, state_path=state_path)
    runner.prepare()
    requested = set(node_ids)
    unknown = requested - set(graph.node_map)
    if unknown:
        raise GraphError(f"unknown reset nodes: {sorted(unknown)}")
    targets = set(requested)
    if include_downstream:
        targets.update(runner._descendants(requested))
    for node_id in sorted(targets):
        runner._reset_node_record(node_id, "explicitly reset by operator")
    runner.state["status"] = PENDING
    runner.state.pop("finished_at", None)
    runner._event("graph_reset", nodes=sorted(targets))
    runner._save()
    return runner.state
