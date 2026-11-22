import argparse
import json
import subprocess
import sys
from pathlib import Path
import pytest

from src.cli import build_parser, main
from src.utils.graph import Graph


def test_cli_parser_structure() -> None:
    parser = build_parser()
    assert parser.prog == "antibandwidth"
    # Verify subparsers exist
    subparser_actions = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]
    assert len(subparser_actions) == 1
    subparser_names = list(subparser_actions[0].choices.keys())
    assert "solve" in subparser_names
    assert "optimize" in subparser_names
    assert "inspect" in subparser_names


def test_cli_no_args_shows_help(capsys: pytest.CaptureFixture[str]) -> None:
    ret = main([])
    assert ret == 2
    captured = capsys.readouterr()
    assert "usage:" in captured.err.lower() or "usage:" in captured.out.lower()


# =========================================================================
# Inspect Subcommand Tests
# =========================================================================

def test_cli_inspect_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    ret = main(["inspect", "-g", "instances/A-pores_1.mtx.rnd", "-w", "5", "-s", "h"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "A-pores_1" in captured.out
    assert "Vertices (n):        30" in captured.out
    assert "Edges (m):           103" in captured.out
    assert "Target Threshold w:  5" in captured.out
    assert "Theoretical Variables (N):" in captured.out
    assert "Theoretical Clauses (C):" in captured.out
    assert "Best Known w:" not in captured.out


def test_cli_inspect_missing_graph(capsys: pytest.CaptureFixture[str]) -> None:
    ret = main(["inspect", "-g", "instances/non_existent.mtx.rnd"])
    assert ret != 0
    captured = capsys.readouterr()
    assert "Error:" in captured.err or "not found" in captured.err.lower()


def test_cli_inspect_invalid_w(capsys: pytest.CaptureFixture[str]) -> None:
    ret = main(["inspect", "-g", "instances/A-pores_1.mtx.rnd", "-w", "1"])
    assert ret != 0
    captured = capsys.readouterr()
    assert "w must satisfy" in captured.err or "must be >= 2" in captured.err


# =========================================================================
# Solve Subcommand Tests
# =========================================================================

def test_cli_solve_sat(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    out_file = tmp_path / "solve_p4.json"
    p4_file = tmp_path / "p4.mtx.rnd"
    p4_file.write_text("Nombre del problema: P4\n4 2 3\n1 2\n2 3\n3 4\n")

    ret = main([
        "solve",
        "-g", str(p4_file),
        "-w", "2",
        "-s", "n",
        "-o", str(out_file),
    ])
    assert ret == 0
    captured = capsys.readouterr()
    assert "SAT" in captured.out
    assert "Verified:      True" in captured.out

    assert out_file.exists()
    data = json.loads(out_file.read_text())
    assert data["status"] == "SAT"
    assert data["w"] == 2
    assert data["lower_bound"] == 1
    assert data["upper_bound"] == 2
    assert data["theoretical_upper_bound"] == 2
    assert "best_known_w" not in data
    assert data["verified"] is True
    assert len(data["labeling"]) == 4


def test_cli_solve_output_directory(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    p4_file = tmp_path / "p4.mtx.rnd"
    p4_file.write_text("Nombre del problema: P4\n4 2 3\n1 2\n2 3\n3 4\n")
    out_dir = tmp_path / "out_dir"
    out_dir.mkdir()

    ret = main([
        "solve",
        "-g", str(p4_file),
        "-w", "2",
        "-s", "n",
        "-o", f"{out_dir}/",
    ])
    assert ret == 0
    expected_file = out_dir / "p4.mtx.rnd.json"
    assert expected_file.exists()
    data = json.loads(expected_file.read_text())
    assert data["status"] == "SAT"


def test_cli_solve_unsat(capsys: pytest.CaptureFixture[str]) -> None:
    ret = main([
        "solve",
        "-g", "instances/A-pores_1.mtx.rnd",
        "-w", "16",  # U = floor(30/2) = 15, w=16 is UNSAT
        "-t", "5.0",
    ])
    assert ret == 0
    captured = capsys.readouterr()
    assert "UNSAT" in captured.out


def test_cli_solve_missing_graph(capsys: pytest.CaptureFixture[str]) -> None:
    ret = main(["solve", "-g", "non_existent.mtx.rnd", "-w", "2"])
    assert ret != 0
    captured = capsys.readouterr()
    assert "Error loading graph" in captured.err


def test_cli_solve_w_exceeds_n(capsys: pytest.CaptureFixture[str]) -> None:
    ret = main(["solve", "-g", "instances/A-pores_1.mtx.rnd", "-w", "31"])
    assert ret != 0
    captured = capsys.readouterr()
    assert "cannot exceed number of vertices" in captured.err


def test_cli_optimize_missing_graph(capsys: pytest.CaptureFixture[str]) -> None:
    ret = main(["optimize", "-g", "non_existent.mtx.rnd"])
    assert ret != 0
    captured = capsys.readouterr()
    assert "Error loading graph" in captured.err


def test_cli_solve_invalid_width(capsys: pytest.CaptureFixture[str]) -> None:
    ret = main([
        "solve",
        "-g", "instances/A-pores_1.mtx.rnd",
        "-w", "1",
    ])
    assert ret != 0
    captured = capsys.readouterr()
    assert "must be >= 2" in captured.err


def test_cli_solve_timeout(capsys: pytest.CaptureFixture[str]) -> None:
    ret = main([
        "solve",
        "-g", "instances/A-pores_1.mtx.rnd",
        "-w", "10",
        "-t", "0.005",
    ])
    assert ret == 1
    captured = capsys.readouterr()
    assert "TIMEOUT" in captured.out


def test_cli_solve_quiet(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    out_file = tmp_path / "quiet.json"
    ret = main([
        "solve",
        "-g", "instances/A-pores_1.mtx.rnd",
        "-w", "5",
        "-t", "10.0",
        "-q",
        "-o", str(out_file),
    ])
    assert ret == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert out_file.exists()


# =========================================================================
# Optimize Subcommand Tests
# =========================================================================

def test_cli_optimize_p4(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    out_file = tmp_path / "opt_p4.json"
    p4_file = tmp_path / "p4.mtx.rnd"
    p4_file.write_text("Nombre del problema: P4\n4 2 3\n1 2\n2 3\n3 4\n")

    ret = main([
        "optimize",
        "-g", str(p4_file),
        "--start-w", "2",
        "-s", "n",
        "-o", str(out_file),
    ])
    assert ret == 0
    captured = capsys.readouterr()
    assert "Optimal Bandwidth w*:" in captured.out
    assert "2" in captured.out

    assert out_file.exists()
    data = json.loads(out_file.read_text())
    assert data["status"] == "OPTIMAL"
    assert data["optimal_w"] == 2
    assert data["start_w"] == 2
    assert data["lower_bound"] == 1
    assert data["upper_bound"] == 2
    assert data["theoretical_upper_bound"] == 2
    assert "best_known_w" not in data
    assert data["verified"] is True
    assert len(data["steps"]) == 1


def test_cli_optimize_output_directory(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    p4_file = tmp_path / "p4.mtx.rnd"
    p4_file.write_text("Nombre del problema: P4\n4 2 3\n1 2\n2 3\n3 4\n")
    out_dir = tmp_path / "opt_dir"
    out_dir.mkdir()

    ret = main([
        "optimize",
        "-g", str(p4_file),
        "--start-w", "2",
        "-s", "n",
        "-o", str(out_dir),
    ])
    assert ret == 0
    expected_file = out_dir / "p4.mtx.rnd.json"
    assert expected_file.exists()
    data = json.loads(expected_file.read_text())
    assert data["status"] == "OPTIMAL"
    assert data["optimal_w"] == 2


def test_cli_optimize_unsat_start(capsys: pytest.CaptureFixture[str]) -> None:
    # A-pores_1 with start_w (20) exceeding upper bound (8)
    ret = main([
        "optimize",
        "-g", "instances/A-pores_1.mtx.rnd",
        "--start-w", "20",  # Upper bound is 15
    ])
    assert ret == 0
    captured = capsys.readouterr()
    assert "UNSAT_START" in captured.out


def test_cli_optimize_invalid_start_w(capsys: pytest.CaptureFixture[str]) -> None:
    ret = main([
        "optimize",
        "-g", "instances/A-pores_1.mtx.rnd",
        "--start-w", "1",
    ])
    assert ret != 0
    captured = capsys.readouterr()
    assert "start-w must be >= 2" in captured.err


def test_cli_optimize_timeout(capsys: pytest.CaptureFixture[str]) -> None:
    ret = main([
        "optimize",
        "-g", "instances/A-pores_1.mtx.rnd",
        "--start-w", "6",
        "-t", "0.005",
    ])
    assert ret == 1
    captured = capsys.readouterr()
    assert "TIMEOUT" in captured.out


def test_cli_inspect_default_width_uses_lower_bound(capsys: pytest.CaptureFixture[str]) -> None:
    # Omit -w on pores_1 (Sinnl lower bound = 6, upper bound = 8)
    ret = main(["inspect", "-g", "instances/A-pores_1.mtx.rnd"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "Predefined Lower Bound (LB): 6" in captured.out
    assert "Predefined Upper Bound (UB): 8" in captured.out
    assert "Theoretical Bound U: 15" in captured.out
    assert "Target Threshold w:  6 (predefined lower bound)" in captured.out


def test_cli_solve_default_width_uses_lower_bound(capsys: pytest.CaptureFixture[str]) -> None:
    # Omit -w on pores_1
    ret = main(["solve", "-g", "instances/A-pores_1.mtx.rnd", "-t", "5.0"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "Target w:      6 (predefined lower bound)" in captured.out
    assert "Status:        SAT" in captured.out


def test_cli_solve_explicit_width_overrides_lower_bound(capsys: pytest.CaptureFixture[str]) -> None:
    # Explicitly pass -w 2 on pores_1
    ret = main(["solve", "-g", "instances/A-pores_1.mtx.rnd", "-w", "2", "-t", "5.0"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "Target w:      2\n" in captured.out


def test_cli_optimize_default_start_w_uses_lower_bound(capsys: pytest.CaptureFixture[str]) -> None:
    # Omit --start-w on pores_1
    ret = main(["optimize", "-g", "instances/A-pores_1.mtx.rnd", "-t", "10.0"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "Start w:       6 (predefined lower bound)" in captured.out
    assert "Upper Bound w: 8" in captured.out

