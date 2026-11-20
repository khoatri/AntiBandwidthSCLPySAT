from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


RAW_BENCHMARK_LOWER_BOUNDS: dict[str, int] = {
    "A-pores_1.mtx.rnd": 6,
    "B-ibm32.mtx.rnd": 9,
    "C-bcspwr01.mtx.rnd": 16,
    "D-bcsstk01.mtx.rnd": 8,
    "E-bcspwr02.mtx.rnd": 21,
    "F-curtis54.mtx.rnd": 12,
    "G-will57.mtx.rnd": 12,
    "H-impcol_b.mtx.rnd": 8,
    "I-ash85.mtx.rnd": 19,
    "J-nos4.mtx.rnd": 32,
    "K-dwt__234.mtx.rnd": 46,
    "L-bcspwr03.mtx.rnd": 39,
    "M-bcsstk06.mtx.rnd": 28,
    "N-bcsstk07.mtx.rnd": 28,
    "O-impcol_d.mtx.rnd": 91,
    "P-can__445.mtx.rnd": 78,
    "Q-494_bus.mtx.rnd": 219,
    "R-dwt__503.mtx.rnd": 46,
    "S-sherman4.mtx.rnd": 256,
    "T-dwt__592.mtx.rnd": 103,
    "U-662_bus.mtx.rnd": 219,
    "V-nos6.mtx.rnd": 326,
    "W-685_bus.mtx.rnd": 136,
    "X-can__715.mtx.rnd": 112,
}

RAW_BENCHMARK_UPPER_BOUNDS: dict[str, int] = {
    "A-pores_1.mtx.rnd": 8,
    "B-ibm32.mtx.rnd": 9,
    "C-bcspwr01.mtx.rnd": 17,
    "D-bcsstk01.mtx.rnd": 9,
    "E-bcspwr02.mtx.rnd": 22,
    "F-curtis54.mtx.rnd": 13,
    "G-will57.mtx.rnd": 14,
    "H-impcol_b.mtx.rnd": 8,
    "I-ash85.mtx.rnd": 27,
    "J-nos4.mtx.rnd": 40,
    "K-dwt__234.mtx.rnd": 58,
    "L-bcspwr03.mtx.rnd": 39,
    "M-bcsstk06.mtx.rnd": 72,
    "N-bcsstk07.mtx.rnd": 72,
    "O-impcol_d.mtx.rnd": 173,
    "P-can__445.mtx.rnd": 120,
    "Q-494_bus.mtx.rnd": 246,
    "R-dwt__503.mtx.rnd": 71,
    "S-sherman4.mtx.rnd": 272,
    "T-dwt__592.mtx.rnd": 150,
    "U-662_bus.mtx.rnd": 220,
    "V-nos6.mtx.rnd": 337,
    "W-685_bus.mtx.rnd": 136,
    "X-can__715.mtx.rnd": 142,
}


def _build_normalized_bound_map(raw_map: dict[str, int]) -> dict[str, int]:
    normalized: dict[str, int] = {}
    for raw_name, val in raw_map.items():
        normalized[raw_name] = val
        stripped = (
            raw_name[2:]
            if (len(raw_name) >= 2 and raw_name[0].isalpha() and raw_name[1] == "-")
            else raw_name
        )
        normalized[stripped] = val
        stem_raw = raw_name.replace(".mtx.rnd", "").replace(".rnd", "").replace(".mtx", "")
        stem_stripped = stripped.replace(".mtx.rnd", "").replace(".rnd", "").replace(".mtx", "")
        normalized[stem_raw] = val
        normalized[stem_stripped] = val
        normalized[f"{stem_raw}.mtx"] = val
        normalized[f"{stem_stripped}.mtx"] = val
    return normalized


BENCHMARK_LOWER_BOUNDS: dict[str, int] = _build_normalized_bound_map(RAW_BENCHMARK_LOWER_BOUNDS)
BENCHMARK_UPPER_BOUNDS: dict[str, int] = _build_normalized_bound_map(RAW_BENCHMARK_UPPER_BOUNDS)


@dataclass(frozen=True)
class Graph:
    """Represents a simple undirected graph G = (V, E) with V = {1, ..., n}."""

    n: int
    edges: tuple[tuple[int, int], ...]
    name: str = ""
    best_known_w: Optional[int] = None
    adjacency: dict[int, set[int]] = field(default=None, hash=False, compare=False, repr=False)  # type: ignore[assignment]
    degrees: dict[int, int] = field(default=None, hash=False, compare=False, repr=False)  # type: ignore[assignment]

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

    def get_lower_bound(self, fallback: int = 1) -> int:
        """Returns the predefined benchmark lower bound if known, else fallback (default: 1, matching C++ reference)."""
        cleaned = self.name.strip()
        if "/" in cleaned or "\\" in cleaned:
            cleaned = Path(cleaned).name
        if cleaned in BENCHMARK_LOWER_BOUNDS:
            return BENCHMARK_LOWER_BOUNDS[cleaned]
        stripped = (
            cleaned[2:]
            if (len(cleaned) >= 2 and cleaned[0].isalpha() and cleaned[1] == "-")
            else cleaned
        )
        if stripped in BENCHMARK_LOWER_BOUNDS:
            return BENCHMARK_LOWER_BOUNDS[stripped]
        stem = cleaned.replace(".mtx.rnd", "").replace(".rnd", "").replace(".mtx", "")
        if stem in BENCHMARK_LOWER_BOUNDS:
            return BENCHMARK_LOWER_BOUNDS[stem]
        return max(1, fallback)

    def get_theoretical_upper_bound(self) -> int:
        """Theoretical upper bound based on graph topology (no isolated vertices: floor(n/2), else n-1)."""
        if not self.has_isolated_vertices():
            return self.n // 2
        return self.n - 1

    def get_upper_bound(self, fallback: Optional[int] = None) -> int:
        """Upper search bound for antibandwidth w.

        Returns published benchmark upper bound if recognized, else fallback (if provided)
        or theoretical upper bound floor(n / 2) (or n - 1 if isolated vertices exist).
        """
        cleaned = self.name.strip()
        if "/" in cleaned or "\\" in cleaned:
            cleaned = Path(cleaned).name
        if cleaned in BENCHMARK_UPPER_BOUNDS:
            return BENCHMARK_UPPER_BOUNDS[cleaned]
        stripped = (
            cleaned[2:]
            if (len(cleaned) >= 2 and cleaned[0].isalpha() and cleaned[1] == "-")
            else cleaned
        )
        if stripped in BENCHMARK_UPPER_BOUNDS:
            return BENCHMARK_UPPER_BOUNDS[stripped]
        stem = cleaned.replace(".mtx.rnd", "").replace(".rnd", "").replace(".mtx", "")
        if stem in BENCHMARK_UPPER_BOUNDS:
            return BENCHMARK_UPPER_BOUNDS[stem]

        if fallback is not None:
            return fallback
        return self.get_theoretical_upper_bound()

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
