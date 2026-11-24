import argparse
import colorsys
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


@dataclass(frozen=True)
class SolverSpec:
    """Configuration specification for a benchmarked solver backend."""

    key: str
    display_name: str
    sheet_prefix: str
    tier1_key: str
    tier2_key: str
    font_key: str


SOLVER_SPECS: List[SolverSpec] = [
    SolverSpec(
        key="kissat404",
        display_name="Kissat 4.0.4",
        sheet_prefix="Kissat_4.0.4",
        tier1_key="kissat_tier1",
        tier2_key="kissat_tier2",
        font_key="kissat_font",
    ),
    SolverSpec(
        key="cadical300",
        display_name="CaDiCaL 3.0.0",
        sheet_prefix="CaDiCaL_3.0.0",
        tier1_key="cadical300_tier1",
        tier2_key="cadical300_tier2",
        font_key="cadical300_font",
    ),
    SolverSpec(
        key="cadical121",
        display_name="CaDiCal 1.2.1",
        sheet_prefix="CaDiCal_1.2.1",
        tier1_key="cadical_tier1",
        tier2_key="cadical_tier2",
        font_key="cadical_font",
    ),
]


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


def determine_winning_solvers(
    records: Dict[str, Optional[SolverRecord]],
) -> Set[str]:
    """Determine which solver(s) achieved the winning result for an instance.

    Criteria:
    1. Zero-Solution Rule: If NO solver found a feasible labeling (all optimal_w is None),
       neither solver demonstrated superiority -> returns empty set () (NO cells bolded).
    2. Bandwidth Superiority: Higher optimal_w is strictly better.
    3. Status Superiority: Proving OPTIMAL beats TIMEOUT/MEMOUT/UNSAT_START/ERROR when optimal_w is equal.
    4. Runtime Tie-Breaker: When multiple solvers are OPTIMAL with identical optimal_w,
       the solver with faster runtime is strictly better if delta_t > 0.005s.
       If delta_t <= 0.005s, they tie for first place.
    5. Timeout Ties: If multiple solvers tie at the highest optimal_w with TIMEOUT status,
       runtime does NOT break the tie (arbitrary teardown noise) -> all tie for first place.
    6. Multi-Winner Rule: All solvers tying for the best rank are included in the returned set.

    Returns:
        Set of winning solver keys (e.g. {"kissat404"}, {"cadical300", "kissat404"}, or set()).
    """
    valid = {k: r for k, r in records.items() if r is not None}
    if not valid:
        return set()

    # If all solvers have optimal_w is None, no feasible solution was found by any solver
    # -> No winner, no bolding.
    has_feasible = any(r.optimal_w is not None for r in valid.values())
    if not has_feasible:
        # Check if anyone proved OPTIMAL (e.g. UNSAT proof)
        has_optimal = any(r.status == "OPTIMAL" for r in valid.values())
        if not has_optimal:
            return set()

    max_w = max(r.optimal_w if r.optimal_w is not None else -1 for r in valid.values())
    cands = [k for k, r in valid.items() if (r.optimal_w if r.optimal_w is not None else -1) == max_w]

    # Check status among top candidates
    opt_cands = [k for k in cands if valid[k].status == "OPTIMAL"]
    if opt_cands:
        # Runtime tie-breaker strictly among OPTIMAL candidates
        times = {
            k: valid[k].total_time_s
            for k in opt_cands
            if valid[k].total_time_s is not None
        }
        if times:
            min_t = min(times.values())
            # All solvers within 0.005s margin of fastest tie for first place
            return {k for k, t in times.items() if abs(t - min_t) <= 0.005}
        return set(opt_cands)

    if max_w == -1:
        return set()

    # None is OPTIMAL; all solvers reaching max_w (e.g. TIMEOUT at same w*) tie
    return set(cands)


def determine_better_solver(
    k: Optional[SolverRecord], c: Optional[SolverRecord]
) -> Optional[str]:
    """Determine which single solver is strictly better between Kissat and CaDiCaL.

    Returns:
        "Kissat", "CaDiCal", or None (if tie or neither found solution).
    """
    winners = determine_winning_solvers({"Kissat": k, "CaDiCal": c})
    if len(winners) == 1:
        return next(iter(winners))
    return None


