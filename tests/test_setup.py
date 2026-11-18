"""Smoke test to verify project environment and basic imports."""


def test_environment_setup(sample_question: str) -> None:
    assert sample_question is not None
    assert "loss ratio" in sample_question
