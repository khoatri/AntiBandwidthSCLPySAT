from pathlib import Path
import pytest

from src.encoding.scl_encoder import SCLEncoder
from src.utils.graph import Graph
from src.utils.graph_parser import parse_instance

INSTANCES_DIR = Path(__file__).resolve().parents[2] / "instances"


def test_concrete_example_n6_w3() -> None:
    # Example from Section 5 of docs/encoding.md: n=6, m=6, w=3
    # Cycle graph C_6
    edges = ((1, 2), (2, 3), (3, 4), (4, 5), (5, 6), (1, 6))
    g = Graph(n=6, edges=edges)

    # 1. Without symmetry breaking
    encoder_no_sym = SCLEncoder(graph=g, w=3, sym_mode="n")
    exp_n, exp_c = encoder_no_sym.expected_counts()
    assert exp_n == 96
    assert exp_c == 288

    res_no_sym = encoder_no_sym.encode()
    assert res_no_sym.n_vars == 96
    assert res_no_sym.n_clauses == 288

    # 2. With symmetry breaking (mode 'f')
    encoder_sym = SCLEncoder(graph=g, w=3, sym_mode="f")
    exp_n_sym, exp_c_sym = encoder_sym.expected_counts()
    assert exp_n_sym == 96
    assert exp_c_sym == 291  # 288 + floor(6 / 2) = 288 + 3 = 291

    res_sym = encoder_sym.encode()
    assert res_sym.n_vars == 96
    assert res_sym.n_clauses == 291


@pytest.mark.parametrize("n", [3, 4, 5, 6, 7, 8, 10])
def test_parameter_sweep_paths(n: int) -> None:
    # Path graph P_n: m = n - 1 edges
    edges = tuple((i, i + 1) for i in range(1, n))
    g = Graph(n=n, edges=edges)

    for w in range(2, n + 1):
        for sym in ["n", "f", "h", "l"]:
            encoder = SCLEncoder(graph=g, w=w, sym_mode=sym)
            exp_n, exp_c = encoder.expected_counts()
            res = encoder.encode()

            assert res.n_vars == exp_n, (
                f"Mismatch in N for n={n}, w={w}, sym={sym}: "
                f"got {res.n_vars}, expected {exp_n}"
            )
            assert res.n_clauses == exp_c, (
                f"Mismatch in C for n={n}, w={w}, sym={sym}: "
                f"got {res.n_clauses}, expected {exp_c}"
            )


@pytest.mark.parametrize("n", [4, 5, 6, 7])
def test_parameter_sweep_complete_graphs(n: int) -> None:
    # Complete graph K_n: m = n*(n-1)//2 edges
    edges = tuple((i, j) for i in range(1, n + 1) for j in range(i + 1, n + 1))
    g = Graph(n=n, edges=edges)

    for w in range(2, n + 1):
        encoder = SCLEncoder(graph=g, w=w, sym_mode="n")
        exp_n, exp_c = encoder.expected_counts()
        res = encoder.encode()

        assert res.n_vars == exp_n
        assert res.n_clauses == exp_c


def test_counts_on_real_instances() -> None:
    # Instance A-pores_1.mtx.rnd: n=30, m=103, best_known_w=7
    pores_path = INSTANCES_DIR / "A-pores_1.mtx.rnd"
    if pores_path.exists():
        g = parse_instance(pores_path)
        for w in [2, 7, 15]:
            for sym in ["n", "h"]:
                encoder = SCLEncoder(graph=g, w=w, sym_mode=sym)
                exp_n, exp_c = encoder.expected_counts()
                res = encoder.encode()

                assert res.n_vars == exp_n
                assert res.n_clauses == exp_c

    # Instance B-ibm32.mtx.rnd: n=32, m=90, best_known_w=9
    ibm_path = INSTANCES_DIR / "B-ibm32.mtx.rnd"
    if ibm_path.exists():
        g = parse_instance(ibm_path)
        for w in [2, 9, 16]:
            encoder = SCLEncoder(graph=g, w=w, sym_mode="f")
            exp_n, exp_c = encoder.expected_counts()
            res = encoder.encode()

            assert res.n_vars == exp_n
            assert res.n_clauses == exp_c
