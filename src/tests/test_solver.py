from dataclasses import FrozenInstanceError
from typing import Any
import os
import sys
import pytest

from src.solvers.solver import ABPSolver, SolveResult
import src.solvers.solver as solver_module
from src.utils.graph import Graph
from src.utils.graph_parser import parse_instance
from src.utils.solution_verifier import verify_solution


# =========================================================================
# Integration Tests with Kissat Solver Backend
# =========================================================================

def test_solver_p4_sat_and_unsat() -> None:
    # Path P4: 1 - 2 - 3 - 4. Known optimal bandwidth AB(P4) = 2.
    g = Graph(n=4, edges=((1, 2), (2, 3), (3, 4)))
    solver = ABPSolver()

    # w = 2 is SAT
    res_sat = solver.solve(g, w=2)
    assert isinstance(res_sat, SolveResult)
    assert res_sat.status == "SAT"
    assert res_sat.w == 2
    assert res_sat.labeling is not None
    assert len(res_sat.labeling) == 4
    assert set(res_sat.labeling.keys()) == {1, 2, 3, 4}
    assert set(res_sat.labeling.values()) == {1, 2, 3, 4}
    assert res_sat.solve_time >= 0.0
    assert res_sat.encoding_time >= 0.0
    assert res_sat.total_time >= res_sat.solve_time
    assert res_sat.stats.get("verified") is True
    assert res_sat.stats.get("n") == 4
    assert res_sat.stats.get("m") == 3
    assert res_sat.stats.get("w") == 2
    assert res_sat.stats.get("sym_mode") == "n"
    assert "n_vars" in res_sat.stats
    assert "n_clauses" in res_sat.stats

    # Verify certificate correctness
    is_valid, err_msg = verify_solution(g, res_sat.labeling, 2)
    assert is_valid, err_msg

    # w = 3 is UNSAT (upper bound floor(4 / 2) = 2)
    res_unsat = solver.solve(g, w=3)
    assert res_unsat.status == "UNSAT"
    assert res_unsat.w == 3
    assert res_unsat.labeling is None


def test_solver_c4_unsat() -> None:
    # Cycle C4 has 4 edges, but in n=4 there are only 3 pairs with distance >= 2.
    # By pigeonhole principle, AB(C4) = 1, so w = 2 is UNSAT.
    g = Graph(n=4, edges=((1, 2), (2, 3), (3, 4), (1, 4)))
    solver = ABPSolver()

    res_unsat = solver.solve(g, w=2)
    assert res_unsat.status == "UNSAT"
    assert res_unsat.labeling is None


def test_solver_c6_sat_and_unsat() -> None:
    # Cycle C6 has AB(C6) = 2.
    # For n = 6, w = 2 is SAT (e.g. 1-3-5-2-6-4-1), w = 3 is UNSAT.
    edges = ((1, 2), (2, 3), (3, 4), (4, 5), (5, 6), (1, 6))
    g = Graph(n=6, edges=edges)
    solver = ABPSolver()

    res_sat = solver.solve(g, w=2)
    assert res_sat.status == "SAT"
    assert res_sat.labeling is not None
    assert res_sat.stats.get("verified") is True

    is_valid, err_msg = verify_solution(g, res_sat.labeling, 2)
    assert is_valid, err_msg

    res_unsat = solver.solve(g, w=3)
    assert res_unsat.status == "UNSAT"
    assert res_unsat.labeling is None


def test_solver_k4_unsat() -> None:
    # Complete graph K4: AB(Kn) = 1 for n >= 2
    edges = ((1, 2), (1, 3), (1, 4), (2, 3), (2, 4), (3, 4))
    g = Graph(n=4, edges=edges)
    solver = ABPSolver()

    res = solver.solve(g, w=2)
    assert res.status == "UNSAT"
    assert res.labeling is None