def determine_bold_cells(
    k: Optional[SolverRecord], c: Optional[SolverRecord]
) -> Tuple[Set[str], Set[str]]:
    """Determine which cells (if any) should be bolded between Kissat and CaDiCaL.

    When a solver ties for first place, its cells are bolded. When no solver
    found a solution, no cells are bolded.

    Returns:
        (bold_fields_kissat, bold_fields_cadical)
    """
    winners = determine_winning_solvers({"Kissat": k, "CaDiCal": c})
    bold_fields = {"optimal_w", "time", "status"}
    bold_k = bold_fields if "Kissat" in winners else set()
    bold_c = bold_fields if "CaDiCal" in winners else set()
    return (bold_k, bold_c)


# Pastel Color Palette for Cross-Solver Comparison (8-char ARGB hex for LibreOffice compatibility)
# Zero grayish tones: warm pastels for metadata, colorful pastels for symmetry modes and solvers.
# Each cell fill color is paired with a matching bolder/darker font color from the same hue family.
PASTEL_PALETTE = {
    "metadata": {
        "tier1_fill": "FFFFF9C4",  # Warm Pastel Butter / Cream
        "tier1_font": "FF7D6608",  # Dark Warm Amber
        "tier2_fill": "FFFFFDE7",  # Light Warm Ivory / Pale Butter
        "tier2_font": "FF7D6608",  # Dark Warm Amber
    },
    "f": {
        "kissat_tier1": "FFA9DFBF",  # Pastel Mint Green
        "kissat_tier2": "FFD4EFDF",
        "kissat_font": "FF145A32",   # Dark Forest Green
        "cadical300_tier1": "FFFAD7A0",  # Pastel Apricot / Warm Amber
        "cadical300_tier2": "FFFDEBD0",
        "cadical300_font": "FF7E3B02",   # Deep Amber / Warm Russet
        "cadical_tier1": "FFA2D9CE",  # Pastel Aqua / Teal
        "cadical_tier2": "FFD1F2EB",
        "cadical_font": "FF0E6251",   # Dark Teal
        "font": "FF145A32",
    },
    "h": {
        "kissat_tier1": "FFFAD7A0",  # Pastel Apricot / Warm Amber
        "kissat_tier2": "FFFDEBD0",
        "kissat_font": "FF7E3B02",   # Deep Amber / Warm Russet
        "cadical300_tier1": "FFAED6F1",  # Pastel Sky Blue
        "cadical300_tier2": "FFD6EAF8",
        "cadical300_font": "FF1B4F72",   # Dark Navy / Deep Ocean Blue
        "cadical_tier1": "FFEDBB99",  # Pastel Coral / Peach
        "cadical_tier2": "FFFBEEE6",
        "cadical_font": "FF6E2C00",   # Dark Russet / Terracotta
        "font": "FF6E2C00",
    },
    "n": {
        "kissat_tier1": "FFAED6F1",  # Pastel Sky Blue
        "kissat_tier2": "FFD6EAF8",
        "kissat_font": "FF1B4F72",   # Dark Navy / Deep Ocean Blue
        "cadical300_tier1": "FFA9DFBF",  # Pastel Mint Green
        "cadical300_tier2": "FFD4EFDF",
        "cadical300_font": "FF145A32",   # Dark Forest Green
        "cadical_tier1": "FFD2B4DE",  # Pastel Lavender Blue
        "cadical_tier2": "FFE8DAEF",
        "cadical_font": "FF512E5F",   # Deep Plum / Violet
        "font": "FF1B4F72",
    },
    "l": {
        "kissat_tier1": "FFD7BDE2",  # Pastel Lilac
        "kissat_tier2": "FFE8DAEF",
        "kissat_font": "FF512E5F",   # Deep Plum / Violet
        "cadical300_tier1": "FFA2D9CE",  # Pastel Aqua
        "cadical300_tier2": "FFD1F2EB",
        "cadical300_font": "FF0E6251",   # Dark Teal
        "cadical_tier1": "FFF5CBA7",  # Pastel Cantaloupe
        "cadical_tier2": "FFFBEEE6",
        "cadical_font": "FF7E3B02",   # Dark Burnt Orange / Amber
        "font": "FF512E5F",
    },
}

STATUS_PASTEL_FILLS = {
    "OPTIMAL": "FFD4EFDF",      # Soft Pastel Green
    "TIMEOUT": "FFFADBD8",      # Soft Pastel Rose
    "MEMOUT": "FFFCF3CF",       # Soft Pastel Amber
    "UNSAT": "FFE8DAEF",        # Soft Pastel Violet
    "UNSAT_START": "FFE8DAEF",  # Soft Pastel Violet
    "ERROR": "FFF5C6CB",        # Soft Pastel Coral / Red
}

