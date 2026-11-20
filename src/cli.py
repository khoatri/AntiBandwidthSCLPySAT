import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from src.encoding.scl_encoder import SCLEncoder
from src.solvers.optimizer import ABPOptimizer
from src.solvers.solver import ABPSolver
from src.utils.graph import Graph
from src.utils.graph_parser import parse_instance


def _resolve_output_path(output_arg: str, graph_path: str) -> Path:
    """Resolve destination JSON path, handling directory targets appropriately.

    If output_arg is an existing directory or ends with a directory separator,
    the instance filename is appended as '<instance_name>.json'.
    Otherwise, output_arg is treated as the full target file path.
    """
    out_path = Path(output_arg)
    if out_path.is_dir() or str(output_arg).endswith(("/", "\\")):
        out_path.mkdir(parents=True, exist_ok=True)
        inst_name = Path(graph_path).name
        return out_path / f"{inst_name}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    return out_path


def build_parser() -> argparse.ArgumentParser:
    """Construct command-line argument parser with solve, optimize, and inspect subcommands."""
    parser = argparse.ArgumentParser(
        prog="antibandwidth",
        description="SCL encoding for the Anti-Bandwidth Problem (ABP) using PySAT and kissat404",
    )
    subparsers = parser.add_subparsers(dest="subcommand", help="Available subcommands")

    # -------------------------------------------------------------------------
    # Subcommand: inspect
    # -------------------------------------------------------------------------
    inspect_parser = subparsers.add_parser(
        "inspect",
        help="Inspect graph structure and theoretical formula size without solving",
    )
    inspect_parser.add_argument(
        "-g", "--graph",
        required=True,
        type=str,
        help="Path to input graph instance (*.mtx.rnd)",
    )
    inspect_parser.add_argument(
        "-w", "--width",
        type=int,
        default=None,
        help="Target bandwidth threshold w for formula calculation (default: graph predefined lower bound, or 2)",
    )
    inspect_parser.add_argument(
        "-s", "--sym",
        choices=["n", "f", "h", "l"],
        default="n",
        help="Symmetry breaking mode: n (none), f (first-vertex), h (half/max-degree), l (lowest-degree) (default: n)",
    )

    # -------------------------------------------------------------------------
    # Subcommand: solve
    # -------------------------------------------------------------------------
    solve_parser = subparsers.add_parser(
        "solve",
        help="Solve a single decision instance: Is AB(G) >= w?",
    )
    solve_parser.add_argument(
        "-g", "--graph",
        required=True,
        type=str,
        help="Path to input graph instance (*.mtx.rnd)",
    )
    solve_parser.add_argument(
        "-w", "--width",
        required=False,
        type=int,
        default=None,
        help="Target bandwidth threshold w (2 <= w <= n) (default: graph predefined lower bound, or 2)",
    )
    solve_parser.add_argument(
        "-s", "--sym",
        choices=["n", "f", "h", "l"],
        default="n",
        help="Symmetry breaking mode: n (none), f (first-vertex), h (half/max-degree), l (lowest-degree) (default: n)",
    )
    solve_parser.add_argument(
        "-t", "--timeout",
        type=float,
        default=None,
        help="Maximum solve time in seconds",
    )
    solve_parser.add_argument(
        "-m", "--mem-limit",
        type=float,
        default=None,
        help="Maximum memory limit in GB (e.g. 30.0)",
    )
    solve_parser.add_argument(
        "-o", "--output",
        type=str,
        default=None,
        help="Path to save output JSON result",
    )
    solve_parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Suppress human-readable console output",
    )

    # -------------------------------------------------------------------------
    # Subcommand: optimize
    # -------------------------------------------------------------------------
    opt_parser = subparsers.add_parser(
        "optimize",
        help="Find optimal anti-bandwidth w* via incremental linear search",
    )
    opt_parser.add_argument(
        "-g", "--graph",
        required=True,
        type=str,
        help="Path to input graph instance (*.mtx.rnd)",
    )
    opt_parser.add_argument(
        "--start-w",
        type=int,
        default=None,
        help="Starting lower bound for linear search (default: graph predefined lower bound, or 2)",
    )
    opt_parser.add_argument(
        "-s", "--sym",
        choices=["n", "f", "h", "l"],
        default="n",
        help="Symmetry breaking mode: n (none), f (first-vertex), h (half/max-degree), l (lowest-degree) (default: n)",
    )
    opt_parser.add_argument(
        "-t", "--timeout",
        type=float,
        default=None,
        help="Total maximum time in seconds for the entire optimization search",
    )
    opt_parser.add_argument(
        "-m", "--mem-limit",
        type=float,
        default=None,
        help="Memory limit in GB per decision step (e.g. 30.0)",
    )
    opt_parser.add_argument(
        "-o", "--output",
        type=str,
        default=None,
        help="Path to export optimization results to JSON",
    )
    opt_parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Suppress progress prints to console",
    )

    return parser


