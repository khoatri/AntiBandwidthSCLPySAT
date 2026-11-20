from src.utils.graph import Graph
from src.utils.solution_verifier import (
    compute_actual_bandwidth,
    verify_solution,
)


def test_solution_verifier_valid_path() -> None:
    # Path P_4: 1 - 2 - 3 - 4
    # Labeling: phi(1)=1, phi(2)=3, phi(3)=2, phi(4)=4
    # Edge differences:
    # (1, 2): |1 - 3| = 2
    # (2, 3): |3 - 2| = 1
    # (3, 4): |2 - 4| = 2
    # Actual bandwidth = min(2, 1, 2) = 1
    g = Graph(n=4, edges=((1, 2), (2, 3), (3, 4)))
    labeling = {1: 1, 2: 3, 3: 2, 4: 4}

    assert compute_actual_bandwidth(g, labeling) == 1

    valid, msg = verify_solution(g, labeling, w=1)
    assert valid is True
    assert msg == "OK"

    # For w=2, edge (2, 3) violates distance requirement
    valid, msg = verify_solution(g, labeling, w=2)
    assert valid is False
    assert "violates distance requirement" in msg
    assert "(2, 3)" in msg


def test_solution_verifier_optimal_labeling() -> None:
    # Path P_4 with optimal labeling achieving w = 2:
    # phi(1)=1, phi(2)=4, phi(3)=2, phi(4)=3
    # Edge differences:
    # (1, 2): |1 - 4| = 3
    # (2, 3): |4 - 2| = 2
    # (3, 4): |2 - 3| = 1 (wait: |2-3|=1, so beta=1)
    # Better: phi(1)=1, phi(2)=3, phi(3)=1... no, permutation
    # For P_4:
    # Try: phi = {1: 2, 2: 4, 3: 1, 4: 3}
    # (1, 2): |2 - 4| = 2
    # (2, 3): |4 - 1| = 3
    # (3, 4): |1 - 3| = 2
    # Actual bandwidth = min(2, 3, 2) = 2!
    g = Graph(n=4, edges=((1, 2), (2, 3), (3, 4)))
    labeling = {1: 2, 2: 4, 3: 1, 4: 3}

    assert compute_actual_bandwidth(g, labeling) == 2

    valid, msg = verify_solution(g, labeling, w=2)
    assert valid is True
    assert msg == "OK"

    # w = 3 should fail
    valid, msg = verify_solution(g, labeling, w=3)
    assert valid is False


def test_solution_verifier_missing_vertex() -> None:
    g = Graph(n=3, edges=((1, 2), (2, 3)))
    labeling = {1: 1, 2: 2}  # vertex 3 missing

    valid, msg = verify_solution(g, labeling, w=1)
    assert valid is False
    assert "Missing labels for vertices" in msg


def test_solution_verifier_extra_vertex() -> None:
    g = Graph(n=2, edges=((1, 2),))
    labeling = {1: 1, 2: 2, 99: 3}

    valid, msg = verify_solution(g, labeling, w=1)
    assert valid is False
    assert "Unexpected vertex keys" in msg


def test_solution_verifier_duplicate_label() -> None:
    g = Graph(n=3, edges=((1, 2), (2, 3)))
    labeling = {1: 1, 2: 2, 3: 1}  # label 1 used twice

    valid, msg = verify_solution(g, labeling, w=1)
    assert valid is False
    assert "Duplicate label assignments" in msg


def test_solution_verifier_out_of_range_label() -> None:
    g = Graph(n=3, edges=((1, 2), (2, 3)))
    labeling = {1: 1, 2: 2, 3: 4}  # label 4 > n=3

    valid, msg = verify_solution(g, labeling, w=1)
    assert valid is False
    assert "out of range" in msg
