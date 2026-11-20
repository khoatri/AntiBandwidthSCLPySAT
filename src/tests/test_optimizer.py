from typing import Any, Optional
from dataclasses import FrozenInstanceError
import pytest
import time

from src.solvers.optimizer import ABPOptimizer, OptimizationResult
from src.solvers.solver import ABPSolver, SolveResult
from src.utils.graph import Graph
from src.utils.graph_parser import parse_instance
from src.utils.solution_verifier import verify_solution


class MockSolver(ABPSolver):
    """Deterministic mock solver for testing optimizer state transitions and edge cases."""

    def __init__(self, responses: list[SolveResult]) -> None:
        super().__init__()
        self.responses = list(responses)
        self.call_history: list[dict[str, Any]] = []

    def solve(
        self,
        graph: Graph,
        w: int,
        sym_mode: str = "n",
        timeout: Optional[float] = None,
        mem_limit: Optional[float] = None,
    ) -> SolveResult:
        self.call_history.append({
            "graph": graph,
            "w": w,
            "sym_mode": sym_mode,
            "timeout": timeout,
            "mem_limit": mem_limit,
        })
        if not self.responses:
            raise IndexError("MockSolver ran out of predefined responses")
        return self.responses.pop(0)


def _make_result(
    status: str,
    w: int,
    labeling: Optional[dict[int, int]] = None,
    total_time: float = 0.05,
) -> SolveResult:
    return SolveResult(
        status=status,
        w=w,
        labeling=labeling,
        solve_time=total_time * 0.8,
        encoding_time=total_time * 0.2,
        total_time=total_time,
        stats={"n": 4, "w": w},
    )


# =========================================================================
# Integration Tests with Kissat Solver Backend
# =========================================================================

def test_optimizer_p4() -> None:
    # Path P4: U = floor(4 / 2) = 2. Known AB(P4) = 2.
    g = Graph(n=4, edges=((1, 2), (2, 3), (3, 4)))
    optimizer = ABPOptimizer()

    res = optimizer.linear_search(g, start_w=2)
    assert isinstance(res, OptimizationResult)
    assert res.status == "OPTIMAL"
    assert res.optimal_w == 2
    assert res.optimal_labeling is not None
    assert len(res.steps) == 1
    assert res.total_time > 0.0
    assert res.upper_bound == 2

    # Verify certificate correctness
    is_valid, err_msg = verify_solution(g, res.optimal_labeling, res.optimal_w)
    assert is_valid, err_msg


def test_optimizer_c6() -> None:
    # Cycle C6: U = floor(6 / 2) = 3. AB(C6) = 2.
    # Evaluates w=2 (SAT), w=3 (UNSAT).
    edges = ((1, 2), (2, 3), (3, 4), (4, 5), (5, 6), (1, 6))
    g = Graph(n=6, edges=edges)
    optimizer = ABPOptimizer()

    res = optimizer.linear_search(g, start_w=2)
    assert res.status == "OPTIMAL"
    assert res.optimal_w == 2
    assert res.optimal_labeling is not None
    assert len(res.steps) == 2
    assert res.steps[0].w == 2 and res.steps[0].status == "SAT"
    assert res.steps[1].w == 3 and res.steps[1].status == "UNSAT"

    is_valid, err_msg = verify_solution(g, res.optimal_labeling, res.optimal_w)
    assert is_valid, err_msg


def test_optimizer_p6_upper_bound_early_exit() -> None:
    # Path P6: U = floor(6 / 2) = 3. Known AB(P6) = 3.
    # Evaluates w=2 (SAT), w=3 (SAT). Reaching U=3 proves optimality without extra steps.
    edges = ((1, 2), (2, 3), (3, 4), (4, 5), (5, 6))
    g = Graph(n=6, edges=edges)
    optimizer = ABPOptimizer()

    res = optimizer.linear_search(g, start_w=2)
    assert res.status == "OPTIMAL"
    assert res.optimal_w == 3
    assert res.optimal_labeling is not None
    assert len(res.steps) == 2

    is_valid, err_msg = verify_solution(g, res.optimal_labeling, res.optimal_w)
    assert is_valid, err_msg


