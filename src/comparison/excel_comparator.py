import argparse
import csv
from dataclasses import dataclass
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional, Set, Tuple

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

# Ensure repository root is on sys.path
repo_root = Path(__file__).resolve().parent.parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from src.comparison.cadical_log_parser import CSV_COLUMNS


@dataclass
class SolverRecord:
    """Represents a benchmark run record for an instance."""

    instance: str
    n: int
    m: int
    lower_bound: Optional[int]
    upper_bound: Optional[int]
    optimal_w: Optional[int]
    status: str
    total_time_s: Optional[float]
    steps_evaluated: int
    sym_mode: str
    verified: bool


def natural_sort_key(s: str) -> list[Any]:
    """Helper for natural alphanumeric sorting (e.g. file_2 before file_10)."""
    return [
        int(text) if text.isdigit() else text.lower()
        for text in re.split(r"(\d+)", s)
    ]


def load_csv(csv_path: Optional[Path]) -> Dict[str, SolverRecord]:
    """Parse a summary.csv file into a dict mapping instance name -> SolverRecord."""
    records: Dict[str, SolverRecord] = {}
    if not csv_path or not csv_path.exists():
        return records

    with open(csv_path, "r", encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f)
        for row in reader:
            inst = row.get("instance", "").strip()
            if not inst:
                continue

            n = int(row["n"]) if row.get("n", "").isdigit() else 0
            m = int(row["m"]) if row.get("m", "").isdigit() else 0

            lb = int(row["lower_bound"]) if row.get("lower_bound", "").isdigit() else None
            ub = int(row["upper_bound"]) if row.get("upper_bound", "").isdigit() else None
            opt_w = int(row["optimal_w"]) if row.get("optimal_w", "").isdigit() else None

            status = row.get("status", "").strip().upper()

            try:
                time_s = float(row["total_time_s"]) if row.get("total_time_s") else None
            except ValueError:
                time_s = None

            steps = int(row["steps_evaluated"]) if row.get("steps_evaluated", "").isdigit() else 0
            verified = row.get("verified", "").strip().lower() in ("true", "1")
            sym_mode = row.get("sym_mode", "").strip()

            records[inst] = SolverRecord(
                instance=inst,
                n=n,
                m=m,
                lower_bound=lb,
                upper_bound=ub,
                optimal_w=opt_w,
                status=status,
                total_time_s=time_s,
                steps_evaluated=steps,
                sym_mode=sym_mode,
                verified=verified,
            )

    return records


def determine_better_solver(
    k: Optional[SolverRecord], c: Optional[SolverRecord]
) -> Optional[str]:
    """Determine which solver achieved the better result for an instance.

    Criteria:
    1. Strict Timeout Tie Rule: If both solvers timed out (TIMEOUT) at the same
       optimal_w (or neither found any SAT step), it is a tie -> neither solver
       is better (returns None, meaning NO cells are bolded).
    2. Bandwidth Superiority: The solver with strictly larger optimal_w is better.
    3. Status Superiority: Proving OPTIMAL beats TIMEOUT/MEMOUT when optimal_w is equal.
    4. Runtime Tie-Breaker: When both are OPTIMAL with identical optimal_w, the solver
       with faster runtime is better (if runtime difference > 0.005s).

    Returns:
        "Kissat", "CaDiCal", or None.
    """
    if not k or not c:
        if k and not c:
            return "Kissat"
        if c and not k:
            return "CaDiCal"
        return None

    kw = k.optimal_w
    cw = c.optimal_w

    k_to = (k.status == "TIMEOUT")
    c_to = (c.status == "TIMEOUT")

    # 1. Strict Timeout Tie Rule: Both TIMEOUT with identical w* -> NO winner / tie
    if k_to and c_to and kw == cw:
        return None

    # 2. Bandwidth Superiority: Larger w* is strictly better
    if kw is not None and cw is not None:
        if kw > cw:
            return "Kissat"
        elif cw > kw:
            return "CaDiCal"
    elif kw is not None and cw is None:
        return "Kissat"
    elif cw is not None and kw is None:
        return "CaDiCal"

    # 3. Status Superiority: Both w* equal (or both None)
    k_opt = (k.status == "OPTIMAL")
    c_opt = (c.status == "OPTIMAL")

    if k_opt and not c_opt:
        return "Kissat"
    elif c_opt and not k_opt:
        return "CaDiCal"

    # 4. Runtime Tie-Breaker: Both OPTIMAL with identical w* -> Faster runtime is better
    if k_opt and c_opt:
        kt = k.total_time_s
        ct = c.total_time_s
        if kt is not None and ct is not None:
            if abs(kt - ct) > 0.005:
                return "Kissat" if kt < ct else "CaDiCal"

    return None