STATUS_FONTS = {
    "OPTIMAL": "FF196F3D",      # Dark Forest Green
    "TIMEOUT": "FF922B21",      # Dark Wine Red
    "MEMOUT": "FF7D6608",       # Dark Ochre
    "UNSAT": "FF5B2C6F",        # Deep Plum
    "UNSAT_START": "FF5B2C6F",  # Deep Plum
    "ERROR": "FF721C24",        # Dark Coral Red
}

FILL_TO_FONT_COLOR: Dict[str, str] = {
    # Metadata (Pastel Butter / Ivory -> Dark Warm Amber)
    "FFFFF9C4": "FF7D6608",
    "FFFFFDE7": "FF7D6608",
    # Mint Green family (Pastel Mint -> Dark Forest Green)
    "FFA9DFBF": "FF145A32",
    "FFD4EFDF": "FF145A32",
    # Apricot / Warm Amber family (Pastel Apricot -> Deep Amber / Warm Russet)
    "FFFAD7A0": "FF7E3B02",
    "FFFDEBD0": "FF7E3B02",
    # Aqua / Teal family (Pastel Aqua -> Dark Teal)
    "FFA2D9CE": "FF0E6251",
    "FFD1F2EB": "FF0E6251",
    # Sky Blue family (Pastel Sky Blue -> Dark Navy / Deep Ocean Blue)
    "FFAED6F1": "FF1B4F72",
    "FFD6EAF8": "FF1B4F72",
    # Coral / Peach family (Pastel Coral -> Dark Russet / Terracotta)
    "FFEDBB99": "FF6E2C00",
    "FFFBEEE6": "FF6E2C00",
    # Lavender / Lilac family (Pastel Lavender/Lilac -> Deep Plum / Violet)
    "FFD2B4DE": "FF512E5F",
    "FFD7BDE2": "FF512E5F",
    "FFE8DAEF": "FF512E5F",
    # Cantaloupe family (Pastel Cantaloupe -> Dark Burnt Orange / Amber)
    "FFF5CBA7": "FF7E3B02",
    # Status fills
    "FFFADBD8": "FF922B21",
    "FFFCF3CF": "FF7D6608",
    "FFF5C6CB": "FF721C24",
}


def derive_bolder_font_color(fill_hex: str) -> str:
    """Return a matching bolder/darker font color for any cell fill color."""
    clean = fill_hex.upper().lstrip("#")
    if len(clean) == 6:
        clean = "FF" + clean
    if clean in FILL_TO_FONT_COLOR:
        return FILL_TO_FONT_COLOR[clean]

    # Algorithmic fallback using HLS
    rgb_part = clean[2:] if len(clean) == 8 else clean
    try:
        r, g, b = (int(rgb_part[i : i + 2], 16) / 255.0 for i in (0, 2, 4))
        h, l, s = colorsys.rgb_to_hls(r, g, b)
        target_l = 0.22
        target_s = min(1.0, s * 1.35) if s > 0.08 else s
        nr, ng, nb = colorsys.hls_to_rgb(h, target_l, target_s)
        return f"FF{int(round(nr * 255)):02X}{int(round(ng * 255)):02X}{int(round(nb * 255)):02X}"
    except Exception:
        return "FF000000"


