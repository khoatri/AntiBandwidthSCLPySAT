import csv
from pathlib import Path
import pytest
import openpyxl

from src.comparison.excel_comparator import (
    SolverRecord,
    determine_better_solver,
    determine_bold_cells,
    generate_excel_comparison,
    load_csv,
    main,
)

SAMPLE_KISSAT_CSV = """instance,n,m,lower_bound,upper_bound,optimal_w,status,total_time_s,steps_evaluated,sym_mode,verified
A-pores_1.mtx.rnd,30,103,6,8,6,OPTIMAL,0.450,2,f,True
B-ibm32.mtx.rnd,32,90,9,9,9,OPTIMAL,0.158,1,f,True
C-bcspwr01.mtx.rnd,39,46,16,17,17,OPTIMAL,0.318,2,f,True
I-ash85.mtx.rnd,85,219,19,27,21,TIMEOUT,1800.000,4,f,True
M-bcsstk06.mtx.rnd,420,3720,28,72,,TIMEOUT,1800.000,1,f,False
"""

SAMPLE_CADICAL_CSV = """instance,n,m,lower_bound,upper_bound,optimal_w,status,total_time_s,steps_evaluated,sym_mode,verified
A-pores_1.mtx.rnd,30,103,6,8,6,OPTIMAL,23.370,2,f,True
B-ibm32.mtx.rnd,32,90,9,9,9,OPTIMAL,0.470,1,f,True
C-bcspwr01.mtx.rnd,39,46,16,17,16,TIMEOUT,1800.000,1,f,True
I-ash85.mtx.rnd,85,219,19,27,21,TIMEOUT,1800.040,4,f,True
M-bcsstk06.mtx.rnd,420,3720,28,72,,TIMEOUT,1800.210,1,f,False
"""


def test_load_csv(tmp_path: Path) -> None:
    csv_file = tmp_path / "kissat_f.csv"
    csv_file.write_text(SAMPLE_KISSAT_CSV)

    records = load_csv(csv_file)
    assert len(records) == 5
    assert "B-ibm32.mtx.rnd" in records

    ibm = records["B-ibm32.mtx.rnd"]
    assert ibm.instance == "B-ibm32.mtx.rnd"
    assert ibm.n == 32
    assert ibm.m == 90
    assert ibm.lower_bound == 9
    assert ibm.upper_bound == 9
    assert ibm.optimal_w == 9
    assert ibm.status == "OPTIMAL"
    assert ibm.total_time_s == 0.158
    assert ibm.steps_evaluated == 1
    assert ibm.sym_mode == "f"
    assert ibm.verified is True


