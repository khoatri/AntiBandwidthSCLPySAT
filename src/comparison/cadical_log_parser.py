import argparse
import csv
from dataclasses import dataclass
import os
from pathlib import Path
import re
import sys
from typing import Any, Optional

# Ensure repository root is on sys.path
repo_root = Path(__file__).resolve().parent.parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

CSV_COLUMNS = [
    "instance",
    "n",
    "m",
    "lower_bound",
    "upper_bound",
    "optimal_w",
    "status",
    "total_time_s",
    "steps_evaluated",
    "sym_mode",
    "verified",
]


@dataclass
class CadicalLogResult:
    """Parsed outcome of an AntiBandwidthSCL (CaDiCaL backend) benchmark log."""

    instance: str
    n: int
    m: int
    lower_bound: Optional[int]
    upper_bound: Optional[int]
    optimal_w: Optional[int]
    status: str
    total_time_s: float
    steps_evaluated: int
    sym_mode: str
    verified: bool


def natural_sort_key(s: str) -> list[Any]:
    """Helper for natural alphanumeric sorting (e.g., file_2 before file_10)."""
    return [
        int(text) if text.isdigit() else text.lower()
        for text in re.split(r"(\d+)", s)
    ]


def derive_edge_count(n: int, w: int, glue_constraints: int) -> int:
    """Analytically calculate number of graph edges m from glue staircase constraints.

    In the SCL ladder formulation, each edge generates:
        e = 4 * (n - w + 1) - 3 * (n // w)
    glue staircase exclusion clauses.
    Therefore:
        m = glue_constraints // e.
    """
    e = 4 * (n - w + 1) - 3 * (n // w)
    if e > 0:
        return glue_constraints // e
    return 0


def _lookup_edge_count_from_file(
    instance_name: str, instances_dir: Optional[Path]
) -> Optional[int]:
    """Attempt to parse edge count m from the instance file header line 2."""
    candidate_paths: list[Path] = []
    if instances_dir is not None:
        candidate_paths.append(instances_dir / instance_name)
    candidate_paths.append(repo_root / "instances" / instance_name)

    for p in candidate_paths:
        if p.is_file():
            try:
                with open(p, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#") or line.startswith("Nombre"):
                            continue
                        parts = line.split()
                        if len(parts) >= 2 and all(part.isdigit() for part in parts[:2]):
                            # Format: <n> <m> or <n> <ignored> <m>
                            return int(parts[-1])
            except Exception:
                pass
    return None


def parse_cadical_log(
    file_path: Path,
    instances_dir: Optional[Path] = None,
    default_sym_mode: Optional[str] = None,
) -> CadicalLogResult:
    """Parse a single CaDiCaL .out log file generated under runlim."""
    text = file_path.read_text(encoding="utf-8", errors="ignore")

    # 1. Instance name
    inst_match = re.search(
        r"\[runlim\]\s+argv\[1\]:\s*(?:.*/)?([^/\s]+\.mtx\.rnd)", text
    )
    if not inst_match:
        inst_match = re.search(
            r"c\s+Antibandwidth problem with w\s*=\s*\d+\s*\(\s*([^/\s]+\.mtx\.rnd)\s*\)",
            text,
        )

    if inst_match:
        instance_name = inst_match.group(1).strip()
    else:
        # Fallback from filename, e.g. B-ibm32.--ladder_2026-11-22_10:56:18.out -> B-ibm32.mtx.rnd
        base = file_path.name
        base = re.sub(r"\.--ladder.*", "", base)
        base = re.sub(r"\.out$", "", base)
        if not base.endswith(".mtx.rnd"):
            base = f"{base}.mtx.rnd"
        instance_name = base

    # 2. Sinnl bounds
    lb_match = re.search(r"c\s+LB-w\s*=\s*(\d+)", text)
    lower_bound = int(lb_match.group(1)) if lb_match else None

    ub_match = re.search(r"c\s+UB-w\s*=\s*(\d+)", text)
    upper_bound = int(ub_match.group(1)) if ub_match else None

    # 3. Symmetry breaking mode
    sym_mode = default_sym_mode
    if not sym_mode:
        sym_match = re.search(
            r"c\s+Encode symmetry breaking with option:\s*([nfhl])", text
        )
        if not sym_match:
            sym_match = re.search(r"\[runlim\]\s+argv\[4\]:\s*([nfhl])", text)
        sym_mode = sym_match.group(1).strip() if sym_match else "n"

    # 4. Vertices n
    n_match = re.search(r"c\s+Initializing a Ladder encoder with n\s*=\s*(\d+)", text)
    n = int(n_match.group(1)) if n_match else 0

    # 5. Steps evaluated
    step_splits = re.split(r"c\s+Antibandwidth problem with w\s*=\s*(\d+)", text)
    steps_w: list[int] = []
    sat_steps: list[int] = []
    verified = True

    # When splitting by regex with a capturing group, the matched groups appear at odd indices
    for i in range(1, len(step_splits), 2):
        step_w = int(step_splits[i])
        block_body = step_splits[i + 1] if i + 1 < len(step_splits) else ""
        steps_w.append(step_w)

        is_sat = bool(re.search(r"\bs\s+SAT\b", block_body))
        if is_sat:
            sat_steps.append(step_w)

        calc_match = re.search(
            r"p\s+calculated antibandwidth\s*=\s*(\d+)", block_body
        )
        if calc_match:
            calc_abw = int(calc_match.group(1))
            if is_sat and calc_abw < step_w:
                verified = False

    steps_evaluated = len(steps_w)

    # 6. Edges m
    m = _lookup_edge_count_from_file(instance_name, instances_dir)
    if m is None and n > 0:
        # Fallback to analytical derivation
        glue_match = re.search(
            r"c\s+Obj k glue staircase constraints:\s*(\d+)", text
        )
        if glue_match and steps_w:
            m = derive_edge_count(
                n=n, w=steps_w[0], glue_constraints=int(glue_match.group(1))
            )
    if m is None:
        m = 0

    # 7. Runlim termination status and runtime
    runlim_status_match = re.search(r"\[runlim\]\s+status:\s*([^\n\r]+)", text)
    raw_status = (
        runlim_status_match.group(1).strip().lower()
        if runlim_status_match
        else "ok"
    )

    real_time_match = re.search(r"\[runlim\]\s+real:\s*([\d\.]+)\s*seconds", text)
    if real_time_match:
        total_time_s = float(real_time_match.group(1))
    else:
        cpu_time_match = re.search(r"\[runlim\]\s+time:\s*([\d\.]+)\s*seconds", text)
        total_time_s = float(cpu_time_match.group(1)) if cpu_time_match else 0.0

    optimal_w: Optional[int] = None
    if "out of time" in raw_status:
        status = "TIMEOUT"
        if sat_steps:
            optimal_w = max(sat_steps)
    elif "out of space" in raw_status or "bad_alloc" in text:
        status = "MEMOUT"
        if sat_steps:
            optimal_w = max(sat_steps)
    elif "ok" in raw_status:
        if sat_steps:
            status = "OPTIMAL"
            optimal_w = max(sat_steps)
        elif steps_w:
            status = "UNSAT"
        else:
            status = "UNKNOWN"
    else:
        status = "ERROR"
        if sat_steps:
            optimal_w = max(sat_steps)

    return CadicalLogResult(
        instance=instance_name,
        n=n,
        m=m,
        lower_bound=lower_bound,
        upper_bound=upper_bound,
        optimal_w=optimal_w,
        status=status,
        total_time_s=total_time_s,
        steps_evaluated=steps_evaluated,
        sym_mode=sym_mode,
        verified=verified,
    )


def parse_cadical_directory(
    input_dir: Path,
    output_csv: Optional[Path] = None,
    sym_mode: Optional[str] = None,
    instances_dir: Optional[Path] = None,
    quiet: bool = False,
) -> list[CadicalLogResult]:
    """Parse all .out logs in input_dir and optionally export summary.csv."""
    if not input_dir.is_dir():
        raise FileNotFoundError(f"Input directory not found: {input_dir}")

    log_files = [f for f in input_dir.iterdir() if f.is_file() and f.name.endswith(".out")]
    log_files.sort(key=lambda p: natural_sort_key(p.name))

    results: list[CadicalLogResult] = []
    for log_path in log_files:
        try:
            res = parse_cadical_log(
                file_path=log_path,
                instances_dir=instances_dir,
                default_sym_mode=sym_mode,
            )
            results.append(res)
            if not quiet:
                print(
                    f"Parsed {log_path.name}: {res.instance} | "
                    f"w*={res.optimal_w} | status={res.status} | time={res.total_time_s:.3f}s"
                )
        except Exception as e:
            if not quiet:
                print(f"Error parsing {log_path.name}: {e}", file=sys.stderr)

    if output_csv is not None:
        output_csv.parent.mkdir(parents=True, exist_ok=True)
        with open(output_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
            writer.writeheader()
            for r in results:
                writer.writerow(
                    {
                        "instance": r.instance,
                        "n": str(r.n),
                        "m": str(r.m),
                        "lower_bound": str(r.lower_bound) if r.lower_bound is not None else "",
                        "upper_bound": str(r.upper_bound) if r.upper_bound is not None else "",
                        "optimal_w": str(r.optimal_w) if r.optimal_w is not None else "",
                        "status": r.status,
                        "total_time_s": f"{r.total_time_s:.3f}",
                        "steps_evaluated": str(r.steps_evaluated),
                        "sym_mode": r.sym_mode,
                        "verified": str(r.verified),
                    }
                )

    return results


def build_parser() -> argparse.ArgumentParser:
    """Construct CLI argument parser for CaDiCaL log parsing."""
    parser = argparse.ArgumentParser(
        prog="antibandwidth-cadical-parser",
        description="Parse CaDiCaL (.out) runlim logs into summary.csv",
    )
    parser.add_argument(
        "-i",
        "--input-dir",
        type=Path,
        required=True,
        help="Directory containing CaDiCaL .out log files",
    )
    parser.add_argument(
        "-o",
        "--output-csv",
        type=Path,
        default=None,
        help="Path for destination summary CSV file (default: <input-dir>/summary.csv)",
    )
    parser.add_argument(
        "-s",
        "--sym-mode",
        choices=["n", "f", "h", "l"],
        default=None,
        help="Symmetry breaking mode (default: auto-detected from logs)",
    )
    parser.add_argument(
        "--instances-dir",
        type=Path,
        default=None,
        help="Directory containing original benchmark instances (*.mtx.rnd) to cross-check graph parameters",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress per-file console progress messages",
    )
    return parser


def main() -> int:
    """CLI execution entry point."""
    parser = build_parser()
    args = parser.parse_args()

    out_csv = args.output_csv
    if out_csv is None:
        out_csv = args.input_dir / "summary.csv"

    results = parse_cadical_directory(
        input_dir=args.input_dir,
        output_csv=out_csv,
        sym_mode=args.sym_mode,
        instances_dir=args.instances_dir,
        quiet=args.quiet,
    )
    print(f"Successfully processed {len(results)} logs -> {out_csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
