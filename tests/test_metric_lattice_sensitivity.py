"""Pin the measurement-lattice sensitivity of the Cycle 4 spatial metrics.

``e3-cycle4-design.md`` §3 claims that ``density_morans_i`` and
``occupancy_entropy`` are not resolution-invariant, so a grid-discretization
robustness check measured on the native lattice would report a measurement
artefact as a scientific failure.  These tests keep that fact from being silently
"fixed" or forgotten: they assert the mechanism on synthetic particle
configurations, independently of any simulator output.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import List, Sequence, Tuple

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    REPO_ROOT / "research" / "src" / "experiments" / "check_metric_lattice_sensitivity.py"
)
sys.path.insert(0, str(MODULE_PATH.parent))
_SPEC = importlib.util.spec_from_file_location(
    "check_metric_lattice_sensitivity", MODULE_PATH
)
assert _SPEC is not None and _SPEC.loader is not None
checker = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(checker)

BOUNDS = (0.0, 100.0, 0.0, 100.0)

Point = Tuple[float, float]


def _write_run(
    runs_dir: Path,
    seed: int,
    condition: str,
    points: Sequence[Point],
    *,
    snapshot_indices: Sequence[int] = (0,),
) -> Path:
    """Create a synthetic run directory whose snapshots carry ``x,y,w``."""

    run_dir = runs_dir / f"seed-{seed}--{condition}"
    run_dir.mkdir(parents=True, exist_ok=True)
    body = ["x,y,w"]
    body.extend(f"{float(px):.6f},{float(py):.6f},1.000000" for px, py in points)
    text = "\n".join(body) + "\n"
    for index in snapshot_indices:
        (run_dir / f"snap_{index:08d}.csv").write_text(text, encoding="utf-8")
    return run_dir


def _fill_cell(cell_x: int, cell_y: int, per_side: int, width: float) -> List[Point]:
    """Particles on a ``per_side``-square grid inside one coarse-lattice cell."""

    return [
        ((cell_x + (i + 0.5) / per_side) * width, (cell_y + (j + 0.5) / per_side) * width)
        for i in range(per_side)
        for j in range(per_side)
    ]


def test_entropy_is_strictly_smaller_on_a_finer_lattice(tmp_path: Path) -> None:
    """The ``log(n_cells)`` normalisation makes refinement lower the entropy."""

    runs_dir = tmp_path / "runs"
    rng = np.random.default_rng(20260920)
    points = list(zip(rng.uniform(0.0, 100.0, 500), rng.uniform(0.0, 100.0, 500)))
    for condition in ("clustered", "shuffled"):
        _write_run(runs_dir, 11, condition, points)

    payload = checker.lattice_sensitivity(
        runs_dir, lattices=((16, 16), (64, 64)), bounds=BOUNDS
    )
    coarse, fine = payload["per_lattice"]
    assert coarse["lattice"] == [16, 16] and fine["lattice"] == [64, 64]
    coarse_entropy = coarse["metrics"]["occupancy_entropy"]["condition_means"]["clustered"]
    fine_entropy = fine["metrics"]["occupancy_entropy"]["condition_means"]["clustered"]
    assert coarse_entropy > fine_entropy


def test_the_paired_moran_effect_shrinks_purely_from_the_lattice(tmp_path: Path) -> None:
    """Reproduce the artefact mechanism: adjacency is a length of one cell.

    At the coarse lattice the two conditions are histogram-matched and differ only
    in whether the loaded cells touch.  At the finer lattice that adjacency
    contrast is diluted because one coarse cell becomes a block of fine cells.
    """

    runs_dir = tmp_path / "runs"
    width = 100.0 / 16.0
    adjacent = _fill_cell(0, 0, 6, width) + _fill_cell(1, 0, 6, width)
    separated = _fill_cell(0, 0, 6, width) + _fill_cell(8, 0, 6, width)
    _write_run(runs_dir, 21, "clustered", adjacent)
    _write_run(runs_dir, 21, "shuffled", separated)

    payload = checker.lattice_sensitivity(
        runs_dir, lattices=((16, 16), (64, 64)), bounds=BOUNDS
    )
    coarse, fine = payload["per_lattice"]
    coarse_effect = coarse["metrics"]["density_morans_i"]["paired_effect"]
    fine_effect = fine["metrics"]["density_morans_i"]["paired_effect"]
    assert coarse_effect > 0.0
    assert fine_effect < coarse_effect


def test_final_snapshot_is_the_highest_index_not_the_lexicographic_max(
    tmp_path: Path,
) -> None:
    run_dir = _write_run(
        tmp_path / "runs", 31, "clustered", [(1.0, 1.0)], snapshot_indices=(9, 10)
    )
    assert checker.final_snapshot(run_dir).name == "snap_00000010.csv"


def test_payload_is_marked_as_a_diagnostic_and_records_transitions(
    tmp_path: Path,
) -> None:
    runs_dir = tmp_path / "runs"
    _write_run(runs_dir, 41, "clustered", [(10.0, 10.0), (20.0, 20.0)])
    _write_run(runs_dir, 41, "shuffled", [(30.0, 30.0), (40.0, 40.0)])

    payload = checker.lattice_sensitivity(
        runs_dir, lattices=((16, 16), (32, 32), (64, 64)), bounds=BOUNDS
    )
    assert payload["not_a_claim_input"] is True
    assert payload["estimator"] == "final_snapshot"
    assert [entry["lattice"] for entry in payload["per_lattice"]] == [
        [16, 16],
        [32, 32],
        [64, 64],
    ]
    transitions = payload["adjacent_transitions"]["density_morans_i"]
    assert [item["from_lattice"] for item in transitions] == [[16, 16], [32, 32]]
    for item in transitions:
        assert item["absolute_change"] == pytest.approx(
            abs(item["effect_after"] - item["effect_before"])
        )


def test_a_missing_condition_fails_fast(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    _write_run(runs_dir, 51, "clustered", [(10.0, 10.0)])
    with pytest.raises(RuntimeError, match="missing run"):
        checker.lattice_sensitivity(
            runs_dir, lattices=((16, 16), (32, 32)), bounds=BOUNDS
        )


def test_unmatched_directory_names_are_ignored(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    _write_run(runs_dir, 61, "clustered", [(10.0, 10.0)])
    _write_run(runs_dir, 61, "shuffled", [(30.0, 30.0)])
    (runs_dir / "inputs").mkdir()
    (runs_dir / "notes").mkdir()

    payload = checker.lattice_sensitivity(runs_dir, lattices=((16, 16),), bounds=BOUNDS)
    assert payload["seeds"] == [61]


def test_cli_writes_json_output(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    _write_run(runs_dir, 71, "clustered", [(10.0, 10.0), (12.0, 12.0)])
    _write_run(runs_dir, 71, "shuffled", [(80.0, 80.0), (82.0, 82.0)])
    output = tmp_path / "lattice.json"

    assert (
        checker.main(
            [
                "--runs-dir",
                str(runs_dir),
                "--lattices",
                "16,32",
                "--bounds",
                "0,100,0,100",
                "--output",
                str(output),
            ]
        )
        == 0
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["bounds"] == [0.0, 100.0, 0.0, 100.0]
    assert len(payload["per_lattice"]) == 2


def test_lattice_list_rejects_a_single_size(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="at least two sizes"):
        checker.main(["--runs-dir", str(tmp_path), "--lattices", "16"])