def test_optimizer_unsat_start() -> None:
    # Complete graph K4: AB(K4) = 1. With start_w = 2, first step is UNSAT.
    edges = ((1, 2), (1, 3), (1, 4), (2, 3), (2, 4), (3, 4))
    g = Graph(n=4, edges=edges)
    optimizer = ABPOptimizer()

    res = optimizer.linear_search(g, start_w=2)
    assert res.status == "UNSAT_START"
    assert res.optimal_w is None
    assert res.optimal_labeling is None
    assert len(res.steps) == 1
    assert res.steps[0].status == "UNSAT"


def test_optimizer_start_w_exceeds_upper_bound() -> None:
    # When start_w > U, optimizer terminates immediately with UNSAT_START
    g = Graph(n=4, edges=((1, 2), (2, 3), (3, 4)))
    optimizer = ABPOptimizer()

    res = optimizer.linear_search(g, start_w=5)
    assert res.status == "UNSAT_START"
    assert res.optimal_w is None
    assert res.optimal_labeling is None
    assert len(res.steps) == 0
    assert res.total_time == 0.0


def test_optimizer_custom_start_w() -> None:
    # Path P6 has AB(P6) = 3. If started at start_w = 3, halts in 1 step.
    edges = ((1, 2), (2, 3), (3, 4), (4, 5), (5, 6))
    g = Graph(n=6, edges=edges)
    optimizer = ABPOptimizer()

    res = optimizer.linear_search(g, start_w=3)
    assert res.status == "OPTIMAL"
    assert res.optimal_w == 3
    assert len(res.steps) == 1
    assert res.steps[0].w == 3


def test_optimizer_symmetry_modes() -> None:
    # Test linear search with all symmetry modes
    g = Graph(n=5, edges=((1, 2), (2, 3), (3, 4), (4, 5)))
    optimizer = ABPOptimizer()

    for sym in ("n", "f", "h", "l"):
        res = optimizer.linear_search(g, start_w=2, sym_mode=sym)
        assert res.status == "OPTIMAL"
        assert res.optimal_w == 2
        assert res.optimal_labeling is not None


def test_optimizer_timeout_halt() -> None:
    # Small total timeout halts search and records TIMEOUT
    g = parse_instance("instances/A-pores_1.mtx.rnd")
    optimizer = ABPOptimizer()

    res = optimizer.linear_search(g, start_w=6, timeout=0.005)
    assert res.status == "TIMEOUT"
    assert len(res.steps) == 1
    assert res.steps[0].status == "TIMEOUT"


def test_optimizer_cumulative_timeout_budget() -> None:
    # Test that remaining timeout budget is deducted across successive steps
    g = parse_instance("instances/A-pores_1.mtx.rnd")
    optimizer = ABPOptimizer()

    res = optimizer.linear_search(g, start_w=6, timeout=0.05)
    assert res.status == "TIMEOUT"
    assert res.total_time <= 0.2


# =========================================================================
# Unit Tests with Mock Solver (Edge Cases, Failures, and Invariants)
# =========================================================================

def test_optimizer_step_error_on_first_step() -> None:
    # If the first step encounters an ERROR, optimizer halts with status ERROR
    g = Graph(n=4, edges=((1, 2), (2, 3), (3, 4)))
    mock_solver = MockSolver([
        _make_result("ERROR", w=2),
    ])
    optimizer = ABPOptimizer(solver=mock_solver)

    res = optimizer.linear_search(g, start_w=2)
    assert res.status == "ERROR"
    assert res.optimal_w is None
    assert res.optimal_labeling is None
    assert len(res.steps) == 1
    assert res.steps[0].status == "ERROR"


def test_optimizer_step_error_after_sat_step() -> None:
    # If a later step encounters an ERROR, optimizer halts with status ERROR
    # but preserves the best known certified solution
    g = Graph(n=6, edges=((1, 2), (2, 3), (3, 4), (4, 5), (5, 6)))  # U = 3
    sat_labeling = {1: 1, 2: 3, 3: 5, 4: 2, 5: 4, 6: 6}
    mock_solver = MockSolver([
        _make_result("SAT", w=2, labeling=sat_labeling),
        _make_result("ERROR", w=3),
    ])
    optimizer = ABPOptimizer(solver=mock_solver)

    res = optimizer.linear_search(g, start_w=2)
    assert res.status == "ERROR"
    assert res.optimal_w == 2
    assert res.optimal_labeling == sat_labeling
    assert len(res.steps) == 2


