from src.encoding.ladder import IntervalSummaryCache
from src.encoding.sliding_window import encode_edge_sliding_window_exclusions


def test_sliding_window_clause_counts_and_structure() -> None:
    # For n = 6, w = 3:
    # Windows: [1, 2, 3] (aligned, mod 0), [2, 3, 4] (crossing, mod 1),
    #          [3, 4, 5] (crossing, mod 2), [4, 5, 6] (aligned, mod 0)
    # Total windows: 6 - 3 + 1 = 4.
    # Aligned windows: floor(6 / 3) = 2.
    # Crossing windows: 4 - 2 = 2.
    # Expected clauses per edge: e = 1 * 2 + 4 * 2 = 10.
    n = 6
    w = 3
    var_id = 100

    def alloc() -> int:
        nonlocal var_id
        var_id += 1
        return var_id

    cache = IntervalSummaryCache(n=n, var_allocator=alloc)

    # Single edge (1, 2)
    single_edge = ((1, 2),)
    clauses = encode_edge_sliding_window_exclusions(single_edge, n=n, w=w, cache=cache)

    assert len(clauses) == 10
    # First clause must be binary (aligned window 1: not F_{1, 0} or not F_{2, 0})
    assert len(clauses[0]) == 2
    # Next 4 clauses must be crossing window clauses (each length 2)
    for c in clauses:
        assert len(c) == 2
        # All literals in exclusions must be negative
        assert c[0] < 0 and c[1] < 0


def test_sliding_window_multiple_edges() -> None:
    # Triangle graph: 3 vertices, 3 edges, w = 2
    # n = 3, w = 2:
    # Windows: [1, 2] (aligned), [2, 3] (crossing)
    # e = 4*(3 - 2 + 1) - 3*floor(3/2) = 8 - 3 = 5 clauses per edge.
    # For 3 edges => 15 clauses.
    n = 3
    w = 2
    var_id = 100

    def alloc() -> int:
        nonlocal var_id
        var_id += 1
        return var_id

    cache = IntervalSummaryCache(n=n, var_allocator=alloc)
    edges = ((1, 2), (2, 3), (1, 3))
    clauses = encode_edge_sliding_window_exclusions(edges, n=n, w=w, cache=cache)

    assert len(clauses) == 3 * 5


def test_sliding_window_single_block_case() -> None:
    # w = n: single window [1, n], perfectly aligned
    # e = 4*(1) - 3*(1) = 1 clause per edge: not F_{u, 0} or not F_{v, 0}
    n = 5
    w = 5
    var_id = 100

    def alloc() -> int:
        nonlocal var_id
        var_id += 1
        return var_id

    cache = IntervalSummaryCache(n=n, var_allocator=alloc)
    edges = ((1, 2), (3, 4))
    clauses = encode_edge_sliding_window_exclusions(edges, n=n, w=w, cache=cache)

    assert len(clauses) == 2 * 1
    for c in clauses:
        assert len(c) == 2
        assert c[0] < 0 and c[1] < 0
