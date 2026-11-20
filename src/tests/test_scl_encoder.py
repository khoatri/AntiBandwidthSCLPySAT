import pytest
from pysat.formula import CNF

from src.encoding.scl_encoder import EncodingResult, SCLEncoder
from src.utils.graph import Graph


def test_scl_encoder_parameter_validation() -> None:
    g = Graph(n=5, edges=((1, 2), (2, 3)))

    with pytest.raises(ValueError, match="Threshold w must satisfy 2 <= w <= n"):
        SCLEncoder(graph=g, w=1)

    with pytest.raises(ValueError, match="Threshold w must satisfy 2 <= w <= n"):
        SCLEncoder(graph=g, w=6)


def test_scl_encoder_result_structure() -> None:
    g = Graph(n=4, edges=((1, 2), (2, 3), (3, 4)))
    encoder = SCLEncoder(graph=g, w=2, sym_mode="f")
    res = encoder.encode()

    assert isinstance(res, EncodingResult)
    assert isinstance(res.cnf, CNF)
    assert res.n_vars > 0
    assert res.n_clauses > 0
    assert len(res.cnf.clauses) == res.n_clauses

    # Stats validation
    assert res.stats["n"] == 4
    assert res.stats["m"] == 3
    assert res.stats["w"] == 2
    assert res.stats["sym_mode"] == "f"
    assert res.stats["actual_N"] == res.n_vars
    assert res.stats["actual_C"] == res.n_clauses
    assert res.stats["cache_size"] > 0


def test_scl_encoder_clause_order_and_literals() -> None:
    # Test generation order:
    # 1. Symmetry breaking unit clauses (if sym_mode != 'n')
    # 2. Label product EO clauses
    # 3. Vertex block ladders & block occupancy
    # 4. Edge sliding-window exclusions
    g = Graph(n=4, edges=((1, 2), (2, 3)))
    encoder = SCLEncoder(graph=g, w=2, sym_mode="f")
    res = encoder.encode()

    clauses = res.cnf.clauses

    # 1. First floor(4 / 2) = 2 clauses must be symmetry breaking unit clauses
    assert len(clauses[0]) == 1
    assert len(clauses[1]) == 1
    assert clauses[0][0] < 0
    assert clauses[1][0] < 0

    # All literals in all clauses must be valid non-zero integers bounded by n_vars
    for clause in clauses:
        assert len(clause) > 0
        for lit in clause:
            assert lit != 0
            assert abs(lit) <= res.n_vars

    # Primary variable IDs are within [1, n^2 = 16]
    # Auxiliary variables start strictly at n^2 + 1 = 17
    aux_literals = {
        abs(lit) for clause in clauses for lit in clause if abs(lit) > 16
    }
    if aux_literals:
        assert min(aux_literals) == 17
        assert max(aux_literals) == res.n_vars