def test_determine_bold_cells() -> None:
    # 1. Strict timeout tie: both TIMEOUT with same w* -> NO cells bolded & no winner
    k_timeout = SolverRecord(
        "I-ash85.mtx.rnd", 85, 219, 19, 27, 21, "TIMEOUT", 1800.0, 4, "f", True
    )
    c_timeout = SolverRecord(
        "I-ash85.mtx.rnd", 85, 219, 19, 27, 21, "TIMEOUT", 1800.04, 4, "f", True
    )
    assert determine_better_solver(k_timeout, c_timeout) is None
    bold_k, bold_c = determine_bold_cells(k_timeout, c_timeout)
    assert bold_k == set()
    assert bold_c == set()

    # 2. Both TIMEOUT without finding any SAT step (both optimal_w is None) -> NO cells bolded
    k_none = SolverRecord(
        "M-bcsstk06.mtx.rnd", 420, 3720, 28, 72, None, "TIMEOUT", 1800.0, 1, "f", False
    )
    c_none = SolverRecord(
        "M-bcsstk06.mtx.rnd", 420, 3720, 28, 72, None, "TIMEOUT", 1800.2, 1, "f", False
    )
    assert determine_better_solver(k_none, c_none) is None
    bold_k2, bold_c2 = determine_bold_cells(k_none, c_none)
    assert bold_k2 == set()
    assert bold_c2 == set()

    # 3. Different w*: higher w* solver wins and all 3 cells are bolded
    k_higher_w = SolverRecord(
        "C-bcspwr01.mtx.rnd", 39, 46, 16, 17, 17, "OPTIMAL", 0.318, 2, "f", True
    )
    c_lower_w = SolverRecord(
        "C-bcspwr01.mtx.rnd", 39, 46, 16, 17, 16, "TIMEOUT", 1800.0, 1, "f", True
    )
    assert determine_better_solver(k_higher_w, c_lower_w) == "Kissat"
    bold_k3, bold_c3 = determine_bold_cells(k_higher_w, c_lower_w)
    assert bold_k3 == {"optimal_w", "time", "status"}
    assert bold_c3 == set()

    # 4. Same w*, status difference: OPTIMAL beats TIMEOUT
    k_opt = SolverRecord(
        "test.mtx.rnd", 50, 100, 10, 15, 12, "OPTIMAL", 10.0, 2, "f", True
    )
    c_to = SolverRecord(
        "test.mtx.rnd", 50, 100, 10, 15, 12, "TIMEOUT", 1800.0, 3, "f", True
    )
    assert determine_better_solver(k_opt, c_to) == "Kissat"
    bold_k4, bold_c4 = determine_bold_cells(k_opt, c_to)
    assert bold_k4 == {"optimal_w", "time", "status"}
    assert bold_c4 == set()

    # 5. Same w*, both OPTIMAL: faster runtime is bolded
    k_fast = SolverRecord(
        "B-ibm32.mtx.rnd", 32, 90, 9, 9, 9, "OPTIMAL", 0.158, 1, "f", True
    )
    c_slow = SolverRecord(
        "B-ibm32.mtx.rnd", 32, 90, 9, 9, 9, "OPTIMAL", 0.470, 1, "f", True
    )
    assert determine_better_solver(k_fast, c_slow) == "Kissat"
    bold_k5, bold_c5 = determine_bold_cells(k_fast, c_slow)
    assert bold_k5 == {"optimal_w", "time", "status"}
    assert bold_c5 == set()


