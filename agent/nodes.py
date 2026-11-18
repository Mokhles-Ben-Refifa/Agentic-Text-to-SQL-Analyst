"""LangGraph Nodes for Intent Classification, RAG, Generation, Validation, Approval, Execution, and Repair."""

import logging
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import interrupt

from agent.llm import get_llm
from agent.retrieval.retriever import schema_retriever
from agent.state import AgentState, FinalAnswer, IntentClassification, SQLGeneration, SQLRepair
from mcp_server.server import explain_query, run_readonly_query, validate_sql

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"


def load_prompt(name: str) -> str:
    path = PROMPTS_DIR / f"{name}.txt"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


# ==============================================================================
# Node 1: Classify Intent
# ==============================================================================
def classify_node(state: AgentState) -> dict[str, Any]:
    """Classifies user intent as answerable, ambiguous, or out_of_scope."""
    question = state.get("question", "")
    system_prompt = load_prompt("classify")

    llm = get_llm()
    structured_llm = llm.with_structured_output(IntentClassification)

    result: IntentClassification = structured_llm.invoke(
        [
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"User question: {question}"),
        ]
    )

    return {
        "intent": result.category,
        "clarification_message": result.clarification,
        "refusal_message": result.refusal,
    }


# ==============================================================================
# Node 2: Clarify & Refusal Nodes
# ==============================================================================
def clarify_node(state: AgentState) -> dict[str, Any]:
    msg = state.get("clarification_message") or "Could you please clarify your question?"
    return {"answer": f"**Clarification needed:** {msg}"}


def refusal_node(state: AgentState) -> dict[str, Any]:
    msg = (
        state.get("refusal_message")
        or "I am specialized strictly in SQL data analytics and cannot assist with this request."
    )
    return {"answer": f"**Notice:** {msg}"}


# ==============================================================================
# Node 3: Retrieve Schema (RAG)
# ==============================================================================
def retrieve_schema_node(state: AgentState) -> dict[str, Any]:
    """Runs hybrid retrieval and FK expansion for the user question."""
    question = state.get("question", "")
    retrieval_res = schema_retriever.retrieve(question)

    return {
        "retrieved_schema": retrieval_res.formatted_context,
        "retrieved_tables": retrieval_res.expanded_tables,
    }


