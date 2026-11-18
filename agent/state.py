"""State definitions and structured output schemas for the LangGraph SQL Agent."""

from typing import Any, Literal

from pydantic import BaseModel, Field
from typing_extensions import TypedDict


# ==============================================================================
# Pydantic Structured Output Schemas
# ==============================================================================
class IntentClassification(BaseModel):
    """Structured intent classification for the incoming question."""

    category: Literal["answerable", "ambiguous", "out_of_scope"] = Field(
        description="Category: 'answerable' for database questions, 'ambiguous' for vague queries, 'out_of_scope' for non-data requests."
    )
    clarification: str | None = Field(
        default=None,
        description="Clarifying question if category is ambiguous.",
    )
    refusal: str | None = Field(
        default=None,
        description="Polite refusal message if category is out_of_scope.",
    )


class SQLGeneration(BaseModel):
    """Structured output for SQL generation."""

    reasoning: str = Field(description="Step-by-step reasoning plan (tables, joins, filters).")
    sql: str = Field(description="Single clean SELECT SQL query.")


class SQLRepair(BaseModel):
    """Structured output for SQL self-repair."""

    explanation: str = Field(description="Brief explanation of what was fixed and why.")
    fixed_sql: str = Field(description="The corrected single SELECT SQL query.")


class FinalAnswer(BaseModel):
    """Structured final answer synthesis."""

    summary: str = Field(description="Executive business summary answering the user's question.")
    chart_type: Literal["bar", "line", "scatter", "none"] = Field(
        default="none",
        description="Recommended chart type: 'bar' for categories, 'line' for time-series, 'none' otherwise.",
    )
    markdown_table: str | None = Field(
        default=None,
        description="Formatted markdown table of the top result rows.",
    )


# ==============================================================================
# LangGraph Agent State
# ==============================================================================
class AgentState(TypedDict, total=False):
    """State tracked across all nodes in the LangGraph Text-to-SQL graph."""

    question: str
    dialect: str
    db_target: str | None

    # Intent routing
    intent: Literal["answerable", "ambiguous", "out_of_scope"]
    clarification_message: str | None
    refusal_message: str | None

    # Schema RAG context
    retrieved_schema: str
    retrieved_tables: list[str]

    # SQL generation & validation
    sql: str
    sql_reasoning: str
    validation_error: str | None
    error_type: str | None
    repair_hint: str | None

    # Human-in-the-loop approval
    needs_approval: bool
    approval_reason: str | None
    is_approved: bool

    # Execution & self-correction loop
    result_data: list[dict[str, Any]] | None
    row_count: int
    attempts: int
    max_attempts: int

    # Final response
    answer: str
    suggested_chart: str | None