def test_solver_p5_symmetry_modes() -> None:
    # Path P5: 1 - 2 - 3 - 4 - 5. Known AB(P5) = 2.
    g = Graph(n=5, edges=((1, 2), (2, 3), (3, 4), (4, 5)))
    solver = ABPSolver()

    for sym in ("n", "f", "h", "l"):
        res = solver.solve(g, w=2, sym_mode=sym)
        assert res.status == "SAT"
        assert res.labeling is not None
        assert res.stats.get("sym_mode") == sym
        assert res.stats.get("verified") is True

        is_valid, err_msg = verify_solution(g, res.labeling, 2)
        assert is_valid, err_msg


def test_solver_timeout_handling() -> None:
    # Use real benchmark instance with a tiny timeout
    g = parse_instance("instances/A-pores_1.mtx.rnd")
    solver = ABPSolver()

    res = solver.solve(g, w=10, timeout=0.005)
    assert res.status == "TIMEOUT"
    assert res.labeling is None
    assert res.solve_time > 0.0


def test_solver_memout_handling() -> None:
    # 0.01 GB = 10 MB limit, which forces Kissat to run out of memory on pores_1
    g = parse_instance("instances/A-pores_1.mtx.rnd")
    solver = ABPSolver()

    res = solver.solve(g, w=5, mem_limit=0.01)
    assert res.status == "MEMOUT"
    assert res.labeling is None


def test_solver_isolated_sat_and_unsat() -> None:
    # Explicitly test that _solve_isolated returns SAT and UNSAT when limits are set
    g = Graph(n=4, edges=((1, 2), (2, 3), (3, 4)))
    solver = ABPSolver()

    # Pass generous timeout and memory limits to trigger _solve_isolated execution
    res_sat = solver.solve(g, w=2, timeout=10.0, mem_limit=30.0)
    assert res_sat.status == "SAT"
    assert res_sat.labeling is not None
    assert res_sat.stats.get("verified") is True

    res_unsat = solver.solve(g, w=3, timeout=10.0, mem_limit=30.0)
    assert res_unsat.status == "UNSAT"
    assert res_unsat.labeling is None


# =========================================================================
# Unit Tests for Error Handling, Isolation, and Decoding
# =========================================================================

def test_solver_verification_failure_direct(monkeypatch: pytest.MonkeyPatch) -> None:
    # Test direct solve where verify_solution returns invalid labeling
    g = Graph(n=4, edges=((1, 2), (2, 3), (3, 4)))
    solver = ABPSolver()

    monkeypatch.setattr(
        solver_module,
        "verify_solution",
        lambda graph, labeling, w: (False, "Simulated distance violation"),
    )

    res = solver.solve(g, w=2)
    assert res.status == "ERROR"
    assert res.labeling is not None
    assert res.stats.get("verification_error") == "Simulated distance violation"


def test_solver_verification_failure_isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    # Test isolated solve where verify_solution returns invalid labeling
    g = Graph(n=4, edges=((1, 2), (2, 3), (3, 4)))
    solver = ABPSolver()

    monkeypatch.setattr(
        solver_module,
        "verify_solution",
        lambda graph, labeling, w: (False, "Simulated isolated verification failure"),
    )

    res = solver.solve(g, w=2, timeout=10.0)
    assert res.status == "ERROR"
    assert res.labeling is not None
    assert res.stats.get("verification_error") == "Simulated isolated verification failure"


