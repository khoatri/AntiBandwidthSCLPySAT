from __future__ import annotations

from typing import List, Tuple

from src.encoding.ladder import IntervalSummaryCache


def encode_edge_sliding_window_exclusions(
    edges: Tuple[Tuple[int, int], ...],
    n: int,
    w: int,
    cache: IntervalSummaryCache,
) -> List[List[int]]:
    """Encodes sliding-window exclusion constraints for all edges {u, v} in E.

    For each window of width w, I_h = [h, h + w - 1] (1 <= h <= n - w + 1):
    - Aligned windows (mod == 0): 1 clause: not F_{u, j} or not F_{v, j}.
    - Crossing windows (mod != 0): 4 clauses across endpoint split summaries:
        (not U_1 or not V_1), (not U_1 or not V_2),
        (not U_2 or not V_1), (not U_2 or not V_2).
    """
    clauses: List[List[int]] = []
    number_steps = n - w + 1

    for u, v in edges:
        for i in range(number_steps):
            mod = i % w
            subset = i // w

            if mod == 0:
                # Aligned window: matches full block B_{subset}
                l_j = subset * w + 1
                r_j = (subset + 1) * w
                f_u = cache.get_summary(u, l_j, r_j)
                f_v = cache.get_summary(v, l_j, r_j)
                clauses.append([-f_u, -f_v])
            else:
                # Crossing window: splits into D_1 = [h, R_j] and D_2 = [L_{j+1}, h + w - 1]
                h = i + 1
                r_j = (subset + 1) * w
                l_next = (subset + 1) * w + 1
                end_w = h + w - 1

                u1 = cache.get_summary(u, h, r_j)
                u2 = cache.get_summary(u, l_next, end_w)
                v1 = cache.get_summary(v, h, r_j)
                v2 = cache.get_summary(v, l_next, end_w)

                clauses.append([-u1, -v1])
                clauses.append([-u1, -v2])
                clauses.append([-u2, -v1])
                clauses.append([-u2, -v2])

    return clauses
