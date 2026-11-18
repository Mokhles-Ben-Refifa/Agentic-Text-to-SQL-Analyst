"""FastMCP Server exposing database tools and defense-in-depth SQL guardrails."""

import logging
from typing import Any

from fastmcp import FastMCP

from data.database import db_manager
from mcp_server.guardrails import guardrail_engine
from mcp_server.models import CostEstimate, ErrorType, QueryExecutionResult, ValidationResult
from semantic.manager import semantic_manager

logger = logging.getLogger(__name__)

# Initialize FastMCP Server
mcp = FastMCP(
    name="Safe-Text2SQL-Server",
)


@mcp.tool()
def list_tables(db_target: str | None = None) -> list[str]:
    """Lists available database tables, excluding internal audit and system tables."""
    raw_tables = db_manager.get_table_names(sqlite_path=db_target)
    allowed = [t for t in raw_tables if t.lower() not in guardrail_engine.forbidden_tables]
    return sorted(allowed)


@mcp.tool()
def describe_table(table_name: str, db_target: str | None = None) -> dict[str, Any]:
    """Retrieves schema details: column names, data types, primary keys, foreign keys, and business context."""
    if table_name.lower() in guardrail_engine.forbidden_tables:
        return {
            "error": f"Access to table '{table_name}' is forbidden.",
            "error_type": ErrorType.FORBIDDEN_TABLE.value,
        }

    schema = db_manager.get_schema_metadata(sqlite_path=db_target, tables=[table_name])
    table_meta = schema.get(table_name, {})

    # Enrich with semantic layer metadata if available
    semantic_tbl = semantic_manager.get_table(table_name)
    if semantic_tbl:
        table_meta["description"] = semantic_tbl.description
        table_meta["domain_notes"] = semantic_tbl.domain_notes
        for col in table_meta.get("columns", []):
            sem_col = next((c for c in semantic_tbl.columns if c.name == col["name"]), None)
            if sem_col:
                col["business_meaning"] = sem_col.business_meaning
                col["sample_values"] = sem_col.sample_values

    return table_meta


@mcp.tool()
def validate_sql(
    sql: str,
    dialect: str = "postgres",
    allowed_tables: list[str] | None = None,
) -> dict[str, Any]:
    """Parses and validates a query at the AST level without executing it.

    Enforces SELECT-only, single statement, table allowlist, PII masking, and forced LIMIT.
    """
    result: ValidationResult = guardrail_engine.validate_and_sanitize(
        sql=sql,
        dialect=dialect,
        allowed_tables=allowed_tables,
    )
    return result.model_dump()


@mcp.tool()
def explain_query(
    sql: str,
    dialect: str = "postgres",
    db_target: str | None = None,
    cost_threshold: float = 50000.0,
    row_threshold: int = 100000,
) -> dict[str, Any]:
    """Computes execution plan and cost estimates from EXPLAIN to detect expensive queries."""
    val = guardrail_engine.validate_and_sanitize(sql=sql, dialect=dialect)
    if not val.is_valid:
        return {
            "is_valid": False,
            "error_type": val.error_type.value if val.error_type else ErrorType.SYNTAX_ERROR.value,
            "error_message": val.error_message,
            "repair_hint": val.repair_hint,
        }

    plan_result = db_manager.explain_query(sql=val.sanitized_sql or sql, sqlite_path=db_target)
    cost = plan_result.get("total_cost")
    rows = plan_result.get("plan_rows")
    has_full_scan = plan_result.get("has_full_table_scan", False)

    needs_approval = False
    reason = None

    if cost is not None and cost > cost_threshold:
        needs_approval = True
        reason = f"Estimated query cost ({cost:,.0f}) exceeds threshold ({cost_threshold:,.0f})."
    elif rows is not None and rows > row_threshold:
        needs_approval = True
        reason = f"Estimated row scan ({rows:,}) exceeds threshold ({row_threshold:,})."
    elif has_full_scan and dialect.lower() == "sqlite" and plan_result.get("scan_count", 0) > 3:
        needs_approval = True
        reason = "Multiple full table scans detected in execution plan."

    estimate = CostEstimate(
        dialect=plan_result.get("dialect", dialect),
        estimated_cost=cost,
        estimated_rows=rows,
        needs_approval=needs_approval,
        approval_reason=reason,
        raw_plan=plan_result,
    )
    return estimate.model_dump()


@mcp.tool()
def run_readonly_query(
    sql: str,
    dialect: str = "postgres",
    db_target: str | None = None,
    bypass_cost_check: bool = False,
    cost_threshold: float = 50000.0,
) -> dict[str, Any]:
    """Safely executes a read-only query under full defense-in-depth guardrails.

    Applies AST validation, forced LIMIT, cost gating, and read-only DB permissions.
    Returns structured results or categorized errors with actionable self-repair hints.
    """
    # 1. AST Validation & Sanitization
    val = guardrail_engine.validate_and_sanitize(sql=sql, dialect=dialect)
    if not val.is_valid:
        return QueryExecutionResult(
            success=False,
            error_type=val.error_type,
            error_message=val.error_message,
            repair_hint=val.repair_hint,
            executed_sql=sql,
        ).model_dump()

    sanitized_sql = val.sanitized_sql or sql

    # 2. Cost / Complexity Gate
    if not bypass_cost_check:
        plan = explain_query(
            sql=sanitized_sql, dialect=dialect, db_target=db_target, cost_threshold=cost_threshold
        )
        if plan.get("needs_approval"):
            return QueryExecutionResult(
                success=False,
                requires_approval=True,
                error_type=ErrorType.APPROVAL_REQUIRED,
                error_message=f"Query paused for human approval: {plan.get('approval_reason')}",
                repair_hint="Request human approval or add index filters / partition predicates to reduce cost.",
                executed_sql=sanitized_sql,
            ).model_dump()

    # 3. Read-only Execution
    try:
        data = db_manager.execute_query(sql=sanitized_sql, is_admin=False, sqlite_path=db_target)
        return QueryExecutionResult(
            success=True,
            data=data,
            row_count=len(data),
            executed_sql=sanitized_sql,
        ).model_dump()
    except Exception as e:
        err_str = str(e)
        logger.error(f"Database query execution error: {err_str}")
        return QueryExecutionResult(
            success=False,
            error_type=ErrorType.DATABASE_ERROR,
            error_message=err_str,
            repair_hint="Review database error details and verify column/table names and joins.",
            executed_sql=sanitized_sql,
        ).model_dump()


if __name__ == "__main__":
    mcp.run()