def test_optimizer_step_memout_on_first_step() -> None:
    # If first step hits MEMOUT, halts with status MEMOUT and no optimal_w
    g = Graph(n=4, edges=((1, 2), (2, 3), (3, 4)))
    mock_solver = MockSolver([
        _make_result("MEMOUT", w=2),
    ])
    optimizer = ABPOptimizer(solver=mock_solver)

    res = optimizer.linear_search(g, start_w=2)
    assert res.status == "MEMOUT"
    assert res.optimal_w is None
    assert res.optimal_labeling is None
    assert len(res.steps) == 1


def test_optimizer_step_memout_after_sat_step() -> None:
    # If a subsequent step hits MEMOUT, status is MEMOUT, retaining best certified w
    g = Graph(n=6, edges=((1, 2), (2, 3), (3, 4), (4, 5), (5, 6)))
    sat_labeling = {1: 1, 2: 3, 3: 5, 4: 2, 5: 4, 6: 6}
    mock_solver = MockSolver([
        _make_result("SAT", w=2, labeling=sat_labeling),
        _make_result("MEMOUT", w=3),
    ])
    optimizer = ABPOptimizer(solver=mock_solver)

    res = optimizer.linear_search(g, start_w=2)
    assert res.status == "MEMOUT"
    assert res.optimal_w == 2
    assert res.optimal_labeling == sat_labeling
    assert len(res.steps) == 2


def test_optimizer_timeout_after_sat_step() -> None:
    # If w=2 is SAT and w=3 times out, status is TIMEOUT, retaining w=2
    g = Graph(n=6, edges=((1, 2), (2, 3), (3, 4), (4, 5), (5, 6)))
    sat_labeling = {1: 1, 2: 3, 3: 5, 4: 2, 5: 4, 6: 6}
    mock_solver = MockSolver([
        _make_result("SAT", w=2, labeling=sat_labeling),
        _make_result("TIMEOUT", w=3),
    ])
    optimizer = ABPOptimizer(solver=mock_solver)

    res = optimizer.linear_search(g, start_w=2, timeout=10.0)
    assert res.status == "TIMEOUT"
    assert res.optimal_w == 2
    assert res.optimal_labeling == sat_labeling
    assert len(res.steps) == 2


def test_optimizer_remaining_timeout_exhausted_before_step(monkeypatch: pytest.MonkeyPatch) -> None:
    # Simulate time jumping past the total timeout before the second step is dispatched
    g = Graph(n=6, edges=((1, 2), (2, 3), (3, 4), (4, 5), (5, 6)))
    sat_labeling = {1: 1, 2: 3, 3: 5, 4: 2, 5: 4, 6: 6}
    mock_solver = MockSolver([
        _make_result("SAT", w=2, labeling=sat_labeling),
    ])
    optimizer = ABPOptimizer(solver=mock_solver)

    clock_times = [0.0, 1.0, 15.0]  # Start at 0, check w=2 at 1.0s, loop start w=3 at 15.0s
    def fake_perf_counter() -> float:
        if clock_times:
            return clock_times.pop(0)
        return 20.0

    import src.solvers.optimizer as opt_module
    monkeypatch.setattr(opt_module.time, "perf_counter", fake_perf_counter)

    res = optimizer.linear_search(g, start_w=2, timeout=10.0)
    assert res.status == "TIMEOUT"
    assert res.optimal_w == 2
    assert res.optimal_labeling == sat_labeling
    # Only 1 step was dispatched because remaining timeout was <= 0 before step 2
    assert len(res.steps) == 1


