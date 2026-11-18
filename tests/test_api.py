"""Tests for FastAPI backend endpoints."""

from fastapi.testclient import TestClient

from app.api import app

client = TestClient(app)


def test_health_check():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "healthy"


def test_get_tables_endpoint():
    res = client.get("/api/tables?db_target=./data/benchmarks/bird/financial/financial.sqlite")
    assert res.status_code == 200
    tables = res.json()
    assert "loan" in tables
    assert "account" in tables
    assert "internal_audit" not in tables


def test_get_table_details_endpoint():
    res = client.get("/api/tables/loan?db_target=./data/benchmarks/bird/financial/financial.sqlite")
    assert res.status_code == 200
    details = res.json()
    assert "columns" in details
    col_names = [c["name"] for c in details["columns"]]
    assert "amount" in col_names


def test_forbidden_table_endpoint_blocks_audit():
    res = client.get(
        "/api/tables/internal_audit?db_target=./data/benchmarks/bird/financial/financial.sqlite"
    )
    assert res.status_code == 403
    assert "forbidden" in res.json()["detail"].lower()


def test_post_query_endpoint():
    payload = {
        "question": "What is the average loan amount grouped by status?",
        "dialect": "sqlite",
        "db_target": "./data/benchmarks/bird/financial/financial.sqlite",
    }
    res = client.post("/api/query", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert "thread_id" in data
    assert data["intent"] == "answerable"
    assert "sql" in data
    assert "SELECT" in data["sql"].upper()
    assert data["row_count"] > 0
    assert "answer" in data