def _format_replica_sheet(
    ws: Any,
    csv_path: Path,
    header_fill_hex: str,
    header_font_hex: Optional[str] = None,
    regular_font: Optional[Font] = None,
    border: Optional[Border] = None,
) -> None:
    """Format a 1:1 copy of a summary.csv file as an Excel sheet."""
    if header_font_hex is None:
        header_font_hex = derive_bolder_font_color(header_fill_hex)
    if regular_font is None:
        regular_font = Font(name="Liberation Sans", size=10)
    if border is None:
        border = Border()

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
                            fill_hex = STATUS_PASTEL_FILLS[status_val]
                            font_hex = STATUS_FONTS.get(status_val) or derive_bolder_font_color(fill_hex)
                            cell.fill = PatternFill(
                                start_color=fill_hex,
                                end_color=fill_hex,
                                fill_type="solid",
                            )
                            cell.font = Font(
                                name="Liberation Sans",
                                size=10,
                                bold=True,
                                color=font_hex,
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
    kissat404_files: Optional[Dict[str, Optional[Path]]] = None,
    cadical300_files: Optional[Dict[str, Optional[Path]]] = None,
    cadical121_files: Optional[Dict[str, Optional[Path]]] = None,
    output_xlsx: Path = Path("AntiBandwidth_Comparison.xlsx"),
    sheet_title: str = "Comparison",
    *,
    kissat_files: Optional[Dict[str, Optional[Path]]] = None,
    cadical_files: Optional[Dict[str, Optional[Path]]] = None,
    solver_files: Optional[Dict[str, Dict[str, Optional[Path]]]] = None,
) -> None:
    """Build and format the cross-solver comparison workbook supporting 1, 2, or 3 solvers."""
    # Resolve aliases
    k4_files = kissat404_files if kissat404_files is not None else kissat_files or {}
    c3_files = cadical300_files or {}
    c1_files = cadical121_files if cadical121_files is not None else cadical_files or {}

    raw_solvers: Dict[str, Dict[str, Optional[Path]]] = {
        "kissat404": k4_files,
        "cadical300": c3_files,
        "cadical121": c1_files,
    }
    if solver_files is not None:
        raw_solvers.update(solver_files)

    # 1. Identify active modes and active solvers per mode
    active_modes: List[str] = []
    solver_data: Dict[str, Dict[str, Dict[str, SolverRecord]]] = {s.key: {} for s in SOLVER_SPECS}
    active_solvers_by_mode: Dict[str, List[SolverSpec]] = {}

    all_instances_set: Set[str] = set()
    instance_meta: Dict[str, Tuple[int, int, Optional[int], Optional[int]]] = {}

    for mode in ["f", "h", "n", "l"]:
        active_in_mode: List[SolverSpec] = []
        for spec in SOLVER_SPECS:
            fpath = raw_solvers.get(spec.key, {}).get(mode)
            if fpath is not None and fpath.is_file():
                active_in_mode.append(spec)
                data = load_csv(fpath)
                solver_data[spec.key][mode] = data
                for rec in data.values():
                    all_instances_set.add(rec.instance)
                    if rec.instance not in instance_meta or instance_meta[rec.instance][0] == 0:
                        instance_meta[rec.instance] = (
                            rec.n,
                            rec.m,
                            rec.lower_bound,
                            rec.upper_bound,
                        )

        if active_in_mode:
            active_modes.append(mode)
            active_solvers_by_mode[mode] = active_in_mode

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
    meta_pal = PASTEL_PALETTE["metadata"]
    meta_tier1_font = Font(name=font_family, size=11, bold=True, color=meta_pal["tier1_font"])
    meta_tier1_fill = PatternFill(
        start_color=meta_pal["tier1_fill"], end_color=meta_pal["tier1_fill"], fill_type="solid"
    )

    # Col 1-5: Instance Metadata
    ws.merge_cells("A1:E1")
    cell_meta = ws["A1"]
    cell_meta.value = "Instance Metadata"
    cell_meta.font = meta_tier1_font
    cell_meta.alignment = Alignment(horizontal="center", vertical="center")
    cell_meta.fill = meta_tier1_fill

    for c in range(1, 6):
        ws.cell(row=1, column=c).border = thin_border
        ws.cell(row=1, column=c).fill = meta_tier1_fill

    # Header Row 2: Col 1-5 Metadata
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

    # Build Solver Headers per Active Mode
    col_idx = 6
    for mode in active_modes:
        pal = PASTEL_PALETTE.get(mode, meta_pal)
        active_specs = active_solvers_by_mode[mode]

        for spec in active_specs:
            s_t1_fill = pal[spec.tier1_key]
            s_t2_fill = pal[spec.tier2_key]
            s_font_hex = pal.get(spec.font_key) or derive_bolder_font_color(s_t1_fill)

            s_tier1_font = Font(name=font_family, size=11, bold=True, color=s_font_hex)
            s_tier1_fill = PatternFill(
                start_color=s_t1_fill, end_color=s_t1_fill, fill_type="solid"
            )
            s_tier2_font = Font(name=font_family, size=10, bold=True, color=s_font_hex)
            s_tier2_fill = PatternFill(
                start_color=s_t2_fill, end_color=s_t2_fill, fill_type="solid"
            )

            # Tier 1 (Row 1): 3 columns merged
            s_start = col_idx
            s_end = col_idx + 2
            ws.merge_cells(
                start_row=1, start_column=s_start, end_row=1, end_column=s_end
            )
            s_cell = ws.cell(row=1, column=s_start)
            s_cell.value = f"{spec.display_name} ({mode})"
            s_cell.font = s_tier1_font
            s_cell.alignment = Alignment(horizontal="center", vertical="center")
            for c in range(s_start, s_end + 1):
                ws.cell(row=1, column=c).border = thin_border
                ws.cell(row=1, column=c).fill = s_tier1_fill

            # Tier 2 (Row 2): Optimal w, Time (s), Status
            for sub_idx, sub_name in enumerate(["Optimal w", "Time (s)", "Status"]):
                cell = ws.cell(row=2, column=s_start + sub_idx)
                cell.value = sub_name
                cell.font = s_tier2_font
                cell.alignment = Alignment(horizontal="center", vertical="center")
                cell.fill = s_tier2_fill
                cell.border = thin_border

            col_idx += 3

    total_cols = col_idx - 1

    # 3. Fill Data Rows
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

        curr_c = 6
        for mode in active_modes:
            active_specs = active_solvers_by_mode[mode]
            mode_records: Dict[str, Optional[SolverRecord]] = {
                spec.key: solver_data[spec.key][mode].get(inst)
                for spec in active_specs
            }
            winners = determine_winning_solvers(mode_records)

            for spec in active_specs:
                rec = mode_records[spec.key]
                is_winner = spec.key in winners

                # Col 1: Optimal w
                opt_val = rec.optimal_w if (rec and rec.optimal_w is not None) else "-"
                opt_cell = ws.cell(row=row_num, column=curr_c)
                opt_cell.value = opt_val
                opt_cell.font = bold_font if is_winner else regular_font
                opt_cell.alignment = Alignment(
                    horizontal="right" if opt_val != "-" else "center",
                    vertical="center",
                )
                opt_cell.border = thin_border

                # Col 2: Time (s)
                time_cell = ws.cell(row=row_num, column=curr_c + 1)
                if rec and rec.total_time_s is not None:
                    time_cell.value = rec.total_time_s
                    time_cell.number_format = "0.000"
                else:
                    time_cell.value = ""
                time_cell.font = bold_font if is_winner else regular_font
                time_cell.alignment = Alignment(horizontal="right", vertical="center")
                time_cell.border = thin_border

                # Col 3: Status
                status_cell = ws.cell(row=row_num, column=curr_c + 2)
                status_val = rec.status if rec else ""
                status_cell.value = status_val
                status_cell.alignment = Alignment(horizontal="center", vertical="center")
                status_cell.border = thin_border
                if status_val in STATUS_PASTEL_FILLS:
                    fill_hex = STATUS_PASTEL_FILLS[status_val]
                    font_hex = STATUS_FONTS.get(status_val) or derive_bolder_font_color(fill_hex)
                    status_cell.fill = PatternFill(
                        start_color=fill_hex,
                        end_color=fill_hex,
                        fill_type="solid",
                    )
                    status_cell.font = Font(
                        name=font_family,
                        size=10,
                        bold=is_winner,
                        color=font_hex,
                    )
                else:
                    status_cell.font = bold_font if is_winner else regular_font

                curr_c += 3

    # Freeze panes at A3
    ws.freeze_panes = "A3"
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
        ws.column_dimensions[col_letter].width = max(max_len + 3, 12)

    # 4. Create 1:1 CSV Replica Sheets
    for mode in active_modes:
        pal = PASTEL_PALETTE.get(mode, meta_pal)
        active_specs = active_solvers_by_mode[mode]
        for spec in active_specs:
            fpath = raw_solvers.get(spec.key, {}).get(mode)
            if fpath and fpath.is_file():
                ws_rep = wb.create_sheet(title=f"{spec.sheet_prefix}_{mode}")
                s_t1_fill = pal[spec.tier1_key]
                s_font_hex = pal.get(spec.font_key) or derive_bolder_font_color(s_t1_fill)
                _format_replica_sheet(
                    ws_rep, fpath, s_t1_fill, s_font_hex, regular_font, thin_border
                )

    output_xlsx.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output_xlsx)