def handle_inspect(args: argparse.Namespace) -> int:
    """Handle the inspect subcommand."""
    try:
        graph = parse_instance(args.graph)
    except Exception as e:
        sys.stderr.write(f"Error loading graph from '{args.graph}': {e}\n")
        return 1

    lb = graph.get_lower_bound()
    ub = graph.get_upper_bound()
    u_theo = graph.get_theoretical_upper_bound()

    effective_w = lb if args.width is None else args.width
    if effective_w < 2 or effective_w > graph.n:
        sys.stderr.write(
            f"Error: Target bandwidth w must satisfy 2 <= w <= n ({graph.n}), got w={effective_w}\n"
        )
        return 1

    # Theoretical calculations
    encoder = SCLEncoder(graph=graph, w=effective_w, sym_mode=args.sym)
    n_vars_theo, n_clauses_theo = encoder.expected_counts()

    deg_vals = list(graph.degrees.values())
    min_deg = min(deg_vals) if deg_vals else 0
    max_deg = max(deg_vals) if deg_vals else 0
    avg_deg = (sum(deg_vals) / len(deg_vals)) if deg_vals else 0.0

    k_blocks = math.ceil(graph.n / effective_w)
    d_rem = graph.n - (k_blocks - 1) * effective_w

    sym_v = graph.get_symmetry_vertex(args.sym)
    sym_desc = f"{args.sym}"
    if sym_v is not None:
        sym_desc += f" (vertex {sym_v}, degree {graph.degrees[sym_v]})"

    w_annotation = " (predefined lower bound)" if args.width is None else ""

    print("=" * 60)
    print("              Anti-Bandwidth Graph Inspection")
    print("=" * 60)
    print(f"Instance:            {args.graph}")
    print(f"Problem Name:        {graph.name or Path(args.graph).name}")
    print(f"Vertices (n):        {graph.n}")
    print(f"Edges (m):           {graph.m}")
    print(f"Degree (min/avg/max): {min_deg} / {avg_deg:.2f} / {max_deg}")
    print(f"Isolated Vertices:   {graph.has_isolated_vertices()}")
    print(f"Predefined Lower Bound (LB): {lb}")
    print(f"Predefined Upper Bound (UB): {ub}")
    print(f"Theoretical Bound U: {u_theo}")
    if graph.best_known_w is not None:
        print(f"Best Known w:        {graph.best_known_w}")
    print()
    print(f"Target Threshold w:  {effective_w}{w_annotation}")
    print(f"Symmetry Mode:       {sym_desc}")
    print(f"Block Count (K):     {k_blocks} (block size w={effective_w}, remainder d={d_rem})")
    print()
    print("--- Theoretical SCL Formula Size ---")
    print(f"Theoretical Variables (N): {n_vars_theo:,}")
    print(f"Theoretical Clauses (C):   {n_clauses_theo:,}")
    print("=" * 60)
    return 0


