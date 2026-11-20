import argparse
import csv
import json
import os
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# Ensure repository root is on sys.path
repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from src.solvers.optimizer import ABPOptimizer
from src.utils.graph_parser import parse_instance
from src.utils.solution_verifier import verify_solution

CSV_COLUMNS = [
    "instance",
    "n",
    "m",
    "best_known_w",
    "optimal_w",
    "status",
    "total_time_s",
    "steps_evaluated",
    "sym_mode",
    "verified",
]


def build_automation_parser() -> argparse.ArgumentParser:
    """Build argument parser for the batch automation campaign runner."""
    parser = argparse.ArgumentParser(
        prog="antibandwidth-automation",
        description="Automated benchmark campaign runner for the Anti-Bandwidth Problem",
    )
    parser.add_argument(
        "-i", "--instances-dir",
        type=str,
        default="instances",
        help="Directory containing benchmark graph instances (*.mtx.rnd) (default: instances)",
    )
    parser.add_argument(
        "-o", "--output-dir",
        type=str,
        default="benchmarks",
        help="Directory where campaign outputs (summary.csv, manifest, results/) are stored (default: benchmarks)",
    )
    parser.add_argument(
        "-s", "--sym",
        choices=["n", "f", "h", "l"],
        default="n",
        help="Symmetry breaking mode: n (none), f (first-vertex), h (half/max-degree), l (lowest-degree) (default: n)",
    )
    parser.add_argument(
        "-t", "--timeout",
        type=float,
        default=1800.0,
        help="Total timeout in seconds per instance for linear search (default: 1800.0)",
    )
    parser.add_argument(
        "-m", "--mem-limit",
        type=float,
        default=30.0,
        help="Maximum memory limit in GB per decision step (default: 30.0)",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip instances that already have a completed result JSON file in output_dir/results",
    )
    parser.add_argument(
        "--start-w-mode",
        choices=["default", "best_known"],
        default="default",
        help="Starting lower bound mode: 'default' starts at 2, 'best_known' starts at best_known_w from header (default: default)",
    )
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Suppress per-instance console progress logs",
    )
    return parser


def _discover_instances(instances_dir: Path) -> list[Path]:
    """Find and sort matching instance files."""
    if not instances_dir.exists():
        return []

    files = [f for f in instances_dir.iterdir() if f.is_file() and f.name.endswith(".mtx.rnd")]
    return sorted(files, key=lambda p: p.name)


