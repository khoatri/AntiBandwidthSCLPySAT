from __future__ import annotations

from typing import Tuple

from src.utils.graph import Graph


def verify_solution(
    graph: Graph, labeling: dict[int, int], w: int
) -> Tuple[bool, str]:
    """Rigorously verifies whether a candidate labeling phi: V -> Q satisfies:

    1. Domain completeness: Every vertex in V = {1, ..., n} is assigned a label.
    2. Bijectivity: Labels form a permutation of Q = {1, ..., n}.
    3. Minimum edge distance: For every edge {u, v} in E, |phi(u) - phi(v)| >= w.

    Returns:
        (True, "OK") if all conditions hold, otherwise (False, reason).
    """
    expected_vertices = set(range(1, graph.n + 1))
    actual_vertices = set(labeling.keys())

    missing = expected_vertices - actual_vertices
    if missing:
        return (
            False,
            f"Missing labels for vertices: {sorted(missing)[:10]}"
            f"{'...' if len(missing) > 10 else ''}",
        )

    extra = actual_vertices - expected_vertices
    if extra:
        return (
            False,
            f"Unexpected vertex keys outside range [1, {graph.n}]: {sorted(extra)[:10]}"
            f"{'...' if len(extra) > 10 else ''}",
        )

    # Check labels in [1, n]
    invalid_labels = {
        v: lbl for v, lbl in labeling.items() if not (1 <= lbl <= graph.n)
    }
    if invalid_labels:
        items = list(invalid_labels.items())[:5]
        return (
            False,
            f"Labels out of range [1, {graph.n}]: {items}"
            f"{'...' if len(invalid_labels) > 5 else ''}",
        )

    # Check bijectivity
    label_counts: dict[int, list[int]] = {}
    for v, lbl in labeling.items():
        label_counts.setdefault(lbl, []).append(v)

    duplicates = {lbl: vs for lbl, vs in label_counts.items() if len(vs) > 1}
    if duplicates:
        dup_items = list(duplicates.items())[:5]
        return False, f"Duplicate label assignments detected: {dup_items}"

    # Check edge distances
    for u, v in graph.edges:
        dist = abs(labeling[u] - labeling[v])
        if dist < w:
            return (
                False,
                f"Edge ({u}, {v}) violates distance requirement: "
                f"|phi({u})={labeling[u]} - phi({v})={labeling[v]}| = {dist} < {w}",
            )

    return True, "OK"


def compute_actual_bandwidth(graph: Graph, labeling: dict[int, int]) -> int:
    """Computes the actual minimum edge distance under labeling phi.

    beta(phi) = min_{(u, v) in E} |phi(u) - phi(v)|
    """
    if not graph.edges:
        return graph.n - 1
    return min(abs(labeling[u] - labeling[v]) for u, v in graph.edges)