def handle_solve(args: argparse.Namespace) -> int:
    """Handle the solve subcommand."""
    try:
        graph = parse_instance(args.graph)
    except Exception as e:
        sys.stderr.write(f"Error loading graph from '{args.graph}': {e}\n")
        return 1

    effective_w = graph.get_lower_bound() if args.width is None else args.width
    if effective_w < 2:
        sys.stderr.write(f"Error: Width w must be >= 2, got w={effective_w}\n")
        return 1
    if effective_w > graph.n:
        sys.stderr.write(
            f"Error: Width w cannot exceed number of vertices n={graph.n}, got w={effective_w}\n"
        )
        return 1

    solver = ABPSolver()
    res = solver.solve(
        graph=graph,
        w=effective_w,
        sym_mode=args.sym,
        timeout=args.timeout,
        mem_limit=args.mem_limit,
    )

    if not args.quiet:
        timeout_str = f"{args.timeout}s" if args.timeout is not None else "None"
        mem_str = f"{args.mem_limit} GB" if args.mem_limit is not None else "None"
        w_annotation = " (predefined lower bound)" if args.width is None else ""
        print("=" * 60)
        print("              Anti-Bandwidth Decision Problem")
        print("=" * 60)
        print(f"Instance:      {args.graph}")
        print(f"Vertices (n):  {graph.n}, Edges (m): {graph.m}")
        print(f"Target w:      {effective_w}{w_annotation}")
        print(f"Symmetry Mode: {args.sym}")
        print(f"Timeout:       {timeout_str}, Mem Limit: {mem_str}")
        print("-" * 60)
        print(f"Status:        {res.status}")
        print(f"Solve Time:    {res.solve_time:.4f}s")
        print(f"Encoding Time: {res.encoding_time:.4f}s")
        print(f"Total Time:    {res.total_time:.4f}s")
        if res.status == "SAT" and res.labeling is not None:
            is_valid = res.stats.get("verified", False)
            print(f"Verified:      {is_valid}")
            sample = {v: res.labeling[v] for v in sorted(res.labeling.keys())[:8]}
            print(f"Labeling (sample): {sample}{'...' if len(res.labeling) > 8 else ''}")
        print("=" * 60)

    if args.output is not None:
        out_path = _resolve_output_path(args.output, args.graph)
        payload: dict[str, Any] = {
            "instance": args.graph,
            "problem_name": graph.name or Path(args.graph).name,
            "n": graph.n,
            "m": graph.m,
            "w": res.w,
            "sym_mode": args.sym,
            "status": res.status,
            "solve_time": round(res.solve_time, 4),
            "encoding_time": round(res.encoding_time, 4),
            "total_time": round(res.total_time, 4),
            "stats": res.stats,
            "verified": res.stats.get("verified", False),
            "labeling": {str(k): v for k, v in res.labeling.items()} if res.labeling else None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        try:
            out_path.write_text(json.dumps(payload, indent=2))
            if not args.quiet:
                print(f"Results saved to: {out_path}")
        except Exception as e:
            sys.stderr.write(f"Error saving output JSON to '{out_path}': {e}\n")

    return 0 if res.status in ("SAT", "UNSAT") else 1


def handle_optimize(args: argparse.Namespace) -> int:
    """Handle the optimize subcommand."""
    try:
        graph = parse_instance(args.graph)
    except Exception as e:
        sys.stderr.write(f"Error loading graph from '{args.graph}': {e}\n")
        return 1

    effective_start_w = graph.get_lower_bound() if args.start_w is None else args.start_w
    if effective_start_w < 2:
        sys.stderr.write(f"Error: start-w must be >= 2, got start-w={effective_start_w}\n")
        return 1

    optimizer = ABPOptimizer()
    ub = graph.get_upper_bound()

    if not args.quiet:
        timeout_str = f"{args.timeout}s" if args.timeout is not None else "None"
        mem_str = f"{args.mem_limit} GB" if args.mem_limit is not None else "None"
        start_annotation = " (predefined lower bound)" if args.start_w is None else ""
        print("=" * 60)
        print("           Anti-Bandwidth Optimization Search")
        print("=" * 60)
        print(f"Instance:      {args.graph}")
        print(f"Vertices (n):  {graph.n}, Edges (m): {graph.m}")
        print(f"Start w:       {effective_start_w}{start_annotation}")
        print(f"Upper Bound w: {ub}")
        print(f"Symmetry:      {args.sym}")
        print(f"Total Timeout: {timeout_str}, Mem Limit: {mem_str}")
        print("-" * 60)
        print(f"{'Step w':<8} {'Status':<12} {'Solve (s)':<12} {'Total (s)':<12}")
        print("-" * 60)

    res = optimizer.linear_search(
        graph=graph,
        start_w=effective_start_w,
        sym_mode=args.sym,
        timeout=args.timeout,
        mem_limit=args.mem_limit,
    )

    if not args.quiet:
        for s in res.steps:
            print(f"{s.w:<8} {s.status:<12} {s.solve_time:<12.4f} {s.total_time:<12.4f}")
        print("=" * 60)
        print(f"Final Status:         {res.status}")
        print(f"Optimal Bandwidth w*: {res.optimal_w}")
        print(f"Upper Bound U:        {res.upper_bound}")
        print(f"Total Search Time:    {res.total_time:.4f}s")
        is_verified = (
            res.optimal_labeling is not None
            and res.optimal_w is not None
            and any(s.w == res.optimal_w and s.stats.get("verified", False) for s in res.steps)
        )
        if res.optimal_labeling is not None and res.optimal_w is not None:
            print(f"Verified Solution:    {is_verified}")
        print("=" * 60)

    if args.output is not None:
        out_path = _resolve_output_path(args.output, args.graph)
        is_verified = (
            res.optimal_labeling is not None
            and res.optimal_w is not None
            and any(s.w == res.optimal_w and s.stats.get("verified", False) for s in res.steps)
        )

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
            "instance": args.graph,
            "problem_name": graph.name or Path(args.graph).name,
            "n": graph.n,
            "m": graph.m,
            "start_w": args.start_w,
            "sym_mode": args.sym,
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
        try:
            out_path.write_text(json.dumps(payload, indent=2))
            if not args.quiet:
                print(f"Results saved to: {out_path}")
        except Exception as e:
            sys.stderr.write(f"Error saving output JSON to '{out_path}': {e}\n")

    return 0 if res.status in ("OPTIMAL", "UNSAT_START") else 1


def main(argv: Optional[list[str]] = None) -> int:
    """Main CLI entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.subcommand is None:
        parser.print_help()
        return 2

    if args.subcommand == "inspect":
        return handle_inspect(args)
    elif args.subcommand == "solve":
        return handle_solve(args)
    elif args.subcommand == "optimize":
        return handle_optimize(args)
    else:
        parser.print_help()
        return 2


if __name__ == "__main__":
    sys.exit(main())