def determine_bold_cells(
    k: Optional[SolverRecord], c: Optional[SolverRecord]
) -> Tuple[Set[str], Set[str]]:
    """Determine which cells (if any) should be bolded between Kissat and CaDiCaL.

    When a solver wins an instance, all three of its cells ('optimal_w', 'time',
    'status') are bolded. On ties or timeout ties with identical w*, NO cells
    are bolded.

    Returns:
        (bold_fields_kissat, bold_fields_cadical)
    """
    winner = determine_better_solver(k, c)
    if winner == "Kissat":
        return ({"optimal_w", "time", "status"}, set())
    elif winner == "CaDiCal":
        return (set(), {"optimal_w", "time", "status"})
    return (set(), set())


# Pastel Color Palette for Cross-Solver Comparison (8-char ARGB hex for LibreOffice compatibility)
# Zero grayish tones: warm pastels for metadata, colorful pastels for symmetry modes.
PASTEL_PALETTE = {
    "metadata": {
        "tier1_fill": "FFFFF9C4",  # Warm Pastel Butter / Cream
        "tier1_font": "FF7D6608",  # Dark Warm Amber
        "tier2_fill": "FFFFFDE7",  # Light Warm Ivory / Pale Butter
        "tier2_font": "FF6E2C00",  # Dark Warm Brown
    },
    "f": {
        "kissat_tier1": "FFA9DFBF",  # Pastel Mint Green
        "kissat_tier2": "FFD4EFDF",
        "cadical_tier1": "FFA2D9CE", # Pastel Aqua / Teal
        "cadical_tier2": "FFD1F2EB",
        "font": "FF145A32",
    },
    "h": {
        "kissat_tier1": "FFFAD7A0",  # Pastel Apricot
        "kissat_tier2": "FFFDEBD0",
        "cadical_tier1": "FFEDBB99", # Pastel Coral / Peach
        "cadical_tier2": "FFFBEEE6",
        "font": "FF6E2C00",
    },
    "n": {
        "kissat_tier1": "FFAED6F1",  # Pastel Sky Blue
        "kissat_tier2": "FFD6EAF8",
        "cadical_tier1": "FFD2B4DE", # Pastel Lavender Blue
        "cadical_tier2": "FFE8DAEF",
        "font": "FF1B4F72",
    },
    "l": {
        "kissat_tier1": "FFD7BDE2",  # Pastel Lilac
        "kissat_tier2": "FFE8DAEF",
        "cadical_tier1": "FFF5CBA7", # Pastel Cantaloupe
        "cadical_tier2": "FFFBEEE6",
        "font": "FF512E5F",
    },
}

STATUS_PASTEL_FILLS = {
    "OPTIMAL": "FFD4EFDF",   # Soft Pastel Green
    "TIMEOUT": "FFFADBD8",   # Soft Pastel Rose
    "MEMOUT": "FFFCF3CF",    # Soft Pastel Amber
    "UNSAT": "FFE8DAEF",     # Soft Pastel Violet
    "UNSAT_START": "FFE8DAEF", # Soft Pastel Violet
    "ERROR": "FFF5C6CB",     # Soft Pastel Coral / Red
}

