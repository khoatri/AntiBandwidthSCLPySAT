import math
import itertools
import pytest
from pysat.solvers import Solver

from src.encoding.product_eo import encode_amo_seq, encode_product_eo


def test_amo_seq_counts() -> None:
    for t in [2, 3, 4, 5, 8]:
        var_count = 0

        def alloc() -> int:
            nonlocal var_count
            var_count += 1
            return 100 + var_count

        inputs = list(range(1, t + 1))
        clauses = encode_amo_seq(inputs, alloc)

        if t == 2:
            assert len(clauses) == 1
            assert var_count == 0
        else:
            assert len(clauses) == 3 * t - 5
            assert var_count == t - 2


def test_amo_seq_semantics() -> None:
    # Test on t = 4: inputs = [1, 2, 3, 4]
    t = 4
    inputs = list(range(1, t + 1))

    # All combinations of truth assignments
    for true_indices in range(t + 1):
        for true_vars in itertools.combinations(inputs, true_indices):
            var_id = 100

            def alloc() -> int:
                nonlocal var_id
                var_id += 1
                return var_id

            clauses = encode_amo_seq(inputs, alloc)

            unit_clauses = [[v if v in true_vars else -v] for v in inputs]

            with Solver(name="kissat404", bootstrap_with=clauses + unit_clauses) as solver:
                sat = solver.solve()
                if len(true_vars) <= 1:
                    assert sat is True, f"Expected SAT for {true_vars}"
                else:
                    assert sat is False, f"Expected UNSAT for {true_vars}"


def test_product_eo_counts() -> None:
    for n in [2, 3, 4, 5, 6, 10]:
        var_count = 0

        def alloc() -> int:
            nonlocal var_count
            var_count += 1
            return 100 + var_count

        inputs = list(range(1, n + 1))
        clauses = encode_product_eo(inputs, alloc)

        p = math.ceil(math.sqrt(n))
        q = math.ceil(n / p)

        if n == 2:
            expected_c = 2
            expected_a = 0
        else:
            expected_c = 2 * n + 3 * (p + q) - 9
            expected_a = 2 * (p + q) - 4

        assert len(clauses) == expected_c
        assert var_count == expected_a


def test_product_eo_semantics() -> None:
    # Exhaustively test Exactly-One on n = 5
    n = 5
    inputs = list(range(1, n + 1))

    for k in range(n + 1):
        for true_vars in itertools.combinations(inputs, k):
            var_id = 100

            def alloc() -> int:
                nonlocal var_id
                var_id += 1
                return var_id

            clauses = encode_product_eo(inputs, alloc)
            unit_clauses = [[v if v in true_vars else -v] for v in inputs]

            with Solver(name="kissat404", bootstrap_with=clauses + unit_clauses) as solver:
                sat = solver.solve()
                if len(true_vars) == 1:
                    assert sat is True, f"Expected SAT when exactly 1 True: {true_vars}"
                else:
                    assert sat is False, f"Expected UNSAT for {true_vars}"
