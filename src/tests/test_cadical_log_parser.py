import csv
import sys
from pathlib import Path
import pytest

from src.comparison.cadical_log_parser import (
    CadicalLogResult,
    parse_cadical_log,
    parse_cadical_directory,
    derive_edge_count,
    CSV_COLUMNS,
)

SAMPLE_OPTIMAL_LOG = """[runlim] version:\t\t1.10
[runlim] time limit:\t\t1800 seconds
[runlim] real time limit:\t1800 seconds
[runlim] space limit:\t\t30000 MB
[runlim] argv[0]:\t\t/home/tri/AntiBandwidthSCL/build/abw_enc
[runlim] argv[1]:\t\t/home/tri/AntiBandwidthSCL/build/Benchmarks/B-ibm32.mtx.rnd
[runlim] argv[2]:\t\t--ladder
[runlim] argv[3]:\t\t-symmetry-break
[runlim] argv[4]:\t\tf
[runlim] start:\t\t\tSun Nov 22 10:56:18 2026
[runlim] main pid:\t\t227646
[runlim] log captured:
c LadderEncoder 1.0.
c Symetry breaking in the first node.
c Solving strategy: from LB to UB.
c LB-w = 9 (LB in Sinnl - A note on computational approaches for the antibandwidth problem).
c UB-w = 9 (UB in Sinnl - A note on computational approaches for the antibandwidth problem).
c Antibandwidth problem with w = 9 ( B-ibm32.mtx.rnd ):
c Initializing CaDiCaL (version 1.2.1).
c\tConfiguring CaDiCaL as --sat (1).
c Initializing a Ladder encoder with n = 32.
c Encoding starts with w = 9:
c\tEncode symmetry breaking with option: f.
c\tLabels and Vertices aux var: 640
c\tLabels and Vertices constraints:  3136
c\tObj k aux var: 1344
c\tObj k constraints: 13622
c\tObj k glue staircase constraints: 7830
c\tEncoding duration: 0s
c\tNumber of clauses: 16774
c\tNumber of irredundant clauses: 16639
c\tNumber of variables: 3008
c SAT Solving starts:
c\tSolving duration: 253 ms
c\tAnswer: 
s SAT (w = 9)
c\tSolution check:
p calculated antibandwidth = 9.
c
c
[runlim] end:\t\t\tSun Nov 22 10:56:18 2026
[runlim] status:\t\tok
[runlim] result:\t\t0
[runlim] children:\t\t0
[runlim] real:\t\t\t0.47 seconds
[runlim] time:\t\t\t0.20 seconds
[runlim] space:\t\t\t8.3 MB
[runlim] samples:\t\t2
"""

SAMPLE_MULTISTEP_LOG = """[runlim] version:\t\t1.10
[runlim] time limit:\t\t1800 seconds
[runlim] argv[1]:\t\t/path/to/D-bcsstk01.mtx.rnd
[runlim] log captured:
c LB-w = 8 (LB in Sinnl).
c UB-w = 9 (UB in Sinnl).
c Antibandwidth problem with w = 8 ( D-bcsstk01.mtx.rnd ):
c Initializing a Ladder encoder with n = 48.
c\tEncode symmetry breaking with option: f.
c\tObj k glue staircase constraints: 25696
s SAT (w = 8)
p calculated antibandwidth = 8.
c Antibandwidth problem with w = 9 ( D-bcsstk01.mtx.rnd ):
c Initializing a Ladder encoder with n = 48.
c\tEncode symmetry breaking with option: f.
c\tObj k glue staircase constraints: 25520
s SAT (w = 9)
p calculated antibandwidth = 9.
[runlim] end:\t\t\tSun Nov 22 09:56:14 2026
[runlim] status:\t\tok
[runlim] real:\t\t\t0.33 seconds
[runlim] time:\t\t\t0.09 seconds
[runlim] space:\t\t\t13.5 MB
"""

SAMPLE_TIMEOUT_LOG = """[runlim] version:\t\t1.10
[runlim] argv[1]:\t\t/path/to/I-ash85.mtx.rnd
[runlim] log captured:
c LB-w = 19 (LB in Sinnl).
c UB-w = 27 (UB in Sinnl).
c Antibandwidth problem with w = 19 ( I-ash85.mtx.rnd ):
c Initializing a Ladder encoder with n = 85.
c\tEncode symmetry breaking with option: f.
c\tObj k glue staircase constraints: 56064
s SAT (w = 19)
p calculated antibandwidth = 19.
c Antibandwidth problem with w = 20 ( I-ash85.mtx.rnd ):
c Initializing a Ladder encoder with n = 85.
c\tEncode symmetry breaking with option: f.
c\tObj k glue staircase constraints: 55188
s SAT (w = 20)
p calculated antibandwidth = 20.
c Antibandwidth problem with w = 21 ( I-ash85.mtx.rnd ):
c Initializing a Ladder encoder with n = 85.
c\tEncode symmetry breaking with option: f.
c\tObj k glue staircase constraints: 54312
s SAT (w = 21)
p calculated antibandwidth = 21.
c Antibandwidth problem with w = 22 ( I-ash85.mtx.rnd ):
c Initializing a Ladder encoder with n = 85.
c\tEncode symmetry breaking with option: f.
c Signal interruption.
[runlim] status:\t\tout of time
[runlim] real:\t\t\t1800.11 seconds
[runlim] time:\t\t\t1799.87 seconds
[runlim] space:\t\t\t359.1 MB
"""


