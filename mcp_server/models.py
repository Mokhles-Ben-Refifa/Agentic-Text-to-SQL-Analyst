"""Pydantic data models for MCP tool requests, responses, and structured errors."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ErrorType(StrEnum):
    SYNTAX_ERROR = "SYNTAX_ERROR"
    GUARDRAIL_VIOLATION = "GUARDRAIL_VIOLATION"
    FORBIDDEN_TABLE = "FORBIDDEN_TABLE"
    PII_VIOLATION = "PII_VIOLATION"
    PROHIBITED_FUNCTION = "PROHIBITED_FUNCTION"
    COST_EXCEEDED = "COST_EXCEEDED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    DATABASE_ERROR = "DATABASE_ERROR"


class GuardrailViolationError(Exception):
    """Exception raised when a query violates safety guardrails."""

    def __init__(self, error_type: ErrorType, message: str, repair_hint: str = ""):
        super().__init__(message)
        self.error_type = error_type
        self.message = message
        self.repair_hint = repair_hint


class ValidationResult(BaseModel):
    """Result of SQL AST validation and guardrail checks."""

    is_valid: bool
    sanitized_sql: str | None = None
    error_type: ErrorType | None = None
    error_message: str | None = None
    repair_hint: str | None = None
    tables_referenced: list[str] = Field(default_factory=list)
    has_forced_limit: bool = False
    original_limit: int | None = None
    enforced_limit: int | None = None


class CostEstimate(BaseModel):
    """Query execution cost estimate from EXPLAIN."""

    dialect: str
    estimated_cost: float | None = None
    estimated_rows: int | None = None
    needs_approval: bool = False
    approval_reason: str | None = None
    raw_plan: Any = None


class QueryExecutionResult(BaseModel):
    """Result of read-only query execution."""

    success: bool
    data: list[dict[str, Any]] = Field(default_factory=list)
    row_count: int = 0
    executed_sql: str = ""
    cost_estimate: CostEstimate | None = None
    error_type: ErrorType | None = None
    error_message: str | None = None
    repair_hint: str | None = None
    requires_approval: bool = False