def test_generate_excel_comparison(tmp_path: Path) -> None:
    kissat_csv = tmp_path / "kissat_summary.csv"
    cadical_csv = tmp_path / "cadical_summary.csv"
    kissat_csv.write_text(SAMPLE_KISSAT_CSV)
    cadical_csv.write_text(SAMPLE_CADICAL_CSV)

    out_xlsx = tmp_path / "comparison.xlsx"
    generate_excel_comparison(
        kissat_files={"f": kissat_csv},
        cadical_files={"f": cadical_csv},
        output_xlsx=out_xlsx,
    )

    assert out_xlsx.exists()

    wb = openpyxl.load_workbook(out_xlsx)
    assert wb.sheetnames == ["Comparison", "Kissat_4.0.4_f", "CaDiCal_1.2.1_f"]

    ws = wb["Comparison"]

    # Tier 1 headers check
    assert ws["A1"].value == "Instance Metadata"
    assert ws["F1"].value == "Kissat 4.0.4 (f)"
    assert ws["I1"].value == "CaDiCal 1.2.1 (f)"

    # Tier 2 column order check: strictly Optimal w before Time (s) before Status
    assert ws["A2"].value == "Instance"
    assert ws["B2"].value == "n"
    assert ws["C2"].value == "m"
    assert ws["D2"].value == "Lower Bound"
    assert ws["E2"].value == "Upper Bound"

    # Kissat group: F=Optimal w, G=Time (s), H=Status
    assert ws["F2"].value == "Optimal w"
    assert ws["G2"].value == "Time (s)"
    assert ws["H2"].value == "Status"

    # CaDiCal group: I=Optimal w, J=Time (s), K=Status
    assert ws["I2"].value == "Optimal w"
    assert ws["J2"].value == "Time (s)"
    assert ws["K2"].value == "Status"

    # Verify no Speedup or Winner column exists
    assert ws["L2"].value is None

    # Check font and pastel fills on headers (zero gray tones)
    assert ws["A1"].font.name == "Liberation Sans"
    assert ws["A1"].fill.start_color.rgb == "FFFFF9C4"
    assert ws["F1"].fill.start_color.rgb == "FFA9DFBF"
    assert ws["I1"].fill.start_color.rgb == "FFA2D9CE"
    assert ws["A2"].fill.start_color.rgb == "FFFFFDE7"
    assert ws["F2"].fill.start_color.rgb == "FFD4EFDF"
    assert ws["I2"].fill.start_color.rgb == "FFD1F2EB"

    # Check auto-fit column widths (row 1 merged headers ignored, Optimal w is 12)
    assert ws.column_dimensions["F"].width == 12
    assert ws.column_dimensions["I"].width == 12

    # Check winner row bolding: C-bcspwr01 (Kissat proved w=17 OPTIMAL, CaDiCal w=16 TIMEOUT)
    bcspwr_row = None
    for row in range(3, ws.max_row + 1):
        if ws.cell(row=row, column=1).value == "C-bcspwr01.mtx.rnd":
            bcspwr_row = row
            break
    assert bcspwr_row is not None
    # All 3 Kissat cells (Optimal w, Time, Status) are bold
    for col in (6, 7, 8):
        assert ws.cell(row=bcspwr_row, column=col).font.bold is True
    # All 3 CaDiCal cells are NOT bold
    for col in (9, 10, 11):
        assert ws.cell(row=bcspwr_row, column=col).font.bold is False

    # Check timeout-tie row bolding & pastel status fill: I-ash85
    # Find row with instance I-ash85.mtx.rnd
    ash_row = None
    for row in range(3, ws.max_row + 1):
        if ws.cell(row=row, column=1).value == "I-ash85.mtx.rnd":
            ash_row = row
            break
    assert ash_row is not None

    # On ash_row, both are TIMEOUT with w*=21 -> NO cell should be bold
    for col in range(6, 12):
        cell = ws.cell(row=ash_row, column=col)
        assert cell.font is None or not cell.font.bold

    # But status cell should have pastel red fill
    k_status_ash = ws.cell(row=ash_row, column=8)
    assert k_status_ash.fill.start_color.rgb == "FFFADBD8"

    # Check replica sheets
    k_replica = wb["Kissat_4.0.4_f"]
    assert k_replica["A1"].value == "instance"
    assert k_replica["A1"].font.name == "Liberation Sans"
    assert k_replica["A1"].fill.start_color.rgb == "FFA9DFBF"
    assert k_replica["K1"].value == "verified"
    assert k_replica.freeze_panes == "A2"


def test_cli_invocation(tmp_path: Path) -> None:
    kissat_csv = tmp_path / "kissat_f.csv"
    cadical_csv = tmp_path / "cadical_f.csv"
    kissat_csv.write_text(SAMPLE_KISSAT_CSV)
    cadical_csv.write_text(SAMPLE_CADICAL_CSV)

    out_xlsx = tmp_path / "cli_comparison.xlsx"

    test_args = [
        "--kissat-f",
        str(kissat_csv),
        "--cadical-f",
        str(cadical_csv),
        "-o",
        str(out_xlsx),
    ]

    import sys
    orig_argv = sys.argv
    try:
        sys.argv = ["excel_comparator.py"] + test_args
        ret = main()
        assert ret == 0
        assert out_xlsx.exists()
    finally:
        sys.argv = orig_argv


def test_unsat_start_status_styling(tmp_path: Path) -> None:
    kissat_csv = tmp_path / "kissat.csv"
    cadical_csv = tmp_path / "cadical.csv"
    kissat_csv.write_text(
        "instance,n,m,lower_bound,upper_bound,optimal_w,status,total_time_s,steps_evaluated,sym_mode,verified\n"
        "test.mtx.rnd,4,6,2,2,,UNSAT_START,0.010,1,n,False\n"
    )
    cadical_csv.write_text(
        "instance,n,m,lower_bound,upper_bound,optimal_w,status,total_time_s,steps_evaluated,sym_mode,verified\n"
        "test.mtx.rnd,4,6,2,2,,UNSAT,0.010,1,n,False\n"
    )
    out_xlsx = tmp_path / "out.xlsx"
    generate_excel_comparison(
        kissat_files={"n": kissat_csv},
        cadical_files={"n": cadical_csv},
        output_xlsx=out_xlsx,
    )
    wb = openpyxl.load_workbook(out_xlsx)
    ws = wb["Comparison"]
    # Kissat status cell is column 8 on row 3
    k_status = ws.cell(row=3, column=8)
    assert k_status.value == "UNSAT_START"
    assert k_status.fill.start_color.rgb == "FFE8DAEF"
    assert k_status.font.color.rgb == "FF5B2C6F"