def test_parse_optimal_log(tmp_path: Path) -> None:
    log_file = tmp_path / "B-ibm32.out"
    log_file.write_text(SAMPLE_OPTIMAL_LOG)

    res = parse_cadical_log(log_file)
    assert res.instance == "B-ibm32.mtx.rnd"
    assert res.n == 32
    assert res.m == 90  # Derived via analytical formula: 7830 / 87 = 90
    assert res.lower_bound == 9
    assert res.upper_bound == 9
    assert res.optimal_w == 9
    assert res.status == "OPTIMAL"
    assert res.total_time_s == 0.47
    assert res.steps_evaluated == 1
    assert res.sym_mode == "f"
    assert res.verified is True


def test_parse_multistep_log(tmp_path: Path) -> None:
    log_file = tmp_path / "D-bcsstk01.out"
    log_file.write_text(SAMPLE_MULTISTEP_LOG)

    res = parse_cadical_log(log_file)
    assert res.instance == "D-bcsstk01.mtx.rnd"
    assert res.n == 48
    assert res.m == 176
    assert res.lower_bound == 8
    assert res.upper_bound == 9
    assert res.optimal_w == 9
    assert res.status == "OPTIMAL"
    assert res.total_time_s == 0.33
    assert res.steps_evaluated == 2
    assert res.sym_mode == "f"
    assert res.verified is True


def test_parse_timeout_log(tmp_path: Path) -> None:
    log_file = tmp_path / "I-ash85.out"
    log_file.write_text(SAMPLE_TIMEOUT_LOG)

    res = parse_cadical_log(log_file)
    assert res.instance == "I-ash85.mtx.rnd"
    assert res.n == 85
    assert res.lower_bound == 19
    assert res.upper_bound == 27
    assert res.optimal_w == 21  # Highest SAT w found before timeout
    assert res.status == "TIMEOUT"
    assert res.total_time_s == 1800.11
    assert res.steps_evaluated == 4
    assert res.sym_mode == "f"
    assert res.verified is True


def test_derive_edge_count() -> None:
    # B-ibm32: n=32, w=9, glue_constraints=7830
    # e = 4*(32-9+1) - 3*(32//9) = 4*24 - 3*3 = 96 - 9 = 87
    # m = 7830 / 87 = 90
    m = derive_edge_count(n=32, w=9, glue_constraints=7830)
    assert m == 90

    # D-bcsstk01: n=48, w=8, glue_constraints=25696
    # e = 4*(48-8+1) - 3*(48//8) = 4*41 - 3*6 = 164 - 18 = 146
    # m = 25696 / 146 = 176
    m2 = derive_edge_count(n=48, w=8, glue_constraints=25696)
    assert m2 == 176


def test_parse_directory_to_csv(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "B-ibm32.out").write_text(SAMPLE_OPTIMAL_LOG)
    (log_dir / "D-bcsstk01.out").write_text(SAMPLE_MULTISTEP_LOG)
    (log_dir / "I-ash85.out").write_text(SAMPLE_TIMEOUT_LOG)

    out_csv = tmp_path / "summary.csv"
    results = parse_cadical_directory(log_dir, output_csv=out_csv, sym_mode="f")

    assert len(results) == 3
    assert out_csv.exists()

    with open(out_csv, "r", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))
        assert len(reader) == 3
        assert list(reader[0].keys()) == CSV_COLUMNS

        # Check rows
        ibm = next(r for r in reader if r["instance"] == "B-ibm32.mtx.rnd")
        assert ibm["n"] == "32"
        assert ibm["m"] == "90"
        assert ibm["optimal_w"] == "9"
        assert ibm["status"] == "OPTIMAL"
        assert ibm["total_time_s"] == "0.470"
        assert ibm["steps_evaluated"] == "1"
        assert ibm["sym_mode"] == "f"
        assert ibm["verified"] == "True"

        ash = next(r for r in reader if r["instance"] == "I-ash85.mtx.rnd")
        assert ash["status"] == "TIMEOUT"
        assert ash["optimal_w"] == "21"
        assert ash["steps_evaluated"] == "4"
