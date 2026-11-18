"""Tests for FastMCP Server tools and defense-in-depth SQL guardrails."""

from mcp_server.guardrails import SQLGuardrailEngine
from mcp_server.models import ErrorType
from mcp_server.server import (
    describe_table,
    explain_query,
    list_tables,
    run_readonly_query,
    validate_sql,
)


def test_single_statement_enforcement():
    engine = SQLGuardrailEngine()
    # Stacked statement injection
    attack_sql = "SELECT * FROM loan; DROP TABLE district;"
    result = engine.validate_and_sanitize(attack_sql)
    assert not result.is_valid
    assert result.error_type == ErrorType.GUARDRAIL_VIOLATION
    assert "Multiple SQL statements" in result.error_message


def test_write_operations_blocked():
    engine = SQLGuardrailEngine()

    insert_attack = "INSERT INTO loan (loan_id, amount) VALUES (999, 1000);"
    res = engine.validate_and_sanitize(insert_attack)
    assert not res.is_valid
    assert res.error_type == ErrorType.GUARDRAIL_VIOLATION

    drop_attack = "DROP TABLE loan;"
    res2 = engine.validate_and_sanitize(drop_attack)
    assert not res2.is_valid

    delete_attack = "DELETE FROM loan WHERE loan_id = 1;"
    res3 = engine.validate_and_sanitize(delete_attack)
    assert not res3.is_valid


def test_forbidden_tables_blocked():
    engine = SQLGuardrailEngine()

    # Query attempting to exfiltrate internal audit table
    attack = "SELECT * FROM internal_audit;"
    res = engine.validate_and_sanitize(attack)
    assert not res.is_valid
    assert res.error_type == ErrorType.FORBIDDEN_TABLE
    assert "internal_audit" in res.error_message


def test_prohibited_sleep_functions_blocked():
    engine = SQLGuardrailEngine()

    pg_sleep_attack = "SELECT loan_id, pg_sleep(10) FROM loan;"
    res = engine.validate_and_sanitize(pg_sleep_attack, dialect="postgres")
    assert not res.is_valid
    assert res.error_type == ErrorType.PROHIBITED_FUNCTION

    sleep_attack = "SELECT loan_id, sleep(5) FROM loan;"
    res2 = engine.validate_and_sanitize(sleep_attack, dialect="sqlite")
    assert not res2.is_valid
    assert res2.error_type == ErrorType.PROHIBITED_FUNCTION


def test_pii_columns_blocked():
    engine = SQLGuardrailEngine()

    pii_attack = "SELECT first_name, national_id FROM customer;"
    res = engine.validate_and_sanitize(pii_attack)
    assert not res.is_valid
    assert res.error_type == ErrorType.PII_VIOLATION
    assert "national_id" in res.error_message


def test_forced_limit_injection():
    engine = SQLGuardrailEngine(max_limit=1000)

    # 1. No limit specified -> injects LIMIT 1000
    res1 = engine.validate_and_sanitize("SELECT * FROM loan")
    assert res1.is_valid
    assert res1.has_forced_limit
    assert res1.enforced_limit == 1000
    assert "LIMIT 1000" in res1.sanitized_sql.upper()

    # 2. Huge limit specified -> clamped to 1000
    res2 = engine.validate_and_sanitize("SELECT * FROM loan LIMIT 50000")
    assert res2.is_valid
    assert res2.has_forced_limit
    assert res2.enforced_limit == 1000
    assert "LIMIT 1000" in res2.sanitized_sql.upper()

    # 3. Smaller limit -> preserved
    res3 = engine.validate_and_sanitize("SELECT * FROM loan LIMIT 25")
    assert res3.is_valid
    assert not res3.has_forced_limit
    assert res3.enforced_limit == 25
    assert "LIMIT 25" in res3.sanitized_sql.upper()


def test_table_allowlist_enforcement():
    engine = SQLGuardrailEngine()
    allowed = ["loan", "account"]

    valid_query = "SELECT * FROM loan INNER JOIN account ON loan.account_id = account.account_id"
    res1 = engine.validate_and_sanitize(valid_query, allowed_tables=allowed)
    assert res1.is_valid

    invalid_query = (
        "SELECT * FROM loan INNER JOIN district ON loan.account_id = district.district_id"
    )
    res2 = engine.validate_and_sanitize(invalid_query, allowed_tables=allowed)
    assert not res2.is_valid
    assert res2.error_type == ErrorType.FORBIDDEN_TABLE
    assert "district" in res2.error_message


def test_mcp_list_and_describe_tables():
    # Targets our initialized financial.sqlite database
    db_path = "./data/benchmarks/bird/financial/financial.sqlite"
    tables = list_tables(db_target=db_path)
    assert "loan" in tables
    assert "account" in tables
    assert "internal_audit" not in tables  # Never exposed!

    description = describe_table("loan", db_target=db_path)
    col_names = [c["name"] for c in description.get("columns", [])]
    assert "amount" in col_names
    assert "status" in col_names


def test_mcp_validate_sql_tool():
    res = validate_sql("SELECT amount, status FROM loan WHERE amount > 5000")
    assert res["is_valid"]
    assert "sanitized_sql" in res


def test_mcp_explain_query_tool():
    db_path = "./data/benchmarks/bird/financial/financial.sqlite"
    plan = explain_query("SELECT * FROM loan", dialect="sqlite", db_target=db_path)
    assert plan["dialect"] == "sqlite"
    assert "needs_approval" in plan


def test_mcp_run_readonly_query_success():
    db_path = "./data/benchmarks/bird/financial/financial.sqlite"
    res = run_readonly_query(
        "SELECT loan_id, amount, status FROM loan", dialect="sqlite", db_target=db_path
    )
    assert res["success"]
    assert res["row_count"] > 0
    assert len(res["data"]) > 0
    assert "amount" in res["data"][0]


def test_mcp_run_readonly_query_blocks_attack():
    db_path = "./data/benchmarks/bird/financial/financial.sqlite"
    # Attack: DROP TABLE attempt
    res = run_readonly_query("DROP TABLE loan", dialect="sqlite", db_target=db_path)
    assert not res["success"]
    assert res["error_type"] == ErrorType.GUARDRAIL_VIOLATION.value
    assert res["repair_hint"] is not None
