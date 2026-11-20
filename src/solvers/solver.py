import multiprocessing as mp
import os
import resource
import time
from dataclasses import dataclass, field
from multiprocessing.connection import wait
from typing import Any, Optional

from pysat.solvers import Solver

from src.encoding.scl_encoder import SCLEncoder
from src.utils.graph import Graph
from src.utils.solution_verifier import verify_solution


@dataclass(frozen=True)
class SolveResult:
    """Outcome of a single decision problem instance: Is AB(G) >= w?"""

    status: str  # "SAT" | "UNSAT" | "TIMEOUT" | "MEMOUT" | "ERROR"
    w: int
    labeling: Optional[dict[int, int]]
    solve_time: float
    encoding_time: float
    total_time: float
    stats: dict[str, Any] = field(default_factory=dict)


def _solver_worker(
    clauses: list[list[int]],
    mem_limit_gb: Optional[float],
    conn: Any,
    err_write_fd: Optional[int] = None,
) -> None:
    """Worker function executed inside an isolated child process."""
    try:
        import faulthandler
        faulthandler.disable()

        if err_write_fd is not None:
            # Redirect stderr into pipe to capture crash/fatal error messages
            os.dup2(err_write_fd, 2)
            os.close(err_write_fd)

        if mem_limit_gb is not None:
            # Convert GB to bytes
            mem_bytes = int(mem_limit_gb * 1024 * 1024 * 1024)
            resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))

        t0 = time.perf_counter()
        with Solver(name="kissat404", bootstrap_with=clauses) as solver:
            sat = solver.solve()
            model = solver.get_model() if sat else None
        solve_t = time.perf_counter() - t0
        conn.send(("SAT" if sat else "UNSAT", model, solve_t))
    except MemoryError:
        conn.send(("MEMOUT", None, 0.0))
    except Exception as e:
        conn.send(("ERROR", str(e), 0.0))


class ABPSolver:
    """Dedicated SAT solver interface for the Anti-Bandwidth Problem (ABP).

    Backend: Hardcoded strictly to kissat404 via python-sat.
    Process Isolation: Supports fork-based worker execution to enforce hard
    memory limits (RLIMIT_AS in GB) and timeouts, preventing memory leaks and crashes.
    """

    def __init__(self) -> None:
        self.solver_name: str = "kissat404"

    def _decode_labeling(
        self,
        model: list[int],
        n: int,
    ) -> dict[int, int]:
        """Decode vertex-label bijection phi(v) = ell from positive literals in [1, n^2]."""
        labeling: dict[int, int] = {}
        for lit in model:
            if 1 <= lit <= n * n:
                idx = lit - 1
                v = (idx // n) + 1
                ell = (idx % n) + 1
                labeling[v] = ell
        return labeling

    def _solve_direct(
        self,
        clauses: list[list[int]],
    ) -> tuple[str, Optional[list[int]], float]:
        """Run kissat404 directly in the current process."""
        t0 = time.perf_counter()
        with Solver(name=self.solver_name, bootstrap_with=clauses) as solver:
            sat = solver.solve()
            model = solver.get_model() if sat else None
        solve_t = time.perf_counter() - t0
        return ("SAT" if sat else "UNSAT", model, solve_t)

    def _solve_isolated(
        self,
        clauses: list[list[int]],
        timeout: Optional[float],
        mem_limit_gb: Optional[float],
    ) -> tuple[str, Optional[list[int]], float]:
        """Run kissat404 in an isolated child process with timeout and memory enforcement."""
        ctx = mp.get_context("fork")
        parent_conn, child_conn = ctx.Pipe(duplex=False)
        err_r, err_w = os.pipe()

        p = ctx.Process(
            target=_solver_worker,
            args=(clauses, mem_limit_gb, child_conn, err_w),
        )
        t0 = time.perf_counter()
        p.start()
        child_conn.close()
        os.close(err_w)  # Close write end in parent

        ready = wait([parent_conn, p.sentinel], timeout=timeout)
        dur = time.perf_counter() - t0

        def read_crash_stderr() -> str:
            try:
                msg = os.read(err_r, 4096).decode("utf-8", errors="ignore")
                return msg.strip()
            except Exception:
                return ""
            finally:
                os.close(err_r)

        if parent_conn in ready:
            try:
                status, model, solve_t = parent_conn.recv()
                p.join()
                os.close(err_r)
                if status == "ERROR":
                    return ("ERROR", None, solve_t)
                if status == "MEMOUT":
                    return ("MEMOUT", None, solve_t)
                return (status, model, solve_t)
            except EOFError:
                # Worker terminated before sending (e.g. killed by OS on OOM abort)
                p.join()
                err_msg = read_crash_stderr()
                if "out-of-memory" in err_msg or "MemoryError" in err_msg:
                    return ("MEMOUT", None, dur)
                return ("ERROR", None, dur)

        if not ready:
            # Timeout reached
            p.kill()
            p.join()
            os.close(err_r)
            return ("TIMEOUT", None, timeout if timeout is not None else dur)

        # p.sentinel became ready but parent_conn was not ready (worker died)
        p.join()
        err_msg = read_crash_stderr()
        if "out-of-memory" in err_msg or "MemoryError" in err_msg:
            return ("MEMOUT", None, dur)
        return ("ERROR", None, dur)

    def solve(
        self,
        graph: Graph,
        w: int,
        sym_mode: str = "n",
        timeout: Optional[float] = None,
        mem_limit: Optional[float] = None,
    ) -> SolveResult:
        """Solve decision problem: Is AB(graph) >= w?

        Args:
            graph: The input Graph instance.
            w: Target bandwidth threshold (2 <= w <= n).
            sym_mode: Symmetry breaking mode ('n', 'f', 'h', 'l').
            timeout: Maximum solve time in seconds.
            mem_limit: Maximum memory limit in GB.

        Returns:
            SolveResult containing status, labeling, timing, and stats.
        """
        # 1. Construct SCL encoding
        t_enc_start = time.perf_counter()
        encoder = SCLEncoder(graph=graph, w=w, sym_mode=sym_mode)
        enc_res = encoder.encode()
        encoding_time = time.perf_counter() - t_enc_start

        stats: dict[str, Any] = {
            "n": graph.n,
            "m": graph.m,
            "w": w,
            "sym_mode": sym_mode,
            "n_vars": enc_res.n_vars,
            "n_clauses": enc_res.n_clauses,
            "cache_size": enc_res.stats.get("cache_size", 0),
        }

        # 2. Execute SAT solver backend
        if timeout is not None or mem_limit is not None:
            status, model, solve_time = self._solve_isolated(
                clauses=enc_res.cnf.clauses,
                timeout=timeout,
                mem_limit_gb=mem_limit,
            )
        else:
            status, model, solve_time = self._solve_direct(
                clauses=enc_res.cnf.clauses,
            )

        total_time = encoding_time + solve_time

        # 3. Model extraction & runtime solution verification
        labeling: Optional[dict[int, int]] = None
        if status == "SAT" and model is not None:
            labeling = self._decode_labeling(model, graph.n)
            is_valid, err_msg = verify_solution(graph, labeling, w)
            if not is_valid:
                stats["verification_error"] = err_msg
                return SolveResult(
                    status="ERROR",
                    w=w,
                    labeling=labeling,
                    solve_time=solve_time,
                    encoding_time=encoding_time,
                    total_time=total_time,
                    stats=stats,
                )
            stats["verified"] = True

        return SolveResult(
            status=status,
            w=w,
            labeling=labeling,
            solve_time=solve_time,
            encoding_time=encoding_time,
            total_time=total_time,
            stats=stats,
        )
