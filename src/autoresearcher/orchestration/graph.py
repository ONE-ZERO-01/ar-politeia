"""Schema loading and validation for executable multi-agent research graphs."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple


NODE_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$")
TASK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
VALID_KINDS = {"agent", "command", "gate", "barrier", "foreach"}
VALID_TASK_KINDS = {"agent", "command", "gate"}
VALID_PROMPT_MODES = {"stdin", "argument", "none"}


class GraphError(ValueError):
    """Raised when a graph cannot be executed safely."""


@dataclass(frozen=True)
class AdapterSpec:
    name: str
    command: Tuple[str, ...]
    prompt_mode: str = "stdin"
    env: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ConditionSpec:
    path: str
    field: str
    values: Tuple[Any, ...]


@dataclass(frozen=True)
class CycleControlSpec:
    decision_path: str
    decision_field: str
    repeat_values: Tuple[Any, ...]
    terminal_values: Tuple[Any, ...]
    # Optional mapping decision value -> reset root node ids. When a repeat
    # decision has an entry here, only those roots and their descendants are
    # reset for the next cycle; other nodes keep their SUCCEEDED state.
    repeat_reset: Mapping[str, Tuple[str, ...]] = field(default_factory=dict)
    # Decision values that pause the graph in AWAITING_HUMAN instead of
    # finishing. Must be a subset of terminal_values.
    human_values: Tuple[Any, ...] = ()
    # File the human writes their decision into (same decision_field). Read on
    # the next `run` to resume, finish, or keep waiting.
    human_decision_path: Optional[str] = None


@dataclass(frozen=True)
class BudgetSpec:
    """Per-cycle spend guard. Agent nodes are the costly LLM invocations, so
    the runner refuses to start new agent executions once the accumulated
    agent wall-clock time in the current cycle reaches this limit."""

    max_agent_seconds_per_cycle: Optional[int] = None


@dataclass(frozen=True)
class TaskTemplateSpec:
    """Per-task execution template for foreach nodes.

    String fields may contain `{task.<key>}` / `{task_id}` placeholders that
    are substituted from each task object at runtime.
    """

    kind: str
    command: Tuple[str, ...] = ()
    adapter: Optional[str] = None
    prompt_file: Optional[str] = None
    prompt_mode: Optional[str] = None
    workdir: str = "."
    outputs: Tuple[str, ...] = ()
    output_schemas: Mapping[str, str] = field(default_factory=dict)
    timeout_seconds: int = 3600
    retries: int = 0
    env: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class NodeSpec:
    id: str
    kind: str
    depends_on: Tuple[str, ...]
    command: Tuple[str, ...] = ()
    adapter: Optional[str] = None
    prompt_file: Optional[str] = None
    prompt_mode: Optional[str] = None
    workdir: str = "."
    inputs: Tuple[str, ...] = ()
    # Inputs that are read when present but never block node start. Used to
    # feed prior-cycle artifacts (strategy decisions, reviews) into a rerun.
    optional_inputs: Tuple[str, ...] = ()
    outputs: Tuple[str, ...] = ()
    # Mapping output path -> JSON schema file (relative to workspace). The
    # runner validates the produced JSON before marking the node SUCCEEDED.
    output_schemas: Mapping[str, str] = field(default_factory=dict)
    timeout_seconds: int = 3600
    retries: int = 0
    env: Mapping[str, str] = field(default_factory=dict)
    exclusive_resources: Tuple[str, ...] = ()
    when: Optional[ConditionSpec] = None
    description: str = ""
    # foreach nodes: JSON file listing task objects and the execution template.
    tasks_file: Optional[str] = None
    task_template: Optional[TaskTemplateSpec] = None
    # Concurrent tasks inside one foreach node (the node itself occupies one
    # scheduler slot).
    task_parallel: int = 1


@dataclass(frozen=True)
class GraphSpec:
    schema_version: int
    project_id: str
    graph_path: Path
    workspace: Path
    state_file: str
    logs_dir: str
    max_parallel: int
    max_cycles: int
    graph_sha256: str
    adapters: Mapping[str, AdapterSpec]
    nodes: Tuple[NodeSpec, ...]
    cycle_control: Optional[CycleControlSpec] = None
    budget: Optional[BudgetSpec] = None

    @property
    def node_map(self) -> Dict[str, NodeSpec]:
        return {node.id: node for node in self.nodes}

    def resolve_path(self, relative: str) -> Path:
        return _resolve_inside(self.workspace, relative, "declared path")


def _expect_dict(value: Any, label: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise GraphError(f"{label} must be an object")
    return value


def _expect_string(value: Any, label: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise GraphError(f"{label} must be a non-empty string")
    return value


def _string_list(value: Any, label: str) -> Tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise GraphError(f"{label} must be an array")
    result: List[str] = []
    for index, item in enumerate(value):
        result.append(_expect_string(item, f"{label}[{index}]"))
    if len(result) != len(set(result)):
        raise GraphError(f"{label} must not contain duplicates")
    return tuple(result)


def _string_mapping(value: Any, label: str) -> Mapping[str, str]:
    if value is None:
        return {}
    data = _expect_dict(value, label)
    result: Dict[str, str] = {}
    for key, item in data.items():
        result[_expect_string(key, f"{label} key")] = _expect_string(
            item, f"{label}.{key}", allow_empty=True
        )
    return result


def _relative_path(value: Any, label: str, *, allow_dot: bool = True) -> str:
    text = _expect_string(value, label)
    path = Path(text)
    if path.is_absolute() or ".." in path.parts:
        raise GraphError(f"{label} must stay inside the graph workspace")
    if not allow_dot and path == Path("."):
        raise GraphError(f"{label} must name a file or directory")
    return text


def _resolve_inside(root: Path, relative: str, label: str) -> Path:
    path = (root / relative).resolve()
    if path != root and root not in path.parents:
        raise GraphError(f"{label} escapes graph workspace: {relative}")
    return path


def _positive_int(value: Any, label: str, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise GraphError(f"{label} must be a positive integer")
    return value


def _nonnegative_int(value: Any, label: str, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise GraphError(f"{label} must be a non-negative integer")
    return value


def _load_condition(value: Any, label: str) -> Optional[ConditionSpec]:
    if value is None:
        return None
    data = _expect_dict(value, label)
    path = _relative_path(data.get("path"), f"{label}.path", allow_dot=False)
    field_name = _expect_string(data.get("field"), f"{label}.field")
    has_equals = "equals" in data
    has_in = "in" in data
    if has_equals == has_in:
        raise GraphError(f"{label} must define exactly one of equals or in")
    if has_in:
        values = data["in"]
        if not isinstance(values, list) or not values:
            raise GraphError(f"{label}.in must be a non-empty array")
        return ConditionSpec(path=path, field=field_name, values=tuple(values))
    return ConditionSpec(path=path, field=field_name, values=(data["equals"],))


def _load_cycle_control(value: Any) -> Optional[CycleControlSpec]:
    if value is None:
        return None
    data = _expect_dict(value, "cycle_control")
    decision_path = _relative_path(
        data.get("decision_path"),
        "cycle_control.decision_path",
        allow_dot=False,
    )
    decision_field = _expect_string(
        data.get("decision_field", "action"),
        "cycle_control.decision_field",
    )
    repeat_values = data.get("repeat_values")
    terminal_values = data.get("terminal_values")
    if not isinstance(repeat_values, list) or not repeat_values:
        raise GraphError("cycle_control.repeat_values must be a non-empty array")
    if not isinstance(terminal_values, list) or not terminal_values:
        raise GraphError("cycle_control.terminal_values must be a non-empty array")
    if any(value in terminal_values for value in repeat_values):
        raise GraphError(
            "cycle_control repeat_values and terminal_values must be disjoint"
        )
    repeat_reset_value = data.get("repeat_reset")
    repeat_reset: Dict[str, Tuple[str, ...]] = {}
    if repeat_reset_value is not None:
        reset_data = _expect_dict(repeat_reset_value, "cycle_control.repeat_reset")
        for decision, roots in reset_data.items():
            if decision not in repeat_values:
                raise GraphError(
                    "cycle_control.repeat_reset keys must be repeat_values; "
                    f"unknown decision {decision!r}"
                )
            root_ids = _string_list(
                roots, f"cycle_control.repeat_reset.{decision}"
            )
            if not root_ids:
                raise GraphError(
                    f"cycle_control.repeat_reset.{decision} must not be empty"
                )
            repeat_reset[decision] = root_ids
    human_values_raw = data.get("human_values")
    human_values: Tuple[Any, ...] = ()
    if human_values_raw is not None:
        if not isinstance(human_values_raw, list):
            raise GraphError("cycle_control.human_values must be an array")
        unknown = [
            value for value in human_values_raw if value not in terminal_values
        ]
        if unknown:
            raise GraphError(
                "cycle_control.human_values must be a subset of "
                f"terminal_values; unknown: {unknown}"
            )
        human_values = tuple(human_values_raw)
    human_decision_path = data.get("human_decision_path")
    if human_decision_path is not None:
        human_decision_path = _relative_path(
            human_decision_path,
            "cycle_control.human_decision_path",
            allow_dot=False,
        )
    if human_values and human_decision_path is None:
        raise GraphError(
            "cycle_control.human_decision_path is required when "
            "human_values is set"
        )
    return CycleControlSpec(
        decision_path=decision_path,
        decision_field=decision_field,
        repeat_values=tuple(repeat_values),
        terminal_values=tuple(terminal_values),
        repeat_reset=repeat_reset,
        human_values=human_values,
        human_decision_path=human_decision_path,
    )


def _load_budget(value: Any) -> Optional[BudgetSpec]:
    if value is None:
        return None
    data = _expect_dict(value, "budget")
    unknown = set(data) - {"max_agent_seconds_per_cycle"}
    if unknown:
        raise GraphError(f"budget has unknown keys: {sorted(unknown)}")
    max_seconds = data.get("max_agent_seconds_per_cycle")
    if max_seconds is not None:
        max_seconds = _positive_int(
            max_seconds, "budget.max_agent_seconds_per_cycle", 0
        )
    return BudgetSpec(max_agent_seconds_per_cycle=max_seconds)


def _load_task_template(
    value: Any,
    label: str,
    adapters: Mapping[str, AdapterSpec],
    default_adapter: Optional[str],
) -> TaskTemplateSpec:
    data = _expect_dict(value, label)
    kind = data.get("kind", "command")
    if kind not in VALID_TASK_KINDS:
        raise GraphError(f"{label}.kind must be one of {sorted(VALID_TASK_KINDS)}")
    command = _string_list(data.get("command"), f"{label}.command")
    adapter = data.get("adapter")
    if adapter is not None:
        adapter = _expect_string(adapter, f"{label}.adapter")
    if kind == "agent" and adapter is None and not command:
        adapter = default_adapter
    if adapter is not None and adapter not in adapters:
        raise GraphError(f"{label}.adapter references unknown adapter {adapter!r}")
    if kind in {"command", "gate"} and not command:
        raise GraphError(f"{label}.command is required for kind={kind}")
    if kind == "agent" and not command and adapter is None:
        raise GraphError(f"{label} agent templates require command or adapter")
    prompt_file = data.get("prompt_file")
    if prompt_file is not None:
        prompt_file = _relative_path(
            prompt_file, f"{label}.prompt_file", allow_dot=False
        )
    if kind == "agent" and prompt_file is None:
        raise GraphError(f"{label}.prompt_file is required for agent templates")
    prompt_mode = data.get("prompt_mode")
    if prompt_mode is not None and prompt_mode not in VALID_PROMPT_MODES:
        raise GraphError(
            f"{label}.prompt_mode must be one of {sorted(VALID_PROMPT_MODES)}"
        )
    outputs = _string_list(data.get("outputs"), f"{label}.outputs")
    output_schemas_value = data.get("output_schemas")
    output_schemas: Dict[str, str] = {}
    if output_schemas_value is not None:
        schema_data = _expect_dict(output_schemas_value, f"{label}.output_schemas")
        for output_path, schema_path in schema_data.items():
            if output_path not in set(outputs):
                raise GraphError(
                    f"{label}.output_schemas key must be a declared template "
                    f"output: {output_path!r}"
                )
            if "{task" in schema_path:
                raise GraphError(
                    f"{label}.output_schemas values must be static paths"
                )
            output_schemas[output_path] = _relative_path(
                schema_path, f"{label}.output_schemas.{output_path}",
                allow_dot=False,
            )
    return TaskTemplateSpec(
        kind=kind,
        command=command,
        adapter=adapter,
        prompt_file=prompt_file,
        prompt_mode=prompt_mode,
        workdir=_relative_path(data.get("workdir", "."), f"{label}.workdir"),
        outputs=outputs,
        output_schemas=output_schemas,
        timeout_seconds=_positive_int(
            data.get("timeout_seconds"), f"{label}.timeout_seconds", 3600
        ),
        retries=_nonnegative_int(data.get("retries"), f"{label}.retries", 0),
        env=_string_mapping(data.get("env"), f"{label}.env"),
    )


def _load_adapter(name: str, value: Any) -> AdapterSpec:
    data = _expect_dict(value, f"adapters.{name}")
    command = _string_list(data.get("command"), f"adapters.{name}.command")
    if not command:
        raise GraphError(f"adapters.{name}.command must not be empty")
    prompt_mode = data.get("prompt_mode", "stdin")
    if prompt_mode not in VALID_PROMPT_MODES:
        raise GraphError(
            f"adapters.{name}.prompt_mode must be one of "
            f"{sorted(VALID_PROMPT_MODES)}"
        )
    if prompt_mode == "argument" and not any("{prompt}" in item for item in command):
        raise GraphError(
            f"adapters.{name}.command must contain {{prompt}} in argument mode"
        )
    return AdapterSpec(
        name=name,
        command=command,
        prompt_mode=prompt_mode,
        env=_string_mapping(data.get("env"), f"adapters.{name}.env"),
    )


def _load_node(
    value: Any,
    index: int,
    adapters: Mapping[str, AdapterSpec],
    default_adapter: Optional[str],
) -> NodeSpec:
    label = f"nodes[{index}]"
    data = _expect_dict(value, label)
    node_id = _expect_string(data.get("id"), f"{label}.id")
    if not NODE_ID_RE.fullmatch(node_id):
        raise GraphError(
            f"{label}.id must match {NODE_ID_RE.pattern!r}: {node_id!r}"
        )
    kind = data.get("kind", "agent")
    if kind not in VALID_KINDS:
        raise GraphError(f"{label}.kind must be one of {sorted(VALID_KINDS)}")

    command = _string_list(data.get("command"), f"{label}.command")
    adapter = data.get("adapter")
    if adapter is not None:
        adapter = _expect_string(adapter, f"{label}.adapter")
    if kind == "agent" and adapter is None and not command:
        adapter = default_adapter
    if adapter is not None and adapter not in adapters:
        raise GraphError(f"{label}.adapter references unknown adapter {adapter!r}")
    if kind in {"command", "gate"} and not command:
        raise GraphError(f"{label}.command is required for kind={kind}")
    if kind == "barrier" and (command or adapter is not None):
        raise GraphError(f"{label} barrier nodes cannot define command or adapter")
    if kind == "agent" and not command and adapter is None:
        raise GraphError(f"{label} agent nodes require command or adapter")
    if kind == "foreach" and (command or adapter is not None):
        raise GraphError(
            f"{label} foreach nodes define execution in task_template, "
            "not at node level"
        )

    tasks_file = data.get("tasks_file")
    task_template: Optional[TaskTemplateSpec] = None
    task_parallel = _positive_int(
        data.get("task_parallel"), f"{label}.task_parallel", 1
    )
    if kind == "foreach":
        tasks_file = _relative_path(
            tasks_file, f"{label}.tasks_file", allow_dot=False
        )
        if data.get("task_template") is None:
            raise GraphError(f"{label}.task_template is required for foreach")
        task_template = _load_task_template(
            data["task_template"], f"{label}.task_template", adapters,
            default_adapter,
        )
    elif data.get("tasks_file") is not None or data.get("task_template") is not None:
        raise GraphError(
            f"{label}.tasks_file/task_template are only valid for kind=foreach"
        )

    prompt_file = data.get("prompt_file")
    if prompt_file is not None:
        prompt_file = _relative_path(
            prompt_file, f"{label}.prompt_file", allow_dot=False
        )
    if kind == "agent" and prompt_file is None:
        raise GraphError(f"{label}.prompt_file is required for agent nodes")

    prompt_mode = data.get("prompt_mode")
    if prompt_mode is not None and prompt_mode not in VALID_PROMPT_MODES:
        raise GraphError(
            f"{label}.prompt_mode must be one of {sorted(VALID_PROMPT_MODES)}"
        )
    if kind == "agent" and command:
        effective_mode = prompt_mode or "stdin"
        if effective_mode == "argument" and not any(
            "{prompt}" in item for item in command
        ):
            raise GraphError(
                f"{label}.command must contain {{prompt}} in argument mode"
            )

    workdir = _relative_path(data.get("workdir", "."), f"{label}.workdir")
    inputs = _string_list(data.get("inputs"), f"{label}.inputs")
    optional_inputs = _string_list(
        data.get("optional_inputs"), f"{label}.optional_inputs"
    )
    outputs = _string_list(data.get("outputs"), f"{label}.outputs")
    for path_index, relative in enumerate(inputs):
        _relative_path(relative, f"{label}.inputs[{path_index}]", allow_dot=False)
    for path_index, relative in enumerate(optional_inputs):
        _relative_path(
            relative, f"{label}.optional_inputs[{path_index}]", allow_dot=False
        )
    overlap = set(inputs) & set(optional_inputs)
    if overlap:
        raise GraphError(
            f"{label}.optional_inputs must not repeat required inputs: "
            f"{sorted(overlap)}"
        )
    for path_index, relative in enumerate(outputs):
        _relative_path(relative, f"{label}.outputs[{path_index}]", allow_dot=False)
    outputs_set = set(outputs)
    output_schemas_value = data.get("output_schemas")
    output_schemas: Dict[str, str] = {}
    if output_schemas_value is not None:
        if kind == "barrier":
            raise GraphError(f"{label} barrier nodes cannot define output_schemas")
        schema_data = _expect_dict(output_schemas_value, f"{label}.output_schemas")
        for output_path, schema_path in schema_data.items():
            if output_path not in outputs_set:
                raise GraphError(
                    f"{label}.output_schemas key must be a declared output: "
                    f"{output_path!r}"
                )
            output_schemas[output_path] = _relative_path(
                schema_path,
                f"{label}.output_schemas.{output_path}",
                allow_dot=False,
            )

    return NodeSpec(
        id=node_id,
        kind=kind,
        depends_on=_string_list(data.get("depends_on"), f"{label}.depends_on"),
        command=command,
        adapter=adapter,
        prompt_file=prompt_file,
        prompt_mode=prompt_mode,
        workdir=workdir,
        inputs=inputs,
        optional_inputs=optional_inputs,
        outputs=outputs,
        output_schemas=output_schemas,
        timeout_seconds=_positive_int(
            data.get("timeout_seconds"), f"{label}.timeout_seconds", 3600
        ),
        retries=_nonnegative_int(data.get("retries"), f"{label}.retries", 0),
        env=_string_mapping(data.get("env"), f"{label}.env"),
        exclusive_resources=_string_list(
            data.get("exclusive_resources"), f"{label}.exclusive_resources"
        ),
        when=_load_condition(data.get("when"), f"{label}.when"),
        description=str(data.get("description", "")),
        tasks_file=tasks_file,
        task_template=task_template,
        task_parallel=task_parallel,
    )


def _validate_edges(nodes: Sequence[NodeSpec]) -> None:
    node_ids = {node.id for node in nodes}
    if len(node_ids) != len(nodes):
        raise GraphError("node ids must be unique")
    for node in nodes:
        unknown = set(node.depends_on) - node_ids
        if unknown:
            raise GraphError(
                f"node {node.id!r} has unknown dependencies: {sorted(unknown)}"
            )
        if node.id in node.depends_on:
            raise GraphError(f"node {node.id!r} cannot depend on itself")

    indegree = {node.id: len(node.depends_on) for node in nodes}
    children: Dict[str, List[str]] = {node.id: [] for node in nodes}
    for node in nodes:
        for dependency in node.depends_on:
            children[dependency].append(node.id)
    ready = [node_id for node_id, degree in indegree.items() if degree == 0]
    visited = 0
    while ready:
        current = ready.pop()
        visited += 1
        for child in children[current]:
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
    if visited != len(nodes):
        cyclic = sorted(node_id for node_id, degree in indegree.items() if degree)
        raise GraphError(f"graph must be acyclic; cycle includes {cyclic}")

    output_producers: Dict[str, str] = {}
    for node in nodes:
        for output in node.outputs:
            existing = output_producers.get(output)
            if existing is not None:
                raise GraphError(
                    f"output {output!r} has multiple producers: "
                    f"{existing!r} and {node.id!r}"
                )
            output_producers[output] = node.id


def load_graph(path: Path) -> GraphSpec:
    """Load and validate one graph JSON file."""
    graph_path = path.expanduser().resolve()
    try:
        raw_text = graph_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise GraphError(f"cannot read graph {graph_path}: {exc}") from exc
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise GraphError(f"invalid graph JSON: {exc}") from exc
    root = _expect_dict(data, "graph")
    schema_version = root.get("schema_version")
    if schema_version != 1:
        raise GraphError("schema_version must be 1")
    project_id = _expect_string(root.get("project_id"), "project_id")

    workspace_value = _expect_string(root.get("workspace", "."), "workspace")
    if Path(workspace_value).is_absolute():
        raise GraphError("workspace must be relative to the graph file")
    workspace = (graph_path.parent / workspace_value).resolve()
    if not workspace.is_dir():
        raise GraphError(f"workspace does not exist or is not a directory: {workspace}")

    adapter_values = _expect_dict(root.get("adapters", {}), "adapters")
    adapters = {
        _expect_string(name, "adapter name"): _load_adapter(name, value)
        for name, value in adapter_values.items()
    }
    default_adapter = root.get("default_adapter")
    if default_adapter is not None:
        default_adapter = _expect_string(default_adapter, "default_adapter")
        if default_adapter not in adapters:
            raise GraphError(
                f"default_adapter references unknown adapter {default_adapter!r}"
            )

    node_values = root.get("nodes")
    if not isinstance(node_values, list) or not node_values:
        raise GraphError("nodes must be a non-empty array")
    nodes = tuple(
        _load_node(value, index, adapters, default_adapter)
        for index, value in enumerate(node_values)
    )
    _validate_edges(nodes)
    cycle_control = _load_cycle_control(root.get("cycle_control"))
    if cycle_control is not None:
        producers = [
            node.id
            for node in nodes
            if cycle_control.decision_path in node.outputs
        ]
        if len(producers) != 1:
            raise GraphError(
                "cycle_control.decision_path must be declared as the output of "
                f"exactly one node; found producers={producers}"
            )
        node_ids = {node.id for node in nodes}
        for decision, roots in cycle_control.repeat_reset.items():
            unknown = set(roots) - node_ids
            if unknown:
                raise GraphError(
                    f"cycle_control.repeat_reset.{decision} references unknown "
                    f"nodes: {sorted(unknown)}"
                )

    state_file = _relative_path(
        root.get("state_file", ".autoresearcher/orchestrator/state.json"),
        "state_file",
        allow_dot=False,
    )
    logs_dir = _relative_path(
        root.get("logs_dir", ".autoresearcher/orchestrator/logs"),
        "logs_dir",
        allow_dot=False,
    )
    _resolve_inside(workspace, state_file, "state_file")
    _resolve_inside(workspace, logs_dir, "logs_dir")
    for node in nodes:
        workdir = _resolve_inside(workspace, node.workdir, f"node {node.id} workdir")
        if not workdir.is_dir():
            raise GraphError(
                f"node {node.id!r} workdir does not exist or is not a directory: "
                f"{workdir}"
            )
        if node.prompt_file is not None:
            prompt_path = _resolve_inside(
                workspace, node.prompt_file, f"node {node.id} prompt_file"
            )
            if not prompt_path.is_file():
                raise GraphError(
                    f"node {node.id!r} prompt_file does not exist: {prompt_path}"
                )
        for output_path, schema_relative in node.output_schemas.items():
            schema_file = _resolve_inside(
                workspace, schema_relative, f"node {node.id} output schema"
            )
            if not schema_file.is_file():
                raise GraphError(
                    f"node {node.id!r} output schema for {output_path!r} "
                    f"does not exist: {schema_file}"
                )
        if node.task_template is not None:
            template = node.task_template
            if template.prompt_file is not None:
                template_prompt = _resolve_inside(
                    workspace, template.prompt_file,
                    f"node {node.id} task prompt_file",
                )
                if not template_prompt.is_file():
                    raise GraphError(
                        f"node {node.id!r} task_template.prompt_file does not "
                        f"exist: {template_prompt}"
                    )
            for output_path, schema_relative in template.output_schemas.items():
                schema_file = _resolve_inside(
                    workspace, schema_relative,
                    f"node {node.id} task output schema",
                )
                if not schema_file.is_file():
                    raise GraphError(
                        f"node {node.id!r} task output schema for "
                        f"{output_path!r} does not exist: {schema_file}"
                    )

    canonical = json.dumps(root, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    graph_sha256 = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return GraphSpec(
        schema_version=1,
        project_id=project_id,
        graph_path=graph_path,
        workspace=workspace,
        state_file=state_file,
        logs_dir=logs_dir,
        max_parallel=_positive_int(root.get("max_parallel"), "max_parallel", 4),
        max_cycles=_positive_int(root.get("max_cycles"), "max_cycles", 5),
        graph_sha256=graph_sha256,
        adapters=adapters,
        nodes=nodes,
        cycle_control=cycle_control,
        budget=_load_budget(root.get("budget")),
    )


def render_mermaid(graph: GraphSpec) -> str:
    """Render a compact Mermaid representation of the validated graph."""
    lines = ["flowchart TD"]
    for node in graph.nodes:
        label = f"{node.id}<br/>{node.kind}"
        if node.kind == "barrier":
            lines.append(f'    {node.id}{{{{"{label}"}}}}')
        elif node.kind == "gate":
            lines.append(f'    {node.id}{{"{label}"}}')
        elif node.kind == "foreach":
            lines.append(f'    {node.id}[["{label}"]]')
        else:
            lines.append(f'    {node.id}["{label}"]')
    for node in graph.nodes:
        for dependency in node.depends_on:
            lines.append(f"    {dependency} --> {node.id}")
    return "\n".join(lines) + "\n"