def test_format_replica_sheet_with_extra_columns(tmp_path: Path) -> None:
    csv_content = (
        "instance,n,m,lower_bound,upper_bound,best_known_w,optimal_w,status,total_time_s,steps_evaluated,sym_mode,verified\n"
        "A-pores_1.mtx.rnd,30,103,6,8,7,6,OPTIMAL,0.225,2,f,True\n"
    )
    csv_file = tmp_path / "legacy_summary.csv"
    csv_file.write_text(csv_content)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Replica"

    from src.comparison.excel_comparator import _format_replica_sheet, PASTEL_PALETTE
    regular_font = openpyxl.styles.Font(name="Liberation Sans", size=10)
    thin_border = openpyxl.styles.Border()

    _format_replica_sheet(
        ws,
        csv_file,
        header_fill_hex=PASTEL_PALETTE["f"]["kissat_tier1"],
        header_font_hex=PASTEL_PALETTE["f"]["font"],
        regular_font=regular_font,
        border=thin_border,
    )

    # In this 12-column CSV, column 8 is 'status' ('OPTIMAL'), column 9 is 'total_time_s' ('0.225')
    status_cell = ws.cell(row=2, column=8)
    assert status_cell.value == "OPTIMAL"
    assert status_cell.fill.start_color.rgb == "FFD4EFDF"

    time_cell = ws.cell(row=2, column=9)
    assert time_cell.value == 0.225
    assert time_cell.number_format == "0.000"


def test_no_best_w_hyphen_inserted(tmp_path: Path) -> None:
    kissat_csv = tmp_path / "kissat.csv"
    cadical_csv = tmp_path / "cadical.csv"
    kissat_csv.write_text(
        "instance,n,m,lower_bound,upper_bound,optimal_w,status,total_time_s,steps_evaluated,sym_mode,verified\n"
        "M-bcsstk06.mtx.rnd,420,3720,28,72,,TIMEOUT,1800.000,1,f,False\n"
        "A-pores_1.mtx.rnd,30,103,6,8,6,OPTIMAL,0.225,2,f,True\n"
    )
    cadical_csv.write_text(
        "instance,n,m,lower_bound,upper_bound,optimal_w,status,total_time_s,steps_evaluated,sym_mode,verified\n"
        "M-bcsstk06.mtx.rnd,420,3720,28,72,,TIMEOUT,1800.210,1,f,False\n"
        "A-pores_1.mtx.rnd,30,103,6,8,6,OPTIMAL,23.370,2,f,True\n"
    )
    out_xlsx = tmp_path / "out_hyphen.xlsx"
    generate_excel_comparison(
        kissat_files={"f": kissat_csv},
        cadical_files={"f": cadical_csv},
        output_xlsx=out_xlsx,
    )
    wb = openpyxl.load_workbook(out_xlsx)
    ws = wb["Comparison"]

    m_row = None
    for row in range(3, ws.max_row + 1):
        if ws.cell(row=row, column=1).value == "M-bcsstk06.mtx.rnd":
            m_row = row
            break
    assert m_row is not None
    assert ws.cell(row=m_row, column=6).value == "-"
    assert ws.cell(row=m_row, column=6).alignment.horizontal == "center"
    assert ws.cell(row=m_row, column=9).value == "-"
    assert ws.cell(row=m_row, column=9).alignment.horizontal == "center"

    a_row = None
    for row in range(3, ws.max_row + 1):
        if ws.cell(row=row, column=1).value == "A-pores_1.mtx.rnd":
            a_row = row
            break
    assert a_row is not None
    assert ws.cell(row=a_row, column=6).value == 6
    assert ws.cell(row=a_row, column=6).alignment.horizontal == "right"
    assert ws.cell(row=a_row, column=9).value == 6
    assert ws.cell(row=a_row, column=9).alignment.horizontal == "right"