def _process_instance(
    inst_path: Path,
    output_dir: Path,
    sym_mode: str,
    timeout: float,
    mem_limit: float,
    start_w_mode: str,
) -> dict[str, Any]:
    """Run optimization search for a single instance and save JSON log."""
    graph = parse_instance(str(inst_path))

    start_w = 2
    if start_w_mode == "best_known" and graph.best_known_w is not None:
        start_w = max(2, graph.best_known_w)

    optimizer = ABPOptimizer()
    res = optimizer.linear_search(
        graph=graph,
        start_w=start_w,
        sym_mode=sym_mode,
        timeout=timeout,
        mem_limit=mem_limit,
    )

    is_verified = False
    if res.optimal_labeling is not None and res.optimal_w is not None:
        is_verified, _ = verify_solution(graph, res.optimal_labeling, res.optimal_w)

    # Save detailed JSON in results/
    results_dir = output_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    json_path = results_dir / f"{inst_path.name}.json"

    steps_data: list[dict[str, Any]] = [
        {
            "w": s.w,
            "status": s.status,
            "solve_time": round(s.solve_time, 4),
            "encoding_time": round(s.encoding_time, 4),
            "total_time": round(s.total_time, 4),
            "stats": s.stats,
        }
        for s in res.steps
    ]

    payload: dict[str, Any] = {
        "instance": inst_path.name,
        "problem_name": graph.name or inst_path.name,
        "n": graph.n,
        "m": graph.m,
        "best_known_w": graph.best_known_w,
        "start_w": start_w,
        "sym_mode": sym_mode,
        "upper_bound": res.upper_bound,
        "optimal_w": res.optimal_w,
        "status": res.status,
        "total_time": round(res.total_time, 4),
        "verified": is_verified,
        "optimal_labeling": (
            {str(k): v for k, v in res.optimal_labeling.items()}
            if res.optimal_labeling
            else None
        ),
        "steps": steps_data,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    json_path.write_text(json.dumps(payload, indent=2))

    return {
        "instance": inst_path.name,
        "n": str(graph.n),
        "m": str(graph.m),
        "best_known_w": str(graph.best_known_w) if graph.best_known_w is not None else "",
        "optimal_w": str(res.optimal_w) if res.optimal_w is not None else "",
        "status": res.status,
        "total_time_s": f"{res.total_time:.3f}",
        "steps_evaluated": str(len(res.steps)),
        "sym_mode": sym_mode,
        "verified": str(is_verified),
    }


def run_campaign(args: argparse.Namespace) -> int:
    """Execute the benchmark campaign across matching instances."""
    instances_dir = Path(args.instances_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    results_dir = output_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    instances = _discover_instances(instances_dir)
    if not instances:
        print(f"No matching instance files found in '{instances_dir}'")
        return 0

    # Write campaign manifest
    manifest_path = output_dir / "campaign_manifest.json"
    manifest_data = {
        "campaign_start_utc": datetime.now(timezone.utc).isoformat(),
        "instances_dir": str(instances_dir.resolve()),
        "output_dir": str(output_dir.resolve()),
        "sym_mode": args.sym,
        "timeout_s": args.timeout,
        "mem_limit_gb": args.mem_limit,
        "jobs": 1,
        "skip_existing": args.skip_existing,
        "start_w_mode": args.start_w_mode,
        "solver": "kissat404",
        "solver_backend": "PySAT Solver(name='kissat404')",
        "python_version": sys.version,
        "os_platform": platform.platform(),
        "total_instances": len(instances),
    }
    manifest_path.write_text(json.dumps(manifest_data, indent=2))

    summary_csv = output_dir / "summary.csv"
    existing_instances: set[str] = set()

    # If CSV already exists, read processed instances to prevent duplicate header/records
    if summary_csv.exists() and summary_csv.stat().st_size > 0:
        with open(summary_csv, mode="r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("instance"):
                    existing_instances.add(row["instance"])

    csv_file = open(summary_csv, mode="a", newline="", encoding="utf-8")
    writer = csv.DictWriter(csv_file, fieldnames=CSV_COLUMNS)
    if summary_csv.stat().st_size == 0:
        writer.writeheader()
        csv_file.flush()

    total = len(instances)
    if not args.quiet:
        print(f"Starting benchmark campaign: {total} instances discovered")
        print(f"Output directory: {output_dir}")
        print(f"Symmetry: {args.sym}, Timeout: {args.timeout}s, Mem limit: {args.mem_limit} GB")
        print("-" * 75)

    try:
        for idx, inst_path in enumerate(instances, start=1):
            json_file = results_dir / f"{inst_path.name}.json"

            if args.skip_existing and json_file.exists():
                if not args.quiet:
                    print(f"[{idx}/{total}] Skipping existing: {inst_path.name}")
                continue

            try:
                row = _process_instance(
                    inst_path=inst_path,
                    output_dir=output_dir,
                    sym_mode=args.sym,
                    timeout=args.timeout,
                    mem_limit=args.mem_limit,
                    start_w_mode=args.start_w_mode,
                )
            except Exception as exc:
                sys.stderr.write(f"[{idx}/{total}] ERROR processing {inst_path.name}: {exc}\n")
                row = {col: "" for col in CSV_COLUMNS}
                row["instance"] = inst_path.name
                row["status"] = "ERROR"

            # Write to CSV immediately and flush to guarantee persistence
            if row["instance"] not in existing_instances:
                writer.writerow(row)
                csv_file.flush()
                existing_instances.add(row["instance"])

            if not args.quiet:
                w_str = row["optimal_w"] if row["optimal_w"] else "None"
                print(
                    f"[{idx}/{total}] {inst_path.name:<25} "
                    f"w*={w_str:<4} status={row['status']:<10} "
                    f"time={row['total_time_s']:<8}s verified={row['verified']}"
                )
    finally:
        csv_file.close()

    if not args.quiet:
        print("-" * 75)
        print(f"Campaign completed. Summary: {summary_csv}")

    return 0


def main(argv: Optional[list[str]] = None) -> int:
    """Entry point for the automation campaign runner."""
    parser = build_automation_parser()
    args = parser.parse_args(argv)
    return run_campaign(args)


if __name__ == "__main__":
    sys.exit(main())
