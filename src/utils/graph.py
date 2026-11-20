from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Graph:
    """Represents a simple undirected graph G = (V, E) with V = {1, ..., n}."""

    n: int
    edges: tuple[tuple[int, int], ...]
    name: str = ""
    best_known_w: Optional[int] = None
    adjacency: dict[int, set[int]] = None  # type: ignore[assignment]
    degrees: dict[int, int] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.n < 2:
            raise ValueError(f"Graph must have at least 2 vertices, got n={self.n}")

        # Deduplicate, normalize (u < v), and filter self-loops
        unique_edges: set[tuple[int, int]] = set()
        for edge in self.edges:
            if len(edge) != 2:
                raise ValueError(f"Each edge must be a pair (u, v), got {edge}")
            u, v = edge
            if not (1 <= u <= self.n and 1 <= v <= self.n):
                raise ValueError(
                    f"Edge ({u}, {v}) has vertices outside valid range [1, {self.n}]"
                )
            if u == v:
                continue  # Discard self-loop in simple graph
            norm_edge = (min(u, v), max(u, v))
            unique_edges.add(norm_edge)

        sorted_edges = tuple(sorted(unique_edges))
        object.__setattr__(self, "edges", sorted_edges)

        # Build adjacency and degrees
        adj: dict[int, set[int]] = {v: set() for v in range(1, self.n + 1)}
        degs: dict[int, int] = {v: 0 for v in range(1, self.n + 1)}
        for u, v in sorted_edges:
            adj[u].add(v)
            adj[v].add(u)
            degs[u] += 1
            degs[v] += 1

        object.__setattr__(self, "adjacency", adj)
        object.__setattr__(self, "degrees", degs)

    @property
    def m(self) -> int:
        """Number of undirected edges."""
        return len(self.edges)

    @property
    def min_degree(self) -> int:
        """Minimum vertex degree in G."""
        return min(self.degrees.values()) if self.degrees else 0

    @property
    def max_degree(self) -> int:
        """Maximum vertex degree in G."""
        return max(self.degrees.values()) if self.degrees else 0

    def has_isolated_vertices(self) -> bool:
        """True if there is at least one vertex with degree 0."""
        return self.min_degree == 0

    def get_upper_bound(self) -> int:
        """Upper search bound for antibandwidth w.

        If G has no isolated vertices, any labeling satisfies
        beta(phi) <= floor(n / 2), so floor(n / 2) + 1 is guaranteed UNSAT.
        If isolated vertices exist, the upper bound is n - 1.
        """
        if not self.has_isolated_vertices():
            return self.n // 2
        return self.n - 1

    def get_symmetry_vertex(self, mode: str) -> Optional[int]:
        """Returns the vertex index s for symmetry breaking mode.

        Modes:
            'n': None (no symmetry breaking)
            'f': First vertex (vertex 1)
            'h': Highest degree vertex (ties broken by lowest index)
            'l': Lowest degree vertex (ties broken by lowest index)
        """
        if mode == "n":
            return None
        if mode == "f":
            return 1
        if mode == "h":
            best_v = 1
            max_deg = -1
            for v in range(1, self.n + 1):
                deg = self.degrees[v]
                if deg > max_deg:
                    max_deg = deg
                    best_v = v
            return best_v
        if mode == "l":
            best_v = 1
            min_deg = float("inf")
            for v in range(1, self.n + 1):
                deg = self.degrees[v]
                if deg < min_deg:
                    min_deg = deg
                    best_v = v
            return best_v

        raise ValueError(
            f"Unknown symmetry breaking mode: {mode!r}. Expected 'n', 'f', 'h', or 'l'."
        )

    def __repr__(self) -> str:
        name_str = f"'{self.name}', " if self.name else ""
        return (
            f"Graph({name_str}n={self.n}, m={self.m}, "
            f"min_deg={self.min_degree}, max_deg={self.max_degree})"
        )
