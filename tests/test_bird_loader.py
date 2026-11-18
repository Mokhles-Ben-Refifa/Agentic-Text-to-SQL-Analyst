"""Tests for BIRD/Spider loader, database manager, and 30/70 question splitting."""

import pytest

from data.bird_loader import BenchmarkLoader
from data.database import DatabaseManager
from data.split import split_questions


@pytest.fixture(scope="module")
def financial_sqlite(tmp_path_factory):
    """Sets up a temporary BIRD financial sqlite database for tests."""
    temp_dir = tmp_path_factory.mktemp("bird_test")
    loader = BenchmarkLoader(base_dir=temp_dir)
    sqlite_path = loader.create_mock_financial_database()
    return sqlite_path, loader


def test_financial_schema_tables(financial_sqlite):
    sqlite_path, _ = financial_sqlite
    manager = DatabaseManager()
    tables = manager.get_table_names(sqlite_path=sqlite_path)

    expected = {"district", "account", "client", "disp", "loan", "trans", "internal_audit"}
    assert expected.issubset(set(tables))


def test_financial_query_execution(financial_sqlite):
    sqlite_path, _ = financial_sqlite
    manager = DatabaseManager()

    # Query loan amounts by status
    sql = "SELECT status, COUNT(*) as cnt, AVG(amount) as avg_amount FROM loan GROUP BY status"
    results = manager.execute_query(sql, sqlite_path=sqlite_path)

    assert len(results) > 0
    assert "status" in results[0]
    assert "avg_amount" in results[0]


def test_schema_metadata_extraction(financial_sqlite):
    sqlite_path, _ = financial_sqlite
    manager = DatabaseManager()

    schema = manager.get_schema_metadata(sqlite_path=sqlite_path, tables=["loan", "district"])
    assert "loan" in schema
    assert "district" in schema

    loan_col_names = [c["name"] for c in schema["loan"]["columns"]]
    assert "loan_id" in loan_col_names
    assert "amount" in loan_col_names
    assert "status" in loan_col_names


def test_explain_query_plan(financial_sqlite):
    sqlite_path, _ = financial_sqlite
    manager = DatabaseManager()

    sql = "SELECT * FROM trans WHERE amount > 2000"
    plan = manager.explain_query(sql, sqlite_path=sqlite_path)

    assert plan["dialect"] == "sqlite"
    assert "raw_plan" in plan


def test_split_questions_deterministic():
    sample_questions = [
        {"question_id": i, "question": f"Question {i}", "SQL": f"SELECT {i}"} for i in range(100)
    ]

    dev1, test1 = split_questions(sample_questions, dev_ratio=0.30, seed=42)
    dev2, test2 = split_questions(sample_questions, dev_ratio=0.30, seed=42)

    # Determinism
    assert dev1 == dev2
    assert test1 == test2

    # Ratio
    assert len(dev1) == 30
    assert len(test1) == 70

    # No overlap
    dev_ids = {q["question_id"] for q in dev1}
    test_ids = {q["question_id"] for q in test1}
    assert len(dev_ids.intersection(test_ids)) == 0