def test_solver_worker_exception_handling(monkeypatch: pytest.MonkeyPatch) -> None:
    # Test worker exception caught in try...except Exception as e in _solver_worker
    import pysat.solvers

    g = Graph(n=4, edges=((1, 2), (2, 3), (3, 4)))
    solver = ABPSolver()

    def crash_solve(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("Simulated internal solver crash")

    monkeypatch.setattr(pysat.solvers.Solver, "solve", crash_solve)

    res = solver.solve(g, w=2, timeout=5.0)
    assert res.status == "ERROR"
    assert res.labeling is None


def test_solver_worker_memory_error_handling(monkeypatch: pytest.MonkeyPatch) -> None:
    # Test Python MemoryError caught in try...except MemoryError in _solver_worker
    import pysat.solvers

    g = Graph(n=4, edges=((1, 2), (2, 3), (3, 4)))
    solver = ABPSolver()

    def memerror_solve(*args: Any, **kwargs: Any) -> None:
        raise MemoryError("Simulated Python MemoryError")

    monkeypatch.setattr(pysat.solvers.Solver, "solve", memerror_solve)

    res = solver.solve(g, w=2, timeout=5.0)
    assert res.status == "MEMOUT"
    assert res.labeling is None


def test_solver_non_oom_crash_handling(monkeypatch: pytest.MonkeyPatch) -> None:
    # Test when child process aborts abruptly without writing 'out-of-memory' to stderr
    g = Graph(n=4, edges=((1, 2), (2, 3), (3, 4)))
    solver = ABPSolver()

    def abort_worker(*args: Any, **kwargs: Any) -> None:
        os._exit(1)

    monkeypatch.setattr(solver_module, "_solver_worker", abort_worker)

    res = solver.solve(g, w=2, timeout=5.0, mem_limit=30.0)
    assert res.status == "ERROR"
    assert res.labeling is None


def test_solver_sigkill_oom_handling(monkeypatch: pytest.MonkeyPatch) -> None:
    # Test when child process is terminated by SIGKILL (exitcode -9) under memory limit
    import signal
    g = Graph(n=4, edges=((1, 2), (2, 3), (3, 4)))
    solver = ABPSolver()

    def sigkill_worker(*args: Any, **kwargs: Any) -> None:
        os.kill(os.getpid(), signal.SIGKILL)

    monkeypatch.setattr(solver_module, "_solver_worker", sigkill_worker)

    res = solver.solve(g, w=2, timeout=5.0, mem_limit=30.0)
    assert res.status == "MEMOUT"
    assert res.labeling is None


def test_solver_sentinel_ready_branch_oom(monkeypatch: pytest.MonkeyPatch) -> None:
    # Test branch where p.sentinel is ready but parent_conn is filtered out, with OOM in stderr
    g = Graph(n=4, edges=((1, 2), (2, 3), (3, 4)))
    solver = ABPSolver()

    def mock_worker_oom(clauses: Any, mem_limit: Any, conn: Any, err_write_fd: Any = None) -> None:
        if err_write_fd is not None:
            os.dup2(err_write_fd, 2)
            os.close(err_write_fd)
        os.write(2, b"kissat: fatal error: out-of-memory allocating memory\n")
        os._exit(1)

    monkeypatch.setattr(solver_module, "_solver_worker", mock_worker_oom)

    import multiprocessing.connection as mpc
    real_wait = mpc.wait

    def mock_wait(object_list: list[Any], timeout: Any = None) -> list[Any]:
        ready = real_wait(object_list, timeout=timeout)
        # Exclude parent_conn, leaving only p.sentinel in ready
        return [obj for obj in ready if not hasattr(obj, "recv")]

    monkeypatch.setattr(solver_module, "wait", mock_wait)

    res = solver.solve(g, w=2, timeout=5.0)
    assert res.status == "MEMOUT"
    assert res.labeling is None


def test_solver_sentinel_ready_branch_error(monkeypatch: pytest.MonkeyPatch) -> None:
    # Test branch where p.sentinel is ready but parent_conn is filtered out, without OOM
    g = Graph(n=4, edges=((1, 2), (2, 3), (3, 4)))
    solver = ABPSolver()

    def mock_worker_error(clauses: Any, mem_limit: Any, conn: Any, err_write_fd: Any = None) -> None:
        os._exit(1)

    monkeypatch.setattr(solver_module, "_solver_worker", mock_worker_error)

    import multiprocessing.connection as mpc
    real_wait = mpc.wait

    def mock_wait(object_list: list[Any], timeout: Any = None) -> list[Any]:
        ready = real_wait(object_list, timeout=timeout)
        return [obj for obj in ready if not hasattr(obj, "recv")]

    monkeypatch.setattr(solver_module, "wait", mock_wait)

    res = solver.solve(g, w=2, timeout=5.0)
    assert res.status == "ERROR"
    assert res.labeling is None


def test_solver_read_crash_stderr_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    # Test exception handling in read_crash_stderr (os.read raises OSError)
    g = Graph(n=4, edges=((1, 2), (2, 3), (3, 4)))
    solver = ABPSolver()

    def mock_worker(*args: Any, **kwargs: Any) -> None:
        os._exit(1)

    monkeypatch.setattr(solver_module, "_solver_worker", mock_worker)

    def mock_os_read(fd: int, n: int) -> bytes:
        raise OSError("Simulated read failure")

    monkeypatch.setattr(solver_module.os, "read", mock_os_read)

    res = solver.solve(g, w=2, timeout=5.0)
    assert res.status == "ERROR"
    assert res.labeling is None


def test_solver_decode_labeling_comprehensive() -> None:
    # Directly test _decode_labeling with:
    # - valid positive literals 1 <= lit <= n^2
    # - auxiliary positive literals > n^2
    # - negative literals
    solver = ABPSolver()
    n = 3  # n^2 = 9
    # Encoding: lit = (v - 1) * n + ell.
    # Suppose:
    # v=1, ell=2 -> idx = 0*3 + 1 = 1 -> lit = 2
    # v=2, ell=3 -> idx = 1*3 + 2 = 5 -> lit = 6
    # v=3, ell=1 -> idx = 2*3 + 0 = 6 -> lit = 7
    # Plus negative literals and auxiliary variables > 9
    model = [-1, 2, -3, -4, -5, 6, 7, -8, -9, 10, 11, 25, -15]
    labeling = solver._decode_labeling(model, n=3)

    assert len(labeling) == 3
    assert labeling[1] == 2
    assert labeling[2] == 3
    assert labeling[3] == 1


def test_solver_unknown_symmetry_mode_raises() -> None:
    g = Graph(n=4, edges=((1, 2), (2, 3), (3, 4)))
    solver = ABPSolver()

    with pytest.raises(ValueError, match="Unknown symmetry breaking mode"):
        solver.solve(g, w=2, sym_mode="invalid_mode")


def test_solver_result_immutability() -> None:
    res = SolveResult(
        status="SAT",
        w=2,
        labeling={1: 1, 2: 2},
        solve_time=0.1,
        encoding_time=0.05,
        total_time=0.15,
    )
    with pytest.raises(FrozenInstanceError):
        res.status = "UNSAT"  # type: ignore[misc]


def test_solver_deducts_encoding_time_from_isolated_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    g = Graph(n=4, edges=((1, 2), (2, 3), (3, 4)))
    solver = ABPSolver()

    captured_kwargs: dict[str, Any] = {}

    def mock_solve_isolated(*args: Any, **kwargs: Any) -> tuple[str, Optional[list[int]], float]:
        captured_kwargs.update(kwargs)
        # Model for n=4, w=2 valid labeling: {1: 2, 2: 4, 3: 1, 4: 3} -> positive vars: 2, 8, 9, 15
        pos = {2, 8, 9, 15}
        model = [i if i in pos else -i for i in range(1, 17)]
        return ("SAT", model, 0.01)

    monkeypatch.setattr(solver, "_solve_isolated", mock_solve_isolated)

    res = solver.solve(g, w=2, timeout=5.0)
    assert res.status == "SAT"
    assert "timeout" in captured_kwargs
    passed_timeout = captured_kwargs["timeout"]
    assert passed_timeout is not None
    assert passed_timeout < 5.0
    assert abs(passed_timeout - (5.0 - res.encoding_time)) < 0.05

