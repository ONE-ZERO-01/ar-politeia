"""Tests for the dependency-free JSON contract validator."""

import json
import warnings

import pytest

from autoresearcher.orchestration.contracts import (
    collect_unknown_keywords,
    validate_file,
    validate_json,
)


def _write(path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_supported_keywords_validate_without_warning(tmp_path):
    schema = tmp_path / "schema.json"
    artifact = tmp_path / "out.json"
    _write(
        schema,
        {
            "type": "object",
            "required": ["name"],
            "properties": {
                "name": {"type": "string", "minLength": 1},
                "tags": {"type": "array", "minItems": 1, "items": {"type": "string"}},
            },
        },
    )
    _write(artifact, {"name": "x", "tags": ["a"]})
    with warnings.catch_warnings(record=True) as record:
        warnings.simplefilter("always")
        errors = validate_file(artifact, schema)
    assert errors == []
    assert len(record) == 0


def test_unknown_keyword_warns_and_is_not_enforced(tmp_path):
    schema = tmp_path / "schema.json"
    artifact = tmp_path / "out.json"
    # "minimum" and "pattern" are real JSON Schema keywords the framework does
    # not implement; they must warn rather than silently pass.
    _write(
        schema,
        {
            "type": "object",
            "properties": {
                "n": {"type": "integer", "minimum": 5},
                "code": {"type": "string", "pattern": "^[A-Z]+$"},
            },
        },
    )
    _write(artifact, {"n": 1, "code": "lower"})
    with pytest.warns(UserWarning) as record:
        errors = validate_file(artifact, schema)
    assert errors == []  # unsupported keywords are not enforced
    warning_text = " ".join(str(item.message) for item in record)
    assert "$.properties.n.minimum" in warning_text
    assert "$.properties.code.pattern" in warning_text


def test_collect_unknown_keywords_recurses_into_properties_and_items(tmp_path):
    schema = {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {"value": {"type": "number", "exclusiveMinimum": 0}},
        },
    }
    unknown = collect_unknown_keywords(schema)
    assert "$.items.properties.value.exclusiveMinimum" in unknown
    assert set(unknown) == {"$.items.properties.value.exclusiveMinimum"}


def test_validate_json_still_enforces_supported_keywords(tmp_path):
    schema = {
        "type": "object",
        "required": ["id"],
        "properties": {"id": {"type": "string", "minLength": 3}},
    }
    assert validate_json({"id": "x"}, schema) != []
    assert validate_json({"id": "abc"}, schema) == []
    assert validate_json({}, schema) != []
