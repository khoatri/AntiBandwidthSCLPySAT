from __future__ import annotations

import math
from typing import Callable, Dict, List, Tuple


class IntervalSummaryCache:
    """Manages allocation and reuse of interval summary auxiliary variables.

    H_v[a, b] <=> (A_{v, a} or ... or A_{v, b}).

    - Singletons: H_v[a, a] reuses primary variable id(A_{v, a}) without allocating
      a new auxiliary variable.
    - Caching: Caches variables by (v, a, b). In particular, full prefix
      H_v[L_j, R_j] and full suffix H_v[L_j, R_j] share the exact same variable.
    """

    def __init__(self, n: int, var_allocator: Callable[[], int]) -> None:
        self.n = n
        self.var_allocator = var_allocator
        self.cache: Dict[Tuple[int, int, int], int] = {}

    def get_summary(self, v: int, a: int, b: int) -> int:
        """Returns the SAT variable ID representing H_v[a, b]."""
        if a > b:
            raise ValueError(f"Invalid interval [{a}, {b}] with a > b")

        if a == b:
            # Singleton: reuse primary assignment variable directly
            return (v - 1) * self.n + a

        key = (v, a, b)
        if key in self.cache:
            return self.cache[key]

        new_var = self.var_allocator()
        self.cache[key] = new_var
        return new_var

    def size(self) -> int:
        """Returns the number of auxiliary interval summaries allocated."""
        return len(self.cache)


def encode_block_ladders(
    v: int, n: int, w: int, cache: IntervalSummaryCache
) -> List[List[int]]:
    """Encodes prefix and suffix ladder chains for vertex v across all blocks B_j.

    - First block (j = 0): Suffix equivalences and suffix AMO.
    - Interior blocks (0 < j < K - 1): Prefix equivalences and prefix AMO;
      suffix equivalences (no suffix AMO needed).
    - Final block (j = K - 1, K > 1): Prefix equivalences and prefix AMO
      (0 clauses if length d = 1).
    - Single block (K = 1): Suffix equivalences and suffix AMO.
    """
    K = math.ceil(n / w)
    clauses: List[List[int]] = []

    if K == 1:
        # Single block case: B_0 = [1, n], suffix equivalences + suffix AMO
        for i in range(1, n):
            a_i = (v - 1) * n + i
            s_i = cache.get_summary(v, i, n)
            s_next = cache.get_summary(v, i + 1, n)

            # S_i <=> (A_{v, i} or S_{i+1})
            clauses.append([-a_i, s_i])
            clauses.append([-s_next, s_i])
            clauses.append([a_i, s_next, -s_i])
            # Suffix AMO: not A_{v, i} or not S_{i+1}
            clauses.append([-a_i, -s_next])
        return clauses

    for j in range(K):
        l_j = j * w + 1
        r_j = min((j + 1) * w, n)

        if j == 0:
            # First block: Suffix equivalences + Suffix AMO
            for i in range(l_j, r_j):
                a_i = (v - 1) * n + i
                s_i = cache.get_summary(v, i, r_j)
                s_next = cache.get_summary(v, i + 1, r_j)

                clauses.append([-a_i, s_i])
                clauses.append([-s_next, s_i])
                clauses.append([a_i, s_next, -s_i])
                clauses.append([-a_i, -s_next])

        elif j < K - 1:
            # Interior block: Prefix equivalences + AMO; Suffix equivalences
            # 1. Prefix chain
            for i in range(l_j + 1, r_j + 1):
                a_i = (v - 1) * n + i
                p_prev = cache.get_summary(v, l_j, i - 1)
                p_i = cache.get_summary(v, l_j, i)

                clauses.append([-p_prev, p_i])
                clauses.append([-a_i, p_i])
                clauses.append([p_prev, a_i, -p_i])
                clauses.append([-a_i, -p_prev])

            # 2. Suffix chain (suffix AMO omitted as prefix AMO already ensures AMO)
            for i in range(l_j, r_j):
                a_i = (v - 1) * n + i
                s_i = cache.get_summary(v, i, r_j)
                s_next = cache.get_summary(v, i + 1, r_j)

                clauses.append([-a_i, s_i])
                clauses.append([-s_next, s_i])
                clauses.append([a_i, s_next, -s_i])

        else:
            # Final block (j = K - 1): Prefix equivalences + Prefix AMO
            # If length d = r_j - l_j + 1 == 1, loop range is empty (0 clauses)
            for i in range(l_j + 1, r_j + 1):
                a_i = (v - 1) * n + i
                p_prev = cache.get_summary(v, l_j, i - 1)
                p_i = cache.get_summary(v, l_j, i)

                clauses.append([-p_prev, p_i])
                clauses.append([-a_i, p_i])
                clauses.append([p_prev, a_i, -p_i])
                clauses.append([-a_i, -p_prev])

    return clauses


def encode_block_occupancy(
    v: int, n: int, w: int, cache: IntervalSummaryCache
) -> List[List[int]]:
    """Encodes that vertex v occupies exactly one block across all B_j:

    1. Block ALO: F_{v, 0} or ... or F_{v, K-1}
    2. Block Pairwise AMO: not F_{v, j} or not F_{v, k} for all 0 <= j < k < K
    """
    K = math.ceil(n / w)
    full_blocks = [
        cache.get_summary(v, j * w + 1, min((j + 1) * w, n)) for j in range(K)
    ]

    clauses: List[List[int]] = []

    # Block ALO (unit clause when K = 1)
    clauses.append(full_blocks)

    # Block Pairwise AMO
    for j in range(K):
        for k in range(j + 1, K):
            clauses.append([-full_blocks[j], -full_blocks[k]])

    return clauses


def encode_adjacent_block_glue(
    v: int, n: int, w: int, cache: IntervalSummaryCache
) -> List[List[int]]:
    """Encodes redundant adjacent-block glue clauses for vertex v across block

    boundaries B_j and B_{j+1}.
    """
    K = math.ceil(n / w)
    if K < 2:
        return []

    clauses: List[List[int]] = []

    for j in range(K - 1):
        l_j = j * w + 1
        r_j = (j + 1) * w
        l_next = (j + 1) * w + 1
        r_next = min((j + 2) * w, n)
        d_next = r_next - l_next + 1
        limit = min(w - 1, d_next)

        for i in range(1, limit + 1):
            left_summary = cache.get_summary(v, l_j + i, r_j)
            right_summary = cache.get_summary(v, l_next, l_next + i - 1)
            clauses.append([-left_summary, -right_summary])

    return clauses
