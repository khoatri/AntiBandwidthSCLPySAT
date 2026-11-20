from __future__ import annotations

import math
from typing import List

from src.utils.graph import Graph


def encode_symmetry_breaking(graph: Graph, sym_mode: str) -> List[List[int]]:
    """Generates optional symmetry breaking unit clauses by restricting a

    selected vertex s to the lower half of the labels:

        not A_{s, ell}  for  ceil(n / 2) < ell <= n

    Adds floor(n / 2) unit clauses and 0 auxiliary variables.
    """
    s = graph.get_symmetry_vertex(sym_mode)
    if s is None:
        return []

    clauses: List[List[int]] = []
    lower_bound_label = math.ceil(graph.n / 2)

    for ell in range(lower_bound_label + 1, graph.n + 1):
        var_id = (s - 1) * graph.n + ell
        clauses.append([-var_id])

    return clauses