STATUS_FONTS = {
    "OPTIMAL": "FF196F3D",   # Dark Forest Green
    "TIMEOUT": "FF922B21",   # Dark Wine Red
    "MEMOUT": "FF7D6608",    # Dark Ochre
    "UNSAT": "FF5B2C6F",     # Deep Plum
    "UNSAT_START": "FF5B2C6F", # Deep Plum
    "ERROR": "FF721C24",     # Dark Coral Red
}


def _format_replica_sheet(
    ws: Any,
    csv_path: Path,
    header_fill_hex: str,
    header_font_hex: str,
    regular_font: Font,
    border: Border,
) -> None:
    """Format a 1:1 copy of a summary.csv file as an Excel sheet."""
    header_font = Font(name="Liberation Sans", size=10, bold=True, color=header_font_hex)
    header_fill = PatternFill(
        start_color=header_fill_hex, end_color=header_fill_hex, fill_type="solid"
    )

    headers: List[str] = []
    with open(csv_path, "r", encoding="utf-8", errors="ignore") as f:
        reader = csv.reader(f)
        for r_idx, row in enumerate(reader, start=1):
            ws.append(row)
            if r_idx == 1:
                headers = [str(col).strip().lower() for col in row]
                # Format header
                for c_idx in range(1, len(row) + 1):
                    cell = ws.cell(row=r_idx, column=c_idx)
                    cell.font = header_font
                    cell.border = border
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                    cell.fill = header_fill
            else:
                for c_idx in range(1, len(row) + 1):
                    cell = ws.cell(row=r_idx, column=c_idx)
                    cell.font = regular_font
                    cell.border = border
                    header_name = headers[c_idx - 1] if c_idx - 1 < len(headers) else ""

                    if header_name in (
                        "n",
                        "m",
                        "lower_bound",
                        "upper_bound",
                        "optimal_w",
                        "best_known_w",
                        "steps_evaluated",
                    ):
                        try:
                            if cell.value != "":
                                cell.value = int(cell.value)
                                cell.alignment = Alignment(horizontal="right")
                        except (ValueError, TypeError):
                            pass
                    elif "time" in header_name:
                        try:
                            if cell.value != "":
                                cell.value = float(cell.value)
                                cell.number_format = "0.000"
                                cell.alignment = Alignment(horizontal="right")
                        except (ValueError, TypeError):
                            pass
                    elif header_name == "status":
                        status_val = str(cell.value or "").strip().upper()
                        cell.alignment = Alignment(horizontal="center")
                        if status_val in STATUS_PASTEL_FILLS:
                            cell.fill = PatternFill(
                                start_color=STATUS_PASTEL_FILLS[status_val],
                                end_color=STATUS_PASTEL_FILLS[status_val],
                                fill_type="solid",
                            )
                            cell.font = Font(
                                name="Liberation Sans",
                                size=10,
                                bold=True,
                                color=STATUS_FONTS.get(status_val, "FF000000"),
                            )
                    elif header_name in ("sym_mode", "verified"):
                        cell.alignment = Alignment(horizontal="center")
                    else:
                        cell.alignment = Alignment(horizontal="left")

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions

    # Auto-fit columns
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            val_str = str(cell.value or "")
            if len(val_str) > max_len:
                max_len = len(val_str)
        ws.column_dimensions[col_letter].width = max(max_len + 3, 11)


