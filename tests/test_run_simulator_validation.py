from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = (
    Path(__file__).parents[1]
    / "research"
    / "src"
    / "experiments"
    / "run_simulator_validation.py"
)
SPEC = importlib.util.spec_from_file_location("run_simulator_validation", MODULE_PATH)
assert SPEC and SPEC.loader
validation = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validation)


def test_python_test_environment_binds_project_src_and_preserves_other_values(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(validation, "PROJECT_ROOT", tmp_path)
    environment = validation.python_test_environment(
        {"PATH": "/usr/bin", "PYTHONPATH": "/stale/checkout"}
    )
    assert environment == {
        "PATH": "/usr/bin",
        "PYTHONPATH": str(tmp_path / "src"),
    }
