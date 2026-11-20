from pathlib import Path
import pytest

from src.utils.graph import Graph
from src.utils.graph_parser import parse_instance

INSTANCES_DIR = Path(__file__).resolve().parents[2] / "instances"


def test_parse_real_instance_pores_1() -> None:
    instance_path = INSTANCES_DIR / "A-pores_1.mtx.rnd"
    assert instance_path.exists(), f"Instance file missing: {instance_path}"

    g = parse_instance(instance_path)
    assert g.n == 30
    assert g.best_known_w == 7
    assert g.m == 103
    assert g.name == "pores_1.mtx.rnd"

    # Properties
    assert not g.has_isolated_vertices()
    assert g.min_degree > 0
    # No isolated vertices => upper bound is floor(n / 2) = 15
    assert g.get_upper_bound() == 15


def test_parse_synthetic_instance(tmp_path: Path) -> None:
    content = """Nombre del problema: test_graph.mtx.rnd
4 2 3
1 2
2 3
3 4
"""
    file_path = tmp_path / "test_graph.mtx.rnd"
    file_path.write_text(content, encoding="utf-8")

    g = parse_instance(file_path)
    assert g.n == 4
    assert g.best_known_w == 2
    assert g.m == 3
    assert g.name == "test_graph.mtx.rnd"
    assert g.edges == ((1, 2), (2, 3), (3, 4))
    assert g.degrees == {1: 1, 2: 2, 3: 2, 4: 1}
    assert not g.has_isolated_vertices()
    assert g.get_upper_bound() == 2  # 4 // 2


def test_graph_deduplication_and_self_loops() -> None:
    # Edges with reversed order, duplicate, and self-loop
    raw_edges = ((2, 1), (1, 2), (3, 3), (2, 3))
    g = Graph(n=3, edges=raw_edges, name="dedup_test")

    assert g.edges == ((1, 2), (2, 3))
    assert g.m == 2
    assert g.degrees == {1: 1, 2: 2, 3: 1}


def test_isolated_vertices_upper_bound() -> None:
    # Triangle (1-2-3) plus isolated vertex 4
    edges = ((1, 2), (2, 3), (1, 3))
    g = Graph(n=4, edges=edges)

    assert g.has_isolated_vertices()
    assert g.degrees[4] == 0
    # With isolated vertices, bound can reach n - 1
    assert g.get_upper_bound() == 3


def test_symmetry_breaking_selection() -> None:
    # Graph: 1 has deg 1, 2 has deg 2, 3 has deg 2, 4 has deg 1
    edges = ((1, 2), (2, 3), (3, 4))
    g = Graph(n=4, edges=edges)

    assert g.get_symmetry_vertex("n") is None
    assert g.get_symmetry_vertex("f") == 1

    # High degree: vertices 2 and 3 both have degree 2. Tie broken by lowest index => 2
    assert g.get_symmetry_vertex("h") == 2

    # Low degree: vertices 1 and 4 both have degree 1. Tie broken by lowest index => 1
    assert g.get_symmetry_vertex("l") == 1

    with pytest.raises(ValueError, match="Unknown symmetry breaking mode"):
        g.get_symmetry_vertex("invalid")


def test_invalid_graph_construction() -> None:
    with pytest.raises(ValueError, match="at least 2 vertices"):
        Graph(n=1, edges=())

    with pytest.raises(ValueError, match="outside valid range"):
        Graph(n=3, edges=((1, 4),))


def test_parser_file_not_found() -> None:
    with pytest.raises(FileNotFoundError):
        parse_instance("non_existent_file.mtx.rnd")


def test_parser_corrupted_header(tmp_path: Path) -> None:
    bad_file = tmp_path / "bad.rnd"
    bad_file.write_text("just text no numbers\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Could not find graph dimensions"):
        parse_instance(bad_file)


def test_parser_edge_count_mismatch(tmp_path: Path) -> None:
    # Header claims m=5, but only 2 edges are provided
    content = """Nombre del problema: mismatch.rnd
4 2 5
1 2
2 3
"""
    mismatch_file = tmp_path / "mismatch.rnd"
    mismatch_file.write_text(content, encoding="utf-8")

    with pytest.raises(ValueError, match="Edge count mismatch"):
        parse_instance(mismatch_file)

