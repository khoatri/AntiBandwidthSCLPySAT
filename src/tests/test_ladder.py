from pysat.solvers import Solver

from src.encoding.ladder import (
    IntervalSummaryCache,
    encode_adjacent_block_glue,
    encode_block_ladders,
    encode_block_occupancy,
)


def test_interval_summary_cache_properties() -> None:
    n = 6
    next_id = 100

    def alloc() -> int:
        nonlocal next_id
        val = next_id
        next_id += 1
        return val

    cache = IntervalSummaryCache(n=n, var_allocator=alloc)

    # 1. Singleton rule: H_v[a, a] must equal primary variable (v-1)*n + a
    assert cache.get_summary(v=1, a=2, b=2) == 2
    assert cache.get_summary(v=2, a=4, b=4) == (2 - 1) * 6 + 4
    # No auxiliary variables allocated for singletons
    assert cache.size() == 0

    # 2. Allocation and reuse
    id1 = cache.get_summary(v=1, a=1, b=3)
    assert id1 == 100
    assert cache.size() == 1

    # Calling with same key must return cached ID without allocating new variable
    id2 = cache.get_summary(v=1, a=1, b=3)
    assert id2 == 100
    assert cache.size() == 1

    # Full prefix and full suffix query the exact same key (v, L_j, R_j)
    # so they automatically share the same ID
    full_prefix = cache.get_summary(v=1, a=1, b=3)
    full_suffix = cache.get_summary(v=1, a=1, b=3)
    assert full_prefix == full_suffix


def test_ladder_clause_counts_k2() -> None:
    # n = 6, w = 3 => K = 2 blocks [1, 2, 3] and [4, 5, 6]
    n = 6
    w = 3
    var_id = 100

    def alloc() -> int:
        nonlocal var_id
        var_id += 1
        return var_id

    cache = IntervalSummaryCache(n=n, var_allocator=alloc)

    ladder_clauses = encode_block_ladders(v=1, n=n, w=w, cache=cache)
    # Expected lambda: 4*(w-1) + 4*(d-1) = 4*2 + 4*2 = 16
    assert len(ladder_clauses) == 16

    occupancy_clauses = encode_block_occupancy(v=1, n=n, w=w, cache=cache)
    # Expected: ALO (1) + AMO (C(2, 2) = 1) = 2
    assert len(occupancy_clauses) == 2

    glue_clauses = encode_adjacent_block_glue(v=1, n=n, w=w, cache=cache)
    # Expected gamma: (K-2)*(w-1) + min(w-1, d) = 0 + min(2, 3) = 2
    assert len(glue_clauses) == 2


def test_ladder_clause_counts_k1() -> None:
    # Single block case: n = 4, w = 4 => K = 1
    n = 4
    w = 4
    var_id = 100

    def alloc() -> int:
        nonlocal var_id
        var_id += 1
        return var_id

    cache = IntervalSummaryCache(n=n, var_allocator=alloc)

    ladder_clauses = encode_block_ladders(v=1, n=n, w=w, cache=cache)
    # Expected lambda: 4*(n-1) = 4*3 = 12
    assert len(ladder_clauses) == 12

    occupancy_clauses = encode_block_occupancy(v=1, n=n, w=w, cache=cache)
    # ALO only: 1 clause (unit clause)
    assert len(occupancy_clauses) == 1

    glue_clauses = encode_adjacent_block_glue(v=1, n=n, w=w, cache=cache)
    assert len(glue_clauses) == 0


def test_ladder_propagation_and_amo() -> None:
    # Test on n = 6, w = 3: Block 0 is [1, 2, 3], Block 1 is [4, 5, 6]
    n = 6
    w = 3
    var_id = 100

    def alloc() -> int:
        nonlocal var_id
        var_id += 1
        return var_id

    cache = IntervalSummaryCache(n=n, var_allocator=alloc)
    clauses = []
    clauses.extend(encode_block_ladders(v=1, n=n, w=w, cache=cache))
    clauses.extend(encode_block_occupancy(v=1, n=n, w=w, cache=cache))

    # Setting label 1 True and label 2 True in same block must be UNSAT (within-block AMO)
    with Solver(name="kissat404", bootstrap_with=clauses + [[1], [2]]) as solver:
        assert solver.solve() is False

    # Setting label 1 True and label 4 True (two different blocks) must be UNSAT (block AMO)
    with Solver(name="kissat404", bootstrap_with=clauses + [[1], [4]]) as solver:
        assert solver.solve() is False

    # Setting exactly one label True (e.g. label 2 True, others False) must be SAT
    unit_clauses = [[-1], [2], [-3], [-4], [-5], [-6]]
    with Solver(name="kissat404", bootstrap_with=clauses + unit_clauses) as solver:
        assert solver.solve() is True
