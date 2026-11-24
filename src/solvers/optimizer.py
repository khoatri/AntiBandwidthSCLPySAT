import time
from dataclasses import dataclass
from typing import Optional

from src.solvers.solver import ABPSolver, SolveResult
from src.utils.graph import Graph


@dataclass(frozen=True)
class OptimizationResult:
    """Outcome of linear search optimization for the Anti-Bandwidth Problem."""

    optimal_w: Optional[int]
    optimal_labeling: Optional[dict[int, int]]
    status: str  # "OPTIMAL" | "TIMEOUT" | "MEMOUT" | "UNSAT_START" | "ERROR"
    steps: list[SolveResult]
    total_time: float
    upper_bound: int


class ABPOptimizer:
    """Incremental linear search optimizer for the Anti-Bandwidth Problem (ABP).

    Evaluates w = start_w, start_w + 1, ... sequentially using fresh solver instances.
    Terminates at first UNSAT, early exit at upper bound U, or limits (TIMEOUT/MEMOUT).
    Supports a total instance timeout, bounding the cumulative time of the search.
    """

    def __init__(
        self,
        solver: Optional[ABPSolver] = None,
        solver_name: str = "kissat404",
    ) -> None:
        self.solver = solver if solver is not None else ABPSolver(solver_name=solver_name)
        self.solver_name: str = self.solver.solver_name

    def linear_search(
        self,
        graph: Graph,
        start_w: Optional[int] = None,
        sym_mode: str = "n",
        timeout: Optional[float] = None,
        mem_limit: Optional[float] = None,
    ) -> OptimizationResult:
        """Execute linear search to find optimal anti-bandwidth.

        Args:
            graph: The input Graph.
            start_w: Starting threshold (default: None, resolves to graph.get_lower_bound()).
            sym_mode: Symmetry breaking mode ('n', 'f', 'h', 'l').
            timeout: Total maximum time in seconds for the entire optimization search.
            mem_limit: Memory limit in GB per decision step.

        Returns:
            OptimizationResult containing optimal bandwidth, certificate labeling,
            search steps, and status.
        """
        upper_bound = graph.get_upper_bound()
        effective_start_w = (
            max(2, graph.get_lower_bound()) if start_w is None else max(2, start_w)
        )

        if effective_start_w > upper_bound:
            return OptimizationResult(
                optimal_w=None,
                optimal_labeling=None,
                status="UNSAT_START",
                steps=[],
                total_time=0.0,
                upper_bound=upper_bound,
            )

        steps: list[SolveResult] = []
        best_w: Optional[int] = None
        best_labeling: Optional[dict[int, int]] = None
        status = "OPTIMAL"
        optimal_w: Optional[int] = None
        optimal_labeling: Optional[dict[int, int]] = None

        t_start = time.perf_counter()

        for w in range(effective_start_w, upper_bound + 1):
            remaining_timeout: Optional[float] = None
            if timeout is not None:
                elapsed = time.perf_counter() - t_start
                remaining_timeout = timeout - elapsed
                if remaining_timeout <= 0.0:
                    status = "TIMEOUT"
                    optimal_w = best_w
                    optimal_labeling = best_labeling
                    break

            step_res = self.solver.solve(
                graph=graph,
                w=w,
                sym_mode=sym_mode,
                timeout=remaining_timeout,
                mem_limit=mem_limit,
            )
            steps.append(step_res)

            if step_res.status == "UNSAT":
                if w == effective_start_w:
                    status = "UNSAT_START"
                    optimal_w = None
                    optimal_labeling = None
                else:
                    status = "OPTIMAL"
                    optimal_w = w - 1
                    optimal_labeling = best_labeling
                break

            elif step_res.status == "SAT":
                best_w = w
                best_labeling = step_res.labeling
                if w == upper_bound:
                    # Reached the proven upper bound (benchmark or theoretical limit).
                    # Finding SAT at upper_bound proves optimality.
                    status = "OPTIMAL"
                    optimal_w = upper_bound
                    optimal_labeling = best_labeling
                    break

            else:
                # TIMEOUT, MEMOUT, or ERROR
                status = step_res.status
                optimal_w = best_w
                optimal_labeling = best_labeling
                break

        total_time = time.perf_counter() - t_start
        return OptimizationResult(
            optimal_w=optimal_w,
            optimal_labeling=optimal_labeling,
            status=status,
            steps=steps,
            total_time=total_time,
            upper_bound=upper_bound,
        )