# ==============================================================================
# Node 4: Generate SQL
# ==============================================================================
def generate_sql_node(state: AgentState) -> dict[str, Any]:
    """Generates a structured SQL query conforming to retrieved schema and glossary."""
    question = state.get("question", "")
    dialect = state.get("dialect", "postgres")
    schema_context = state.get("retrieved_schema", "")

    system_prompt = load_prompt("generate_sql").replace("{dialect}", dialect)
    user_prompt = (
        f"{schema_context}\n\n"
        f"=== USER BUSINESS QUESTION ===\n{question}\n\n"
        f"Write an accurate {dialect} SELECT query answering the question."
    )

    llm = get_llm()
    structured_llm = llm.with_structured_output(SQLGeneration)

    res: SQLGeneration = structured_llm.invoke(
        [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
    )

    return {
        "sql": res.sql.strip(),
        "sql_reasoning": res.reasoning,
        "attempts": state.get("attempts", 0) + 1,
    }


# ==============================================================================
# Node 5: Validate SQL via FastMCP
# ==============================================================================
def validate_node(state: AgentState) -> dict[str, Any]:
    """Validates SQL via AST-level guardrails and checks EXPLAIN query cost."""
    sql = state.get("sql", "")
    dialect = state.get("dialect", "postgres")
    db_target = state.get("db_target")

    # 1. AST Validation
    val_res = validate_sql(sql=sql, dialect=dialect)
    if not val_res.get("is_valid"):
        return {
            "validation_error": val_res.get("error_message"),
            "error_type": val_res.get("error_type"),
            "repair_hint": val_res.get("repair_hint"),
            "needs_approval": False,
        }

    sanitized_sql = val_res.get("sanitized_sql") or sql

    # 2. Cost / Complexity Gate via EXPLAIN
    plan_res = explain_query(sql=sanitized_sql, dialect=dialect, db_target=db_target)
    if plan_res.get("needs_approval"):
        return {
            "sql": sanitized_sql,
            "validation_error": None,
            "needs_approval": True,
            "approval_reason": plan_res.get("approval_reason"),
        }

    return {
        "sql": sanitized_sql,
        "validation_error": None,
        "needs_approval": False,
    }


# ==============================================================================
# Node 6: Human Approval (LangGraph Interrupt)
# ==============================================================================
def human_approval_node(state: AgentState) -> dict[str, Any]:
    """Pauses graph execution for human approval on high-cost or sensitive queries."""
    sql = state.get("sql", "")
    reason = state.get("approval_reason", "High execution cost detected.")

    decision = interrupt(
        {
            "action": "human_approval_required",
            "sql": sql,
            "reason": reason,
            "prompt": "Approve, edit, or reject this query execution.",
        }
    )

    # Decision payload: {"status": "approved"} or {"status": "rejected"}
    if isinstance(decision, dict) and decision.get("status") == "approved":
        return {"is_approved": True, "needs_approval": False}
    else:
        return {
            "is_approved": False,
            "needs_approval": False,
            "refusal_message": f"Query execution was rejected by human operator. (Reason: {reason})",
        }


# ==============================================================================
# Node 7: Execute Read-Only Query
# ==============================================================================
def execute_node(state: AgentState) -> dict[str, Any]:
    """Safely executes the query through the FastMCP server."""
    sql = state.get("sql", "")
    dialect = state.get("dialect", "postgres")
    db_target = state.get("db_target")

    res = run_readonly_query(
        sql=sql,
        dialect=dialect,
        db_target=db_target,
        bypass_cost_check=True,  # Cost already reviewed/approved
    )

    if res.get("success"):
        return {
            "result_data": res.get("data", []),
            "row_count": res.get("row_count", 0),
            "validation_error": None,
        }
    else:
        return {
            "validation_error": res.get("error_message"),
            "error_type": res.get("error_type"),
            "repair_hint": res.get("repair_hint"),
        }


# ==============================================================================
# Node 8: Self-Repair Loop
# ==============================================================================
def repair_node(state: AgentState) -> dict[str, Any]:
    """Generates a surgically corrected SQL query based on the exact error message."""
    failed_sql = state.get("sql", "")
    error_type = state.get("error_type", "UNKNOWN_ERROR")
    error_msg = state.get("validation_error", "")
    repair_hint = state.get("repair_hint", "")
    schema_context = state.get("retrieved_schema", "")

    system_prompt = load_prompt("repair")
    user_prompt = (
        f"=== FAILED SQL QUERY ===\n{failed_sql}\n\n"
        f"=== ERROR DIAGNOSTIC ===\nError Type: {error_type}\nError Message: {error_msg}\nRepair Hint: {repair_hint}\n\n"
        f"=== AVAILABLE SCHEMA CONTEXT ===\n{schema_context}\n\n"
        f"Provide the corrected single SELECT SQL query."
    )

    llm = get_llm()
    structured_llm = llm.with_structured_output(SQLRepair)

    res: SQLRepair = structured_llm.invoke(
        [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
    )

    return {
        "sql": res.fixed_sql.strip(),
        "sql_reasoning": f"Self-repair: {res.explanation}",
        "validation_error": None,
    }


# ==============================================================================
# Node 9: Synthesize Answer
# ==============================================================================
def answer_node(state: AgentState) -> dict[str, Any]:
    """Generates the final natural language summary and transparent SQL display."""
    validation_error = state.get("validation_error")
    attempts = state.get("attempts", 1)
    max_attempts = state.get("max_attempts", 3)

    # 1. Honest failure handling if repair attempts exhausted
    if validation_error and attempts >= max_attempts:
        err_type = state.get("error_type", "Execution Error")
        failed_sql = state.get("sql", "")
        answer = (
            f"❌ **Unable to answer query after {attempts} attempts.**\n\n"
            f"**Error Category:** `{err_type}`\n"
            f"**Diagnostic Details:** {validation_error}\n\n"
            f"**Last Attempted SQL:**\n```sql\n{failed_sql}\n```"
        )
        return {"answer": answer, "suggested_chart": "none"}

    # 2. Success synthesis
    data = state.get("result_data", [])
    sql = state.get("sql", "")
    question = state.get("question", "")

    if not data:
        answer = (
            f"The query executed successfully but returned **0 matching records**.\n\n"
            f"**Executed SQL:**\n```sql\n{sql}\n```"
        )
        return {"answer": answer, "suggested_chart": "none"}

    system_prompt = load_prompt("answer")
    user_prompt = (
        f"Question: {question}\n\n"
        f"Executed SQL: {sql}\n\n"
        f"Returned Rows (sample): {data[:10]}\n"
        f"Total Row Count: {len(data)}"
    )

    llm = get_llm()
    structured_llm = llm.with_structured_output(FinalAnswer)

    res: FinalAnswer = structured_llm.invoke(
        [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
    )

    # Format complete transparent Markdown response
    table_block = f"\n\n{res.markdown_table}" if res.markdown_table else ""
    full_response = (
        f"{res.summary}"
        f"{table_block}\n\n"
        f"<details>\n<summary><b>View Executed SQL</b></summary>\n\n```sql\n{sql}\n```\n</details>"
    )

    return {
        "answer": full_response,
        "suggested_chart": res.chart_type,
    }
