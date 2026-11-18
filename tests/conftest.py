"""Pytest shared fixtures."""

import pytest


@pytest.fixture
def sample_question() -> str:
    return "What was the loss ratio by country last quarter?"
