from src.encoding.symmetry import encode_symmetry_breaking
from src.utils.graph import Graph


def test_symmetry_breaking_mode_none() -> None:
    g = Graph(n=5, edges=((1, 2), (2, 3)))
    clauses = encode_symmetry_breaking(g, sym_mode="n")
    assert clauses == []


def test_symmetry_breaking_even_n() -> None:
    # n = 6: floor(6 / 2) = 3 unit clauses
    # Vertex 1 receives labels 1..6 with IDs 1..6
    # Upper half: ell in {ceil(6/2)+1..6} = {4, 5, 6}
    g = Graph(n=6, edges=((1, 2), (2, 3)))
    clauses = encode_symmetry_breaking(g, sym_mode="f")

    assert len(clauses) == 3
    assert clauses == [[-4], [-5], [-6]]


def test_symmetry_breaking_odd_n() -> None:
    # n = 5: floor(5 / 2) = 2 unit clauses
    # Upper half: ell in {ceil(5/2)+1..5} = {3+1..5} = {4, 5}
    # Middle label 3 is unrestricted!
    g = Graph(n=5, edges=((1, 2), (2, 3)))
    clauses = encode_symmetry_breaking(g, sym_mode="f")

    assert len(clauses) == 2
    assert clauses == [[-4], [-5]]


def test_symmetry_breaking_degree_modes() -> None:
    # Star graph: vertex 2 is center with degree 3, vertices 1, 3, 4 have degree 1
    # n = 4
    edges = ((1, 2), (2, 3), (2, 4))
    g = Graph(n=4, edges=edges)

    # Mode 'h': center is vertex 2.
    # Vertex 2 variables: (2 - 1)*4 + ell = 4 + ell
    # Upper half: ell in {3, 4} => variable IDs 7, 8
    clauses_h = encode_symmetry_breaking(g, sym_mode="h")
    assert len(clauses_h) == 2
    assert clauses_h == [[-7], [-8]]

    # Mode 'l': leaves are 1, 3, 4 (degree 1). Smallest index is 1.
    # Vertex 1 variables: (1 - 1)*4 + ell = ell
    # Upper half: ell in {3, 4} => variable IDs 3, 4
    clauses_l = encode_symmetry_breaking(g, sym_mode="l")
    assert len(clauses_l) == 2
    assert clauses_l == [[-3], [-4]]