def generate_excel_comparison(
    kissat_files: Dict[str, Optional[Path]],
    cadical_files: Dict[str, Optional[Path]],
    output_xlsx: Path,
    sheet_title: str = "Comparison",
) -> None:
    """Build and format the cross-solver comparison workbook."""
    # 1. Identify active modes
    active_modes: List[str] = []
    kissat_data: Dict[str, Dict[str, SolverRecord]] = {}
    cadical_data: Dict[str, Dict[str, SolverRecord]] = {}

    all_instances_set: Set[str] = set()
    instance_meta: Dict[str, Tuple[int, int, Optional[int], Optional[int]]] = {}

    for mode in ["f", "h", "n", "l"]:
        kf = kissat_files.get(mode)
        cf = cadical_files.get(mode)
        has_k = kf is not None and kf.is_file()
        has_c = cf is not None and cf.is_file()
        if has_k or has_c:
            active_modes.append(mode)
            kissat_data[mode] = load_csv(kf) if has_k else {}
            cadical_data[mode] = load_csv(cf) if has_c else {}

            for rec in list(kissat_data[mode].values()) + list(cadical_data[mode].values()):
                all_instances_set.add(rec.instance)
                if rec.instance not in instance_meta or instance_meta[rec.instance][0] == 0:
                    instance_meta[rec.instance] = (
                        rec.n,
                        rec.m,
                        rec.lower_bound,
                        rec.upper_bound,
                    )

    if not active_modes:
        raise ValueError("No valid Kissat or CaDiCaL CSV input files were provided.")

    sorted_instances = sorted(all_instances_set, key=natural_sort_key)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_title

    # Styles
    font_family = "Liberation Sans"
    regular_font = Font(name=font_family, size=10)
    bold_font = Font(name=font_family, size=10, bold=True)

    thin_border_side = Side(style="thin", color="FFD7CCC8")
    thin_border = Border(
        left=thin_border_side,
        right=thin_border_side,
        top=thin_border_side,
        bottom=thin_border_side,
    )

    # 2. Build Header Row 1 (Tier 1 Merged Headers)
    # Col A-E: Instance Metadata
    meta_pal = PASTEL_PALETTE["metadata"]
    meta_tier1_font = Font(name=font_family, size=11, bold=True, color=meta_pal["tier1_font"])
    meta_tier1_fill = PatternFill(
        start_color=meta_pal["tier1_fill"], end_color=meta_pal["tier1_fill"], fill_type="solid"
    )

    ws.merge_cells("A1:E1")
    cell_meta = ws["A1"]
    cell_meta.value = "Instance Metadata"
    cell_meta.font = meta_tier1_font
    cell_meta.alignment = Alignment(horizontal="center", vertical="center")
    cell_meta.fill = meta_tier1_fill

    for c in range(1, 6):
        ws.cell(row=1, column=c).border = thin_border
        ws.cell(row=1, column=c).fill = meta_tier1_fill

    col_idx = 6
    for mode in active_modes:
        pal = PASTEL_PALETTE.get(mode, meta_pal)
        k_tier1_font = Font(name=font_family, size=11, bold=True, color=pal["font"])
        k_tier1_fill = PatternFill(
            start_color=pal["kissat_tier1"], end_color=pal["kissat_tier1"], fill_type="solid"
        )
        c_tier1_font = Font(name=font_family, size=11, bold=True, color=pal["font"])
        c_tier1_fill = PatternFill(
            start_color=pal["cadical_tier1"], end_color=pal["cadical_tier1"], fill_type="solid"
        )

        # Kissat 4.0.4 (mode): 3 columns
        k_start = col_idx
        k_end = col_idx + 2
        ws.merge_cells(
            start_row=1, start_column=k_start, end_row=1, end_column=k_end
        )
        k_cell = ws.cell(row=1, column=k_start)
        k_cell.value = f"Kissat 4.0.4 ({mode})"
        k_cell.font = k_tier1_font
        k_cell.alignment = Alignment(horizontal="center", vertical="center")
        for c in range(k_start, k_end + 1):
            ws.cell(row=1, column=c).border = thin_border
            ws.cell(row=1, column=c).fill = k_tier1_fill

        # CaDiCal 1.2.1 (mode): 3 columns
        c_start = col_idx + 3
        c_end = col_idx + 5
        ws.merge_cells(
            start_row=1, start_column=c_start, end_row=1, end_column=c_end
        )
        c_cell = ws.cell(row=1, column=c_start)
        c_cell.value = f"CaDiCal 1.2.1 ({mode})"
        c_cell.font = c_tier1_font
        c_cell.alignment = Alignment(horizontal="center", vertical="center")
        for c in range(c_start, c_end + 1):
            ws.cell(row=1, column=c).border = thin_border
            ws.cell(row=1, column=c).fill = c_tier1_fill

        col_idx += 6

    # 3. Build Header Row 2 (Tier 2 Column Headers)
    # Strict order: Optimal w before Time (s) before Status
    meta_tier2_font = Font(name=font_family, size=10, bold=True, color=meta_pal["tier2_font"])
    meta_tier2_fill = PatternFill(
        start_color=meta_pal["tier2_fill"], end_color=meta_pal["tier2_fill"], fill_type="solid"
    )

    tier2_metadata = ["Instance", "n", "m", "Lower Bound", "Upper Bound"]
    for c_idx, h_text in enumerate(tier2_metadata, start=1):
        cell = ws.cell(row=2, column=c_idx)
        cell.value = h_text
        cell.font = meta_tier2_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.fill = meta_tier2_fill
        cell.border = thin_border

    c_cur = 6
    for mode in active_modes:
        pal = PASTEL_PALETTE.get(mode, meta_pal)
        k_tier2_font = Font(name=font_family, size=10, bold=True, color=pal["font"])
        k_tier2_fill = PatternFill(
            start_color=pal["kissat_tier2"], end_color=pal["kissat_tier2"], fill_type="solid"
        )
        c_tier2_font = Font(name=font_family, size=10, bold=True, color=pal["font"])
        c_tier2_fill = PatternFill(
            start_color=pal["cadical_tier2"], end_color=pal["cadical_tier2"], fill_type="solid"
        )

        # Kissat: Optimal w, Time (s), Status
        for sub_idx, sub_name in enumerate(["Optimal w", "Time (s)", "Status"]):
            cell = ws.cell(row=2, column=c_cur + sub_idx)
            cell.value = sub_name
            cell.font = k_tier2_font
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.fill = k_tier2_fill
            cell.border = thin_border

        # CaDiCal: Optimal w, Time (s), Status
        for sub_idx, sub_name in enumerate(["Optimal w", "Time (s)", "Status"]):
            cell = ws.cell(row=2, column=c_cur + 3 + sub_idx)
            cell.value = sub_name
            cell.font = c_tier2_font
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.fill = c_tier2_fill
            cell.border = thin_border

        c_cur += 6

    # 4. Fill Data Rows
    for r_offset, inst in enumerate(sorted_instances):
        row_num = 3 + r_offset
        meta = instance_meta.get(inst, (0, 0, None, None))
        n, m, lb, ub = meta

        # Col 1: Instance
        c1 = ws.cell(row=row_num, column=1, value=inst)
        c1.font = regular_font
        c1.alignment = Alignment(horizontal="left", vertical="center")
        c1.border = thin_border

        # Col 2-5: n, m, Lower Bound, Upper Bound
        for idx, val in enumerate([n, m, lb, ub], start=2):
            cell = ws.cell(row=row_num, column=idx)
            cell.value = val if val is not None else ""
            cell.font = regular_font
            cell.alignment = Alignment(horizontal="right", vertical="center")
            cell.border = thin_border

        current_col = 6
        for mode in active_modes:
            k_rec = kissat_data[mode].get(inst)
            c_rec = cadical_data[mode].get(inst)
            winner = determine_better_solver(k_rec, c_rec)
            k_is_better = (winner == "Kissat")
            c_is_better = (winner == "CaDiCal")

            # Kissat columns: Optimal w, Time (s), Status
            # Optimal w
            k_opt_val = k_rec.optimal_w if (k_rec and k_rec.optimal_w is not None) else "-"
            k_opt_cell = ws.cell(row=row_num, column=current_col)
            k_opt_cell.value = k_opt_val
            k_opt_cell.font = bold_font if k_is_better else regular_font
            k_opt_cell.alignment = Alignment(
                horizontal="right" if k_opt_val != "-" else "center",
                vertical="center",
            )
            k_opt_cell.border = thin_border

            # Time (s)
            k_time_cell = ws.cell(row=row_num, column=current_col + 1)
            if k_rec and k_rec.total_time_s is not None:
                k_time_cell.value = k_rec.total_time_s
                k_time_cell.number_format = "0.000"
            else:
                k_time_cell.value = ""
            k_time_cell.font = bold_font if k_is_better else regular_font
            k_time_cell.alignment = Alignment(horizontal="right", vertical="center")
            k_time_cell.border = thin_border

            # Status (pastel badge)
            k_status_cell = ws.cell(row=row_num, column=current_col + 2)
            k_status_val = k_rec.status if k_rec else ""
            k_status_cell.value = k_status_val
            k_status_cell.alignment = Alignment(horizontal="center", vertical="center")
            k_status_cell.border = thin_border
            if k_status_val in STATUS_PASTEL_FILLS:
                k_status_cell.fill = PatternFill(
                    start_color=STATUS_PASTEL_FILLS[k_status_val],
                    end_color=STATUS_PASTEL_FILLS[k_status_val],
                    fill_type="solid",
                )
                k_status_cell.font = Font(
                    name=font_family,
                    size=10,
                    bold=k_is_better,
                    color=STATUS_FONTS.get(k_status_val, "FF000000"),
                )
            else:
                k_status_cell.font = bold_font if k_is_better else regular_font

            # CaDiCal columns: Optimal w, Time (s), Status
            # Optimal w
            c_opt_val = c_rec.optimal_w if (c_rec and c_rec.optimal_w is not None) else "-"
            c_opt_cell = ws.cell(row=row_num, column=current_col + 3)
            c_opt_cell.value = c_opt_val
            c_opt_cell.font = bold_font if c_is_better else regular_font
            c_opt_cell.alignment = Alignment(
                horizontal="right" if c_opt_val != "-" else "center",
                vertical="center",
            )
            c_opt_cell.border = thin_border

            # Time (s)
            c_time_cell = ws.cell(row=row_num, column=current_col + 4)
            if c_rec and c_rec.total_time_s is not None:
                c_time_cell.value = c_rec.total_time_s
                c_time_cell.number_format = "0.000"
            else:
                c_time_cell.value = ""
            c_time_cell.font = bold_font if c_is_better else regular_font
            c_time_cell.alignment = Alignment(horizontal="right", vertical="center")
            c_time_cell.border = thin_border

            # Status (pastel badge)
            c_status_cell = ws.cell(row=row_num, column=current_col + 5)
            c_status_val = c_rec.status if c_rec else ""
            c_status_cell.value = c_status_val
            c_status_cell.alignment = Alignment(horizontal="center", vertical="center")
            c_status_cell.border = thin_border
            if c_status_val in STATUS_PASTEL_FILLS:
                c_status_cell.fill = PatternFill(
                    start_color=STATUS_PASTEL_FILLS[c_status_val],
                    end_color=STATUS_PASTEL_FILLS[c_status_val],
                    fill_type="solid",
                )
                c_status_cell.font = Font(
                    name=font_family,
                    size=10,
                    bold=c_is_better,
                    color=STATUS_FONTS.get(c_status_val, "FF000000"),
                )
            else:
                c_status_cell.font = bold_font if c_is_better else regular_font

            current_col += 6

    # Freeze panes at A3
    ws.freeze_panes = "A3"
    total_cols = 5 + len(active_modes) * 6
    ws.auto_filter.ref = (
        f"A2:{get_column_letter(total_cols)}{2 + len(sorted_instances)}"
    )

    # Auto-fit column widths (ignoring row 1 merged headers so Tier 1 titles don't bloat Optimal w)
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            if cell.row == 1:
                continue
            val_str = str(cell.value or "")
            if len(val_str) > max_len:
                max_len = len(val_str)
        ws.column_dimensions[col_letter].width = max(max_len + 3, 11)

    # 5. Create 1:1 CSV Replica Sheets
    for mode in active_modes:
        pal = PASTEL_PALETTE.get(mode, meta_pal)
        kf = kissat_files.get(mode)
        if kf and kf.is_file():
            ws_k = wb.create_sheet(title=f"Kissat_4.0.4_{mode}")
            _format_replica_sheet(
                ws_k, kf, pal["kissat_tier1"], pal["font"], regular_font, thin_border
            )

        cf = cadical_files.get(mode)
        if cf and cf.is_file():
            ws_c = wb.create_sheet(title=f"CaDiCal_1.2.1_{mode}")
            _format_replica_sheet(
                ws_c, cf, pal["cadical_tier1"], pal["font"], regular_font, thin_border
            )

    output_xlsx.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output_xlsx)


