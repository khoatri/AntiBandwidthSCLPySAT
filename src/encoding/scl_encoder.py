from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Dict, List, Tuple

from pysat.formula import CNF

from src.encoding.ladder import (
    IntervalSummaryCache,
    encode_adjacent_block_glue,
    encode_block_ladders,
    encode_block_occupancy,
)
from src.encoding.product_eo import encode_product_eo
from src.encoding.sliding_window import encode_edge_sliding_window_exclusions
from src.encoding.symmetry import encode_symmetry_breaking
from src.utils.graph import Graph


@dataclass(frozen=True)
class EncodingResult:
    """Represents the outcome of the SCL encoding process."""

    cnf: CNF
    n_vars: int
    n_clauses: int
    stats: Dict[str, Any]


class SCLEncoder:
    """Encodes the Anti-Bandwidth Problem for a given graph G and threshold w

    into a Boolean CNF formula using the SCL (Sequential Counter for Ladder
    constraints) encoding.
    """

    def __init__(self, graph: Graph, w: int, sym_mode: str = "n") -> None:
        if w < 2 or w > graph.n:
            raise ValueError(
                f"Threshold w must satisfy 2 <= w <= n ({graph.n}), got w={w}"
            )

        self.graph = graph
        self.w = w
        self.sym_mode = sym_mode

    def expected_counts(self) -> Tuple[int, int]:
        """Calculates theoretical variable (N) and clause (C) counts according to

        Section 5 of docs/encoding.md.
        """
        n = self.graph.n
        m = self.graph.m
        w = self.w

        p = math.ceil(math.sqrt(n))
        q = math.ceil(n / p)
        K = math.ceil(n / w)
        d = n - (K - 1) * w

        # 1. Product Exactly-One per label
        if n == 2:
            a = 0
            c = 2
        else:
            a = 2 * (p + q) - 4
            c = 2 * n + 3 * (p + q) - 9

        # 2. Vertex Ladder per vertex
        if K == 1:
            alpha = n - 1
            lambda_ = 4 * (n - 1)
            gamma = 0
        else:
            alpha = (w - 1) + (K - 2) * (2 * w - 3) + (d - 1)
            lambda_ = (
                4 * (w - 1) + 7 * (K - 2) * (w - 1) + 4 * (d - 1)
            )
            gamma = (K - 2) * (w - 1) + min(w - 1, d)

        # 3. Edge clauses per edge
        e = 4 * (n - w + 1) - 3 * (n // w)

        # Totals
        block_occupancy_clauses = (K * (K - 1) // 2) + 1
        N = n * n + n * (a + alpha)
        C = n * (c + lambda_ + gamma + block_occupancy_clauses) + m * e

        if self.sym_mode != "n":
            C += n // 2

        return N, C

    def encode(self) -> EncodingResult:
        """Constructs the complete SCL CNF formula in generation order:

        1. Symmetry breaking unit clauses.
        2. Label constraints (2-Product Exactly-One per label).
        3. Vertex constraints (block ladders, adjacent glue, block ALO/AMO).
        4. Edge exclusions (sliding-window exclusions for aligned & crossing windows).
        """
        n = self.graph.n
        w = self.w

        next_var = n * n + 1

        def alloc_var() -> int:
            nonlocal next_var
            var = next_var
            next_var += 1
            return var

        cache = IntervalSummaryCache(n=n, var_allocator=alloc_var)
        cnf = CNF()
        all_clauses = cnf.clauses

        # 1. Optional Symmetry Breaking
        sym_clauses = encode_symmetry_breaking(self.graph, self.sym_mode)
        all_clauses.extend(sym_clauses)

        # 2. Label constraints: Product Exactly-One per label ell in {1, ..., n}
        # Variable for vertex v receiving label ell is id(A_{v, ell}) = (v - 1)*n + ell
        for ell in range(1, n + 1):
            label_inputs = [(v - 1) * n + ell for v in range(1, n + 1)]
            eo_clauses = encode_product_eo(label_inputs, alloc_var)
            all_clauses.extend(eo_clauses)

        # 3. Vertex constraints: ladders, adjacent glue, block ALO/AMO
        for v in range(1, n + 1):
            ladder_clauses = encode_block_ladders(v, n, w, cache)
            all_clauses.extend(ladder_clauses)

            glue_clauses = encode_adjacent_block_glue(v, n, w, cache)
            all_clauses.extend(glue_clauses)

            occupancy_clauses = encode_block_occupancy(v, n, w, cache)
            all_clauses.extend(occupancy_clauses)

        # 4. Edge constraints: sliding-window exclusions
        edge_clauses = encode_edge_sliding_window_exclusions(
            self.graph.edges, n, w, cache
        )
        all_clauses.extend(edge_clauses)

        actual_n_vars = next_var - 1
        actual_n_clauses = len(all_clauses)

        expected_N, expected_C = self.expected_counts()
        if actual_n_vars != expected_N:
            raise AssertionError(
                f"Variable count mismatch: generated {actual_n_vars}, expected {expected_N}"
            )
        if actual_n_clauses != expected_C:
            raise AssertionError(
                f"Clause count mismatch: generated {actual_n_clauses}, expected {expected_C}"
            )

        cnf.nv = actual_n_vars

        stats = {
            "n": n,
            "m": self.graph.m,
            "w": w,
            "sym_mode": self.sym_mode,
            "expected_N": expected_N,
            "expected_C": expected_C,
            "actual_N": actual_n_vars,
            "actual_C": actual_n_clauses,
            "cache_size": cache.size(),
        }

        return EncodingResult(
            cnf=cnf,
            n_vars=actual_n_vars,
            n_clauses=actual_n_clauses,
            stats=stats,
        )
