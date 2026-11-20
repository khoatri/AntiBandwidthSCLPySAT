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
    # No isolated vertices => theoretical upper bound is floor(n / 2) = 15
    assert g.get_theoretical_upper_bound() == 15
    # Benchmark bounds from Sinnl (2018)
    assert g.get_upper_bound() == 8
    assert g.get_lower_bound() == 6


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


def test_graph_hashable_and_usable_in_sets_and_dicts() -> None:
    g1 = Graph(n=4, edges=((1, 2), (2, 3), (3, 4)), name="P4")
    g2 = Graph(n=4, edges=((1, 2), (2, 3), (3, 4)), name="P4")
    g3 = Graph(n=3, edges=((1, 2),), name="P2")

    # Hash should be an int and consistent
    assert isinstance(hash(g1), int)
    assert hash(g1) == hash(g2)

    # Graph can be in sets
    s = {g1, g2, g3}
    assert len(s) == 2

    # Graph can be dict key
    d = {g1: "data_p4", g3: "data_p2"}
    assert d[g2] == "data_p4"


def test_graph_get_lower_and_upper_bounds_all_24_benchmarks() -> None:
    expected_bounds = {
        "A-pores_1.mtx.rnd": (6, 8),
        "B-ibm32.mtx.rnd": (9, 9),
        "C-bcspwr01.mtx.rnd": (16, 17),
        "D-bcsstk01.mtx.rnd": (8, 9),
        "E-bcspwr02.mtx.rnd": (21, 22),
        "F-curtis54.mtx.rnd": (12, 13),
        "G-will57.mtx.rnd": (12, 14),
        "H-impcol_b.mtx.rnd": (8, 8),
        "I-ash85.mtx.rnd": (19, 27),
        "J-nos4.mtx.rnd": (32, 40),
        "K-dwt__234.mtx.rnd": (46, 58),
        "L-bcspwr03.mtx.rnd": (39, 39),
        "M-bcsstk06.mtx.rnd": (28, 72),
        "N-bcsstk07.mtx.rnd": (28, 72),
        "O-impcol_d.mtx.rnd": (91, 173),
        "P-can__445.mtx.rnd": (78, 120),
        "Q-494_bus.mtx.rnd": (219, 246),
        "R-dwt__503.mtx.rnd": (46, 71),
        "S-sherman4.mtx.rnd": (256, 272),
        "T-dwt__592.mtx.rnd": (103, 150),
        "U-662_bus.mtx.rnd": (219, 220),
        "V-nos6.mtx.rnd": (326, 337),
        "W-685_bus.mtx.rnd": (136, 136),
        "X-can__715.mtx.rnd": (112, 142),
    }
    for filename, (expected_lb, expected_ub) in expected_bounds.items():
        # Test full filename
        g = Graph(n=1000, edges=((1, 2),), name=filename)
        assert g.get_lower_bound() == expected_lb, f"LB failed for {filename}"
        assert g.get_upper_bound() == expected_ub, f"UB failed for {filename}"

        # Test name without letter prefix (e.g. pores_1.mtx.rnd)
        stripped = filename[2:]
        g_stripped = Graph(n=1000, edges=((1, 2),), name=stripped)
        assert g_stripped.get_lower_bound() == expected_lb, f"LB failed for stripped {stripped}"
        assert g_stripped.get_upper_bound() == expected_ub, f"UB failed for stripped {stripped}"

        # Test name without .mtx.rnd extension
        stem = filename.replace(".mtx.rnd", "")
        g_stem = Graph(n=1000, edges=((1, 2),), name=stem)
        assert g_stem.get_lower_bound() == expected_lb, f"LB failed for stem {stem}"
        assert g_stem.get_upper_bound() == expected_ub, f"UB failed for stem {stem}"


def test_graph_get_bounds_path_and_unrecognized_fallback() -> None:
    # Full file path with isolated vertices (n=30, 1 edge)
    g_path = Graph(n=30, edges=((1, 2),), name="instances/A-pores_1.mtx.rnd")
    assert g_path.get_lower_bound() == 6
    # Benchmark upper bound takes priority over theoretical bound
    assert g_path.get_upper_bound() == 8
    # Theoretical bound has isolated vertices, so n - 1 = 29
    assert g_path.get_theoretical_upper_bound() == 29

    # Unknown graph without isolated vertices defaults to fallback 2 and theoretical n // 2
    g_unknown = Graph(n=4, edges=((1, 2), (2, 3), (3, 4)), name="custom_graph.mtx.rnd")
    assert g_unknown.get_lower_bound() == 2
    assert g_unknown.get_lower_bound(fallback=5) == 5
    assert g_unknown.get_upper_bound() == 2  # 4 // 2
    assert g_unknown.get_upper_bound(fallback=4) == 4

    # Fallback LB clamped to at least 2
    assert g_unknown.get_lower_bound(fallback=0) == 2
    assert g_unknown.get_lower_bound(fallback=1) == 2


