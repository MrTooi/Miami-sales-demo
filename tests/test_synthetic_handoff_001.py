from agent_evals.synthetic_handoff_001 import stable_unique


def test_removes_duplicates():
    result = stable_unique(["alpha", "alpha", "beta"])
    assert set(result) == {"alpha", "beta"}
    assert len(result) == 2


def test_empty_input():
    assert stable_unique([]) == []