def build_parser() -> argparse.ArgumentParser:
    """Construct CLI argument parser for Excel comparison generator."""
    parser = argparse.ArgumentParser(
        prog="antibandwidth-excel-comparator",
        description="Generate Excel comparison workbook between Kissat 4.0.4, CaDiCaL 3.0.0, and CaDiCal 1.2.1",
    )
    # Mode-specific CSV flags
    for mode in ["f", "h", "n", "l"]:
        # Kissat 4.0.4 flags
        parser.add_argument(
            f"--kissat404-{mode}",
            f"--kissat-{mode}",
            dest=f"kissat404_{mode}",
            type=Path,
            default=None,
            help=f"Path to Kissat 4.0.4 summary CSV for mode {mode}",
        )
        # CaDiCaL 3.0.0 flags
        parser.add_argument(
            f"--cadical300-{mode}",
            dest=f"cadical300_{mode}",
            type=Path,
            default=None,
            help=f"Path to CaDiCaL 3.0.0 summary CSV for mode {mode}",
        )
        # CaDiCal 1.2.1 flags
        parser.add_argument(
            f"--cadical121-{mode}",
            f"--cadical-{mode}",
            dest=f"cadical121_{mode}",
            type=Path,
            default=None,
            help=f"Path to CaDiCal 1.2.1 summary CSV for mode {mode}",
        )

    # Directory discovery flags
    parser.add_argument(
        "--kissat404-dir",
        "--kissat-dir",
        dest="kissat404_dir",
        type=Path,
        default=None,
        help="Directory containing Kissat summary CSVs (e.g. summary_mode_f.csv or f/summary.csv)",
    )
    parser.add_argument(
        "--cadical300-dir",
        dest="cadical300_dir",
        type=Path,
        default=None,
        help="Directory containing CaDiCaL 3.0.0 summary CSVs (e.g. summary_mode_f.csv or f/summary.csv)",
    )
    parser.add_argument(
        "--cadical121-dir",
        "--cadical-dir",
        dest="cadical121_dir",
        type=Path,
        default=None,
        help="Directory containing CaDiCal 1.2.1 summary CSVs (e.g. cadical_summary_mode_f.csv or f/summary.csv)",
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

    k4_files: Dict[str, Optional[Path]] = {}
    c3_files: Dict[str, Optional[Path]] = {}
    c1_files: Dict[str, Optional[Path]] = {}

    for mode in ["f", "h", "n", "l"]:
        # Direct CLI flags
        k4_path = getattr(args, f"kissat404_{mode}", None)
        c3_path = getattr(args, f"cadical300_{mode}", None)
        c1_path = getattr(args, f"cadical121_{mode}", None)

        # Directory discovery fallback for Kissat 4.0.4
        if not k4_path and args.kissat404_dir and args.kissat404_dir.is_dir():
            candidates = [
                args.kissat404_dir / f"summary_mode_{mode}.csv",
                args.kissat404_dir / f"kissat_summary_mode_{mode}.csv",
                args.kissat404_dir / f"kissat404_summary_mode_{mode}.csv",
                args.kissat404_dir / f"summary_{mode}.csv",
                args.kissat404_dir / mode / "summary.csv",
            ]
            for cand in candidates:
                if cand.is_file():
                    k4_path = cand
                    break

        # Directory discovery fallback for CaDiCaL 3.0.0
        if not c3_path and args.cadical300_dir and args.cadical300_dir.is_dir():
            candidates = [
                args.cadical300_dir / f"cadical300_summary_mode_{mode}.csv",
                args.cadical300_dir / f"summary_mode_{mode}.csv",
                args.cadical300_dir / f"summary_{mode}.csv",
                args.cadical300_dir / mode / "summary.csv",
            ]
            for cand in candidates:
                if cand.is_file():
                    c3_path = cand
                    break

        # Directory discovery fallback for CaDiCal 1.2.1
        if not c1_path and args.cadical121_dir and args.cadical121_dir.is_dir():
            candidates = [
                args.cadical121_dir / f"cadical_summary_mode_{mode}.csv",
                args.cadical121_dir / f"cadical121_summary_mode_{mode}.csv",
                args.cadical121_dir / f"summary_mode_{mode}.csv",
                args.cadical121_dir / f"summary_{mode}.csv",
                args.cadical121_dir / mode / "summary.csv",
            ]
            for cand in candidates:
                if cand.is_file():
                    c1_path = cand
                    break

        k4_files[mode] = k4_path
        c3_files[mode] = c3_path
        c1_files[mode] = c1_path

    active_modes = [
        m for m in ["f", "h", "n", "l"]
        if (k4_files[m] and k4_files[m].is_file())
        or (c3_files[m] and c3_files[m].is_file())
        or (c1_files[m] and c1_files[m].is_file())
    ]

    if not active_modes:
        print("Error: No valid input CSV files were provided or found.", file=sys.stderr)
        return 1

    generate_excel_comparison(
        kissat404_files=k4_files,
        cadical300_files=c3_files,
        cadical121_files=c1_files,
        output_xlsx=args.output_xlsx,
        sheet_title=args.title,
    )
    print(
        f"Successfully generated comparison workbook for mode(s) {', '.join(active_modes)}: {args.output_xlsx}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
