"""Minimal, dependency-free JSON contract validation for node outputs.

Supports the JSON Schema subset the framework needs:
``type``, ``enum``, ``required``, ``properties``, ``items``, ``minItems``,
``minLength``. Unknown schema keywords are ignored so schemas stay
forward-compatible, but each unknown keyword emits a warning so that authors
do not silently assume enforcement that does not exist. Validation is
deterministic and never executes content.
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path
from typing import Any, Dict, List


_SUPPORTED_KEYWORDS = frozenset(
    {"type", "enum", "required", "properties", "items", "minItems", "minLength"}
)

_TYPE_CHECKS = {
    "object": lambda value: isinstance(value, dict),
    "array": lambda value: isinstance(value, list),
    "string": lambda value: isinstance(value, str),
    "integer": lambda value: isinstance(value, int) and not isinstance(value, bool),
    "number": lambda value: isinstance(value, (int, float))
    and not isinstance(value, bool),
    "boolean": lambda value: isinstance(value, bool),
    "null": lambda value: value is None,
}


def collect_unknown_keywords(schema: Any, path: str = "$") -> List[str]:
    """Return unsupported schema keywords found anywhere in ``schema``.

    Recurses into ``properties`` and ``items``, which are the only keyword
    values that carry nested schemas. Each returned string is a JSON pointer
    fragment like ``$.properties.foo.minimum``.
    """
    unknown: List[str] = []
    if not isinstance(schema, dict):
        return unknown
    for key in schema:
        if key not in _SUPPORTED_KEYWORDS:
            unknown.append(f"{path}.{key}")
    properties = schema.get("properties")
    if isinstance(properties, dict):
        for name, sub_schema in properties.items():
            if isinstance(sub_schema, dict):
                unknown.extend(
                    collect_unknown_keywords(sub_schema, f"{path}.properties.{name}")
                )
    items = schema.get("items")
    if isinstance(items, dict):
        unknown.extend(collect_unknown_keywords(items, f"{path}.items"))
    return unknown


def validate_json(data: Any, schema: Dict[str, Any], path: str = "$") -> List[str]:
    """Return a list of human-readable violations; empty means valid."""
    errors: List[str] = []

    expected_type = schema.get("type")
    if expected_type is not None:
        allowed = (
            expected_type if isinstance(expected_type, list) else [expected_type]
        )
        if not any(
            _TYPE_CHECKS.get(name, lambda _value: False)(data) for name in allowed
        ):
            errors.append(f"{path}: expected type {allowed}, got {type(data).__name__}")
            return errors

    enum_values = schema.get("enum")
    if enum_values is not None and data not in enum_values:
        errors.append(f"{path}: value {data!r} not in enum {enum_values}")

    if isinstance(data, str):
        min_length = schema.get("minLength")
        if isinstance(min_length, int) and len(data.strip()) < min_length:
            errors.append(f"{path}: string shorter than minLength {min_length}")

    if isinstance(data, dict):
        for key in schema.get("required", []):
            if key not in data:
                errors.append(f"{path}: missing required key {key!r}")
        properties = schema.get("properties", {})
        if isinstance(properties, dict):
            for key, sub_schema in properties.items():
                if key in data and isinstance(sub_schema, dict):
                    errors.extend(
                        validate_json(data[key], sub_schema, f"{path}.{key}")
                    )

    if isinstance(data, list):
        min_items = schema.get("minItems")
        if isinstance(min_items, int) and len(data) < min_items:
            errors.append(f"{path}: fewer than minItems {min_items}")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(data):
                errors.extend(
                    validate_json(item, item_schema, f"{path}[{index}]")
                )

    return errors


def validate_file(artifact: Path, schema_file: Path) -> List[str]:
    """Validate one JSON artifact against one schema file."""
    try:
        schema = json.loads(schema_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"schema unreadable: {schema_file}: {exc}"]
    if not isinstance(schema, dict):
        return [f"schema must be a JSON object: {schema_file}"]
    unknown = collect_unknown_keywords(schema)
    if unknown:
        warnings.warn(
            f"{schema_file}: unsupported schema keywords are ignored and not "
            f"enforced: {', '.join(unknown)}",
            UserWarning,
            stacklevel=2,
        )
    try:
        data = json.loads(artifact.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"artifact is not valid JSON: {artifact}: {exc}"]
    return validate_json(data, schema)
