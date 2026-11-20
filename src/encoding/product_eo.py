from __future__ import annotations

import math
from typing import Callable, List


def encode_amo_seq(
    inputs: List[int], var_allocator: Callable[[], int]
) -> List[List[int]]:
    """Encodes an At-Most-One (AMO) constraint over inputs y_1, ..., y_t using

    a forward sequential implication chain.

    - If t < 2: 0 clauses, 0 auxiliaries.
    - If t == 2: 1 clause (not y_1 or not y_2), 0 auxiliaries.
    - If t >= 3: 3t - 5 clauses, t - 2 auxiliaries.
    """
    t = len(inputs)
    if t < 2:
        return []

    if t == 2:
        return [[-inputs[0], -inputs[1]]]

    clauses: List[List[int]] = []
    s_prev = inputs[0]

    for idx in range(1, t - 1):
        curr = inputs[idx]
        next_s = var_allocator()
        clauses.append([-s_prev, -curr])
        clauses.append([-s_prev, next_s])
        clauses.append([-curr, next_s])
        s_prev = next_s

    clauses.append([-s_prev, -inputs[-1]])
    return clauses


def encode_product_eo(
    inputs: List[int], var_allocator: Callable[[], int]
) -> List[List[int]]:
    """Encodes an Exactly-One (EO) constraint using a 2-product grid with

    sequential AMO chains on selectors.

    - If n == 2: directly emits (x_0 or x_1) and (not x_0 or not x_1) with 0
    auxiliaries.
    - If n >= 3: dimensions p = ceil(sqrt(n)), q = ceil(n / p).
      Emits 2n cell mapping clauses, 1 ALO clause, and sequential AMO clauses
      on p row selectors and q column selectors.
      Total clauses: c = 2n + 3(p + q) - 9.
      Total auxiliaries: a = 2(p + q) - 4.
    """
    n = len(inputs)
    if n < 2:
        raise ValueError(f"Product EO requires at least 2 inputs, got {n}")

    if n == 2:
        return [
            [inputs[0], inputs[1]],
            [-inputs[0], -inputs[1]],
        ]

    p = math.ceil(math.sqrt(n))
    q = math.ceil(n / p)

    r_vars = [var_allocator() for _ in range(p)]
    c_vars = [var_allocator() for _ in range(q)]

    clauses: List[List[int]] = []

    # 1. Cell mappings (each input activates its row and column selector)
    for i in range(n):
        clauses.append([-inputs[i], r_vars[i % p]])
        clauses.append([-inputs[i], c_vars[i // p]])

    # 2. At-Least-One (ALO) clause
    clauses.append(list(inputs))

    # 3. At-Most-One (AMO) on selectors
    clauses.extend(encode_amo_seq(r_vars, var_allocator))
    clauses.extend(encode_amo_seq(c_vars, var_allocator))

    return clauses
