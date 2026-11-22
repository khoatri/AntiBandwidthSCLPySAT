import csv
import json
import subprocess
import sys
from pathlib import Path
import pytest

from src.automation import build_automation_parser, run_campaign, main as automation_main


def test_automation_parser_defaults() -> None:
    parser = build_automation_parser()
    args = parser.parse_args([])
    assert args.instances_dir == "instances"
    assert args.output_dir == "benchmarks"
    assert args.sym == "n"
    assert args.timeout == 1800.0
    assert args.mem_limit == 30.0
    assert args.skip_existing is False
    assert args.start_w_mode == "lower_bound"


def test_automation_custom_args() -> None:
    parser = build_automation_parser()
    args = parser.parse_args([
        "-i", "custom_inst",
        "-o", "custom_out",
        "-s", "h",
        "-t", "60.0",
        "-m", "16.0",
        "--skip-existing",
        "--start-w-mode", "min",
    ])
    assert args.instances_dir == "custom_inst"
    assert args.output_dir == "custom_out"
    assert args.sym == "h"
    assert args.timeout == 60.0
    assert args.mem_limit == 16.0
    assert args.skip_existing is True
    assert args.start_w_mode == "min"


def test_automation_start_w_mode_best_known_rejected() -> None:
    parser = build_automation_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--start-w-mode", "best_known"])
    with pytest.raises(SystemExit):
        parser.parse_args(["--start-w-mode", "header"])