def test_optimizer_argument_forwarding() -> None:
    # Verify sym_mode, mem_limit, and timeout are forwarded to solver
    g = Graph(n=4, edges=((1, 2), (2, 3), (3, 4)))
    mock_solver = MockSolver([
        _make_result("SAT", w=2, labeling={1: 1, 2: 3, 3: 2, 4: 4}),
    ])
    optimizer = ABPOptimizer(solver=mock_solver)

    optimizer.linear_search(g, start_w=2, sym_mode="h", timeout=30.0, mem_limit=16.0)

    assert len(mock_solver.call_history) == 1
    call = mock_solver.call_history[0]
    assert call["w"] == 2
    assert call["sym_mode"] == "h"
    assert call["mem_limit"] == 16.0
    assert call["timeout"] is not None and call["timeout"] <= 30.0


def test_optimizer_result_immutability() -> None:
    # Ensure OptimizationResult cannot be mutated
    res = OptimizationResult(
        optimal_w=2,
        optimal_labeling={1: 1, 2: 2},
        status="OPTIMAL",
        steps=[],
        total_time=1.0,
        upper_bound=2,
    )
    with pytest.raises(FrozenInstanceError):
        res.optimal_w = 3  # type: ignore[misc]


def test_optimizer_defaults_to_graph_lower_bound() -> None:
    # Graph with recognized name should start at lower bound 6 and search up to upper bound 8
    g = Graph(n=30, edges=((1, 2), (2, 3)), name="A-pores_1.mtx.rnd")
    mock_solver = MockSolver([
        _make_result("SAT", w=6),
        _make_result("SAT", w=7),
        _make_result("SAT", w=8),
    ])
    optimizer = ABPOptimizer(solver=mock_solver)
    res = optimizer.linear_search(g)  # start_w omitted

    assert res.status == "OPTIMAL"
    assert res.optimal_w == 8
    assert res.upper_bound == 8
    assert [c["w"] for c in mock_solver.call_history] == [6, 7, 8]


def test_optimizer_proves_optimality_in_one_step_when_lb_equals_ub() -> None:
    # B-ibm32 has LB=9, UB=9. A single SAT call at w=9 proves optimality!
    g = Graph(n=32, edges=((1, 2), (2, 3)), name="B-ibm32.mtx.rnd")
    mock_solver = MockSolver([
        _make_result("SAT", w=9),
    ])
    optimizer = ABPOptimizer(solver=mock_solver)
    res = optimizer.linear_search(g)

    assert res.status == "OPTIMAL"
    assert res.optimal_w == 9
    assert res.upper_bound == 9
    assert len(mock_solver.call_history) == 1
    assert mock_solver.call_history[0]["w"] == 9


def test_optimizer_defaults_to_2_on_custom_graph() -> None:
    g = Graph(n=4, edges=((1, 2), (2, 3), (3, 4)), name="custom_p4")
    mock_solver = MockSolver([
        _make_result("SAT", w=2),
    ])
    optimizer = ABPOptimizer(solver=mock_solver)
    res = optimizer.linear_search(g)  # start_w omitted

    assert len(mock_solver.call_history) == 1
    assert mock_solver.call_history[0]["w"] == 2


def test_optimizer_explicit_start_w_overrides_lower_bound() -> None:
    g = Graph(n=30, edges=((1, 2), (2, 3)), name="A-pores_1.mtx.rnd")
    mock_solver = MockSolver([
        _make_result("SAT", w=4),
        _make_result("UNSAT", w=5),
    ])
    optimizer = ABPOptimizer(solver=mock_solver)
    res = optimizer.linear_search(g, start_w=4)

    assert res.optimal_w == 4
    assert mock_solver.call_history[0]["w"] == 4
    assert mock_solver.call_history[1]["w"] == 5


def test_optimizer_deducts_encoding_time_from_step_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    g = Graph(n=4, edges=((1, 2), (2, 3), (3, 4)))
    solver = ABPSolver()

    captured_timeouts: list[Optional[float]] = []
    original_solve = solver.solve

    def spy_solve(*args: Any, **kwargs: Any) -> SolveResult:
        captured_timeouts.append(kwargs.get("timeout"))
        return original_solve(*args, **kwargs)

    monkeypatch.setattr(solver, "solve", spy_solve)
    optimizer = ABPOptimizer(solver=solver)
    optimizer.linear_search(graph=g, start_w=2, timeout=10.0)
    assert len(captured_timeouts) >= 1
    assert captured_timeouts[0] is not None
    assert captured_timeouts[0] <= 10.0