def build_parser() -> argparse.ArgumentParser:
    """Construct CLI argument parser for Excel comparison generator."""
    parser = argparse.ArgumentParser(
        prog="antibandwidth-excel-comparator",
        description="Generate minimal Excel comparison workbook between Kissat and CaDiCaL",
    )
    # Mode-specific CSV flags
    for mode in ["f", "h", "n", "l"]:
        parser.add_argument(
            f"--kissat-{mode}",
            type=Path,
            default=None,
            help=f"Path to Kissat summary CSV for mode {mode}",
        )
        parser.add_argument(
            f"--cadical-{mode}",
            type=Path,
            default=None,
            help=f"Path to CaDiCaL summary CSV for mode {mode}",
        )

    parser.add_argument(
        "--kissat-dir",
        type=Path,
        default=None,
        help="Directory containing Kissat summary CSVs (e.g. summary_mode_f.csv or f/summary.csv)",
    )
    parser.add_argument(
        "--cadical-dir",
        type=Path,
        default=None,
        help="Directory containing CaDiCaL summary CSVs (e.g. cadical_summary_mode_f.csv or f/summary.csv)",
    )
    parser.add_argument(
        "-o",
        "--output-xlsx",
        type=Path,
        default=Path("AntiBandwidth_Comparison.xlsx"),
        help="Output Excel workbook file path (default: AntiBandwidth_Comparison.xlsx)",
    )
    parser.add_argument(
        "--title",
        type=str,
        default="Comparison",
        help="Title of main comparison worksheet (default: Comparison)",
    )
    return parser