def test_automation_empty_directory(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    empty_inst = tmp_path / "empty_instances"
    empty_inst.mkdir()
    out_dir = tmp_path / "out"

    parser = build_automation_parser()
    args = parser.parse_args(["-i", str(empty_inst), "-o", str(out_dir)])
    ret = run_campaign(args)
    assert ret == 0
    captured = capsys.readouterr()
    assert "No matching instance files found" in captured.out


def test_automation_non_existent_directory(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    non_existent = tmp_path / "definitely_does_not_exist_xyz"
    out_dir = tmp_path / "out"

    parser = build_automation_parser()
    args = parser.parse_args(["-i", str(non_existent), "-o", str(out_dir)])
    ret = run_campaign(args)
    assert ret == 0
    captured = capsys.readouterr()
    assert "No matching instance files found" in captured.out



def test_automation_single_instance_campaign(tmp_path: Path) -> None:
    inst_dir = tmp_path / "instances"
    inst_dir.mkdir()
    out_dir = tmp_path / "benchmarks"

    # Synthetic P4 instance
    p4_file = inst_dir / "test_p4.mtx.rnd"
    p4_file.write_text("Nombre del problema: test_p4\n4 2 3\n1 2\n2 3\n3 4\n")

    parser = build_automation_parser()
    args = parser.parse_args([
        "-i", str(inst_dir),
        "-o", str(out_dir),
        "-t", "10.0",
    ])
    ret = run_campaign(args)
    assert ret == 0

    # 1. Manifest
    manifest_file = out_dir / "campaign_manifest.json"
    assert manifest_file.exists()
    manifest = json.loads(manifest_file.read_text())
    assert manifest["solver"] == "kissat404"
    assert manifest["jobs"] == 1
    assert manifest["total_instances"] == 1

    # 2. Summary CSV
    summary_file = out_dir / "summary.csv"
    assert summary_file.exists()
    with open(summary_file, mode="r", newline="") as f:
        rows = list(csv.DictReader(f))
        assert len(rows) == 1
        r = rows[0]
        assert r["instance"] == "test_p4.mtx.rnd"
        assert r["n"] == "4"
        assert r["m"] == "3"
        assert "best_known_w" not in r
        assert r["optimal_w"] == "2"
        assert r["status"] == "OPTIMAL"
        assert r["verified"] == "True"
        assert r["steps_evaluated"] == "1"

    # 3. Result JSON
    res_file = out_dir / "results" / "test_p4.mtx.rnd.json"
    assert res_file.exists()
    data = json.loads(res_file.read_text())
    assert "best_known_w" not in data
    assert data["optimal_w"] == 2
    assert data["status"] == "OPTIMAL"
    assert data["verified"] is True
    assert len(data["steps"]) == 1


def test_automation_skip_existing(tmp_path: Path) -> None:
    inst_dir = tmp_path / "instances"
    out_dir = tmp_path / "benchmarks"
    inst_dir.mkdir()

    # Create A-inst.mtx.rnd
    (inst_dir / "A-inst.mtx.rnd").write_text("Nombre: A\n4 2 3\n1 2\n2 3\n3 4\n")

    parser = build_automation_parser()

    # Pass 1: Run on A-inst
    args1 = parser.parse_args([
        "-i", str(inst_dir),
        "-o", str(out_dir),
    ])
    ret1 = run_campaign(args1)
    assert ret1 == 0
    assert (out_dir / "results" / "A-inst.mtx.rnd.json").exists()

    # Add B-inst.mtx.rnd
    (inst_dir / "B-inst.mtx.rnd").write_text("Nombre: B\n4 2 3\n1 2\n2 3\n3 4\n")

    # Pass 2: Run with --skip-existing
    args_skip = parser.parse_args([
        "-i", str(inst_dir),
        "-o", str(out_dir),
        "--skip-existing",
    ])
    ret2 = run_campaign(args_skip)
    assert ret2 == 0
    assert (out_dir / "results" / "B-inst.mtx.rnd.json").exists()

    # Summary CSV should have both records
    summary_file = out_dir / "summary.csv"
    with open(summary_file, mode="r", newline="") as f:
        rows = list(csv.DictReader(f))
        instances_in_csv = [r["instance"] for r in rows]
        assert "A-inst.mtx.rnd" in instances_in_csv
        assert "B-inst.mtx.rnd" in instances_in_csv


def test_automation_duplicate_csv_prevention(tmp_path: Path) -> None:
    inst_dir = tmp_path / "instances"
    out_dir = tmp_path / "benchmarks"
    inst_dir.mkdir()
    (inst_dir / "A-inst.mtx.rnd").write_text("Nombre: A\n4 2 3\n1 2\n2 3\n3 4\n")

    parser = build_automation_parser()
    args = parser.parse_args(["-i", str(inst_dir), "-o", str(out_dir)])

    # First run
    assert run_campaign(args) == 0

    # Second run without --skip-existing: should not duplicate row in summary.csv
    assert run_campaign(args) == 0

    summary_file = out_dir / "summary.csv"
    with open(summary_file, mode="r", newline="") as f:
        rows = list(csv.DictReader(f))
        assert len(rows) == 1
        assert rows[0]["instance"] == "A-inst.mtx.rnd"


def test_automation_rerun_updates_existing_csv_row(tmp_path: Path) -> None:
    inst_dir = tmp_path / "instances"
    out_dir = tmp_path / "benchmarks"
    inst_dir.mkdir()
    (inst_dir / "A-inst.mtx.rnd").write_text("Nombre: A\n4 2 3\n1 2\n2 3\n3 4\n")

    parser = build_automation_parser()

    # First run with -s n
    args1 = parser.parse_args(["-i", str(inst_dir), "-o", str(out_dir), "-s", "n"])
    assert run_campaign(args1) == 0

    summary_file = out_dir / "summary.csv"
    with open(summary_file, mode="r", newline="") as f:
        rows = list(csv.DictReader(f))
        assert len(rows) == 1
        assert rows[0]["sym_mode"] == "n"

    # Second run without --skip-existing with -s f
    args2 = parser.parse_args(["-i", str(inst_dir), "-o", str(out_dir), "-s", "f"])
    assert run_campaign(args2) == 0

    with open(summary_file, mode="r", newline="") as f:
        rows = list(csv.DictReader(f))
        assert len(rows) == 1, "Must not append duplicate rows"
        assert rows[0]["sym_mode"] == "f", "Must update existing row with latest run result"


def test_automation_corrupt_instance_continues(tmp_path: Path) -> None:
    inst_dir = tmp_path / "instances"
    out_dir = tmp_path / "benchmarks"
    inst_dir.mkdir()

    # Instance 1: Corrupt header
    (inst_dir / "01-bad.mtx.rnd").write_text("Corrupted file content without dimensions\n")
    # Instance 2: Good graph
    (inst_dir / "02-good.mtx.rnd").write_text("Nombre: good\n4 2 3\n1 2\n2 3\n3 4\n")

    parser = build_automation_parser()
    args = parser.parse_args(["-i", str(inst_dir), "-o", str(out_dir), "-t", "5.0"])

    ret = run_campaign(args)
    assert ret == 0

    summary_file = out_dir / "summary.csv"
    with open(summary_file, mode="r", newline="") as f:
        rows = list(csv.DictReader(f))
        assert len(rows) == 2
        assert rows[0]["instance"] == "01-bad.mtx.rnd"
        assert rows[0]["status"] == "ERROR"
        assert rows[1]["instance"] == "02-good.mtx.rnd"
        assert rows[1]["status"] == "OPTIMAL"


def test_automation_timeout_handling(tmp_path: Path) -> None:
    # Campaign with tiny timeout should record TIMEOUT in CSV and JSON
    inst_dir = tmp_path / "instances"
    out_dir = tmp_path / "benchmarks"
    inst_dir.mkdir()

    # Copy real instance pores_1
    real_pores = Path("instances/A-pores_1.mtx.rnd").read_text()
    (inst_dir / "A-pores_1.mtx.rnd").write_text(real_pores)

    parser = build_automation_parser()
    args = parser.parse_args([
        "-i", str(inst_dir),
        "-o", str(out_dir),
        "-t", "0.005",
        "--start-w-mode", "lower_bound",  # starts at LB=6
    ])
    ret = run_campaign(args)
    assert ret == 0

    summary_file = out_dir / "summary.csv"
    with open(summary_file, mode="r", newline="") as f:
        rows = list(csv.DictReader(f))
        assert len(rows) == 1
        assert rows[0]["status"] == "TIMEOUT"


def test_automation_main_entrypoint(tmp_path: Path) -> None:
    inst_dir = tmp_path / "instances"
    out_dir = tmp_path / "benchmarks"
    inst_dir.mkdir()
    (inst_dir / "test_p4.mtx.rnd").write_text("Nombre: test_p4\n4 2 3\n1 2\n2 3\n3 4\n")

    ret = automation_main(["-i", str(inst_dir), "-o", str(out_dir)])
    assert ret == 0
    assert (out_dir / "summary.csv").exists()


def test_automation_cli_script_invocation(tmp_path: Path) -> None:
    # Test running via python -m src.automation
    inst_dir = tmp_path / "instances"
    out_dir = tmp_path / "benchmarks"
    inst_dir.mkdir()
    (inst_dir / "test_p4.mtx.rnd").write_text("Nombre: test_p4\n4 2 3\n1 2\n2 3\n3 4\n")

    proc = subprocess.run(
        [
            sys.executable,
            "-m", "src.automation",
            "-i", str(inst_dir),
            "-o", str(out_dir),
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert (out_dir / "summary.csv").exists()
    assert (out_dir / "campaign_manifest.json").exists()


def test_automation_starts_from_lower_bound_and_records_bounds(tmp_path: Path) -> None:
    inst_dir = tmp_path / "instances"
    out_dir = tmp_path / "benchmarks"
    inst_dir.mkdir()

    # Named A-pores_1.mtx.rnd with Sinnl LB = 6, UB = 8
    (inst_dir / "A-pores_1.mtx.rnd").write_text(
        Path("instances/A-pores_1.mtx.rnd").read_text()
    )

    parser = build_automation_parser()
    args = parser.parse_args([
        "-i", str(inst_dir),
        "-o", str(out_dir),
        "-t", "5.0",
    ])
    assert run_campaign(args) == 0

    res_file = out_dir / "results" / "A-pores_1.mtx.rnd.json"
    assert res_file.exists()
    data = json.loads(res_file.read_text())
    assert data["start_w"] == 6
    assert data["lower_bound"] == 6
    assert data["upper_bound"] == 8
    assert data["theoretical_upper_bound"] == 15

    # Check summary CSV columns
    summary_file = out_dir / "summary.csv"
    assert summary_file.exists()
    with open(summary_file, mode="r", newline="") as f:
        rows = list(csv.DictReader(f))
        assert len(rows) == 1
        r = rows[0]
        assert r["lower_bound"] == "6"
        assert r["upper_bound"] == "8"


def test_automation_explicit_start_w_modes(tmp_path: Path) -> None:
    inst_dir = tmp_path / "instances"
    out_dir = tmp_path / "benchmarks"
    inst_dir.mkdir()
    (inst_dir / "A-pores_1.mtx.rnd").write_text(
        Path("instances/A-pores_1.mtx.rnd").read_text()
    )
    parser = build_automation_parser()

    # Mode 'min' starts at 2
    args_min = parser.parse_args(["-i", str(inst_dir), "-o", str(out_dir / "min"), "--start-w-mode", "min", "-t", "5.0"])
    assert run_campaign(args_min) == 0
    data_min = json.loads((out_dir / "min" / "results" / "A-pores_1.mtx.rnd.json").read_text())
    assert data_min["start_w"] == 2

    # Mode 'default' / 'lower_bound' starts at Sinnl LB 6
    args_default = parser.parse_args(["-i", str(inst_dir), "-o", str(out_dir / "default"), "--start-w-mode", "default", "-t", "5.0"])
    assert run_campaign(args_default) == 0
    data_default = json.loads((out_dir / "default" / "results" / "A-pores_1.mtx.rnd.json").read_text())
    assert data_default["start_w"] == 6

