from __future__ import annotations

from pathlib import Path
from typing import Union

from src.utils.graph import Graph


def parse_instance(file_path: Union[str, Path]) -> Graph:
    """Parses a benchmark graph instance (*.mtx.rnd).

    Expected format:
        Line 1 (optional): Nombre del problema: <instance_name>
        Header: <n> <expected_m> (or legacy <n> <ignored_val> <expected_m>)
        Edge lines: <u> <v>
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Instance file not found: {path}")

    name = path.name
    n: int | None = None
    expected_m: int | None = None
    edges: list[tuple[int, int]] = []

    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line_num, line in enumerate(f, 1):
            line_str = line.strip()
            if not line_str or line_str.startswith(("#", "%", "c ")):
                continue

            if "Nombre del problema:" in line_str:
                parts = line_str.split("Nombre del problema:", 1)
                extracted_name = parts[1].strip()
                if extracted_name:
                    name = extracted_name
                continue

            tokens = line_str.split()
            # Try to parse integers
            try:
                numbers = [int(tok) for tok in tokens]
            except ValueError:
                continue

            if n is None:
                if len(numbers) >= 3:
                    # In legacy 3-token instance headers (<n> <legacy_val> <m>), the middle value
                    # (historically bandwidth or unused parameter) is ignored.
                    n, expected_m = numbers[0], numbers[2]
                elif len(numbers) == 2:
                    # Fallback for standard 2-number header: n, m
                    n, expected_m = numbers[0], numbers[1]
                else:
                    raise ValueError(
                        f"Malformed header on line {line_num} in {path}: '{line_str}'"
                    )
            else:
                if len(numbers) == 2:
                    u, v = numbers[0], numbers[1]
                    edges.append((u, v))
                elif len(numbers) == 3:
                    # Sometimes edges might have a weight: u v w
                    u, v = numbers[0], numbers[1]
                    edges.append((u, v))

    if n is None:
        raise ValueError(f"Could not find graph dimensions header in {path}")

    graph = Graph(
        n=n,
        edges=tuple(edges),
        name=name,
    )

    if expected_m is not None and graph.m != expected_m:
        raise ValueError(
            f"Edge count mismatch in {path}: header specified m={expected_m}, "
            f"but found {graph.m} unique undirected edges (raw lines: {len(edges)})."
        )

    return graph