def main() -> int:
    """CLI execution entry point."""
    parser = build_parser()
    args = parser.parse_args()

    kissat_files: Dict[str, Optional[Path]] = {}
    cadical_files: Dict[str, Optional[Path]] = {}

    for mode in ["f", "h", "n", "l"]:
        # Direct CLI flag
        k_path = getattr(args, f"kissat_{mode}")
        c_path = getattr(args, f"cadical_{mode}")

        # Directory discovery fallback
        if not k_path and args.kissat_dir and args.kissat_dir.is_dir():
            candidates = [
                args.kissat_dir / f"summary_mode_{mode}.csv",
                args.kissat_dir / f"kissat_summary_mode_{mode}.csv",
                args.kissat_dir / f"summary_{mode}.csv",
                args.kissat_dir / mode / "summary.csv",
            ]
            for cand in candidates:
                if cand.is_file():
                    k_path = cand
                    break

        if not c_path and args.cadical_dir and args.cadical_dir.is_dir():
            candidates = [
                args.cadical_dir / f"cadical_summary_mode_{mode}.csv",
                args.cadical_dir / f"summary_mode_{mode}.csv",
                args.cadical_dir / f"summary_{mode}.csv",
                args.cadical_dir / mode / "summary.csv",
            ]
            for cand in candidates:
                if cand.is_file():
                    c_path = cand
                    break

        kissat_files[mode] = k_path
        cadical_files[mode] = c_path

    active_modes = [
        m for m in ["f", "h", "n", "l"]
        if (kissat_files[m] and kissat_files[m].is_file())
        or (cadical_files[m] and cadical_files[m].is_file())
    ]

    if not active_modes:
        print("Error: No valid input CSV files were provided or found.", file=sys.stderr)
        return 1

    generate_excel_comparison(
        kissat_files=kissat_files,
        cadical_files=cadical_files,
        output_xlsx=args.output_xlsx,
        sheet_title=args.title,
    )
    print(
        f"Successfully generated comparison workbook for mode(s) {', '.join(active_modes)}: {args.output_xlsx}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
