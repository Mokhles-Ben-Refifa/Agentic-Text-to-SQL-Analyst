"""LangGraph StateGraph assembly for the Agentic Text-to-SQL Analyst."""

import logging
from typing import Any, Literal

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from agent.nodes import (
    answer_node,
    clarify_node,
    classify_node,
    execute_node,
    generate_sql_node,
    human_approval_node,
    refusal_node,
    repair_node,
    retrieve_schema_node,
    validate_node,
)
from agent.state import AgentState

logger = logging.getLogger(__name__)


# ==============================================================================
# Conditional Routing Functions
# ==============================================================================
def route_intent(state: AgentState) -> Literal["retrieve_schema", "clarify", "refusal"]:
    """Routes based on intent classification category."""
    intent = state.get("intent", "answerable")
    if intent == "ambiguous":
        return "clarify"
    if intent == "out_of_scope":
        return "refusal"
    return "retrieve_schema"


def route_validation(state: AgentState) -> Literal["repair", "human_approval", "execute", "answer"]:
    """Routes based on validation success, error count, and approval requirements."""
    has_error = state.get("validation_error") is not None
    attempts = state.get("attempts", 1)
    max_attempts = state.get("max_attempts", 3)

    if has_error:
        if attempts < max_attempts:
            return "repair"
        return "answer"

    if state.get("needs_approval"):
        return "human_approval"

    return "execute"


def route_approval(state: AgentState) -> Literal["execute", "refusal"]:
    """Routes based on human reviewer approval."""
    if state.get("is_approved"):
        return "execute"
    return "refusal"


def route_execution(state: AgentState) -> Literal["repair", "answer"]:
    """Routes after query execution: checks if DB error occurred."""
    has_error = state.get("validation_error") is not None
    attempts = state.get("attempts", 1)
    max_attempts = state.get("max_attempts", 3)

    if has_error and attempts < max_attempts:
        return "repair"
    return "answer"


# ==============================================================================
# Graph Construction & Compilation
# ==============================================================================
def create_text2sql_graph(checkpointer: BaseCheckpointSaver | None = None) -> Any:
    """Builds and compiles the full LangGraph workflow for the Text-to-SQL Agent."""
    workflow = StateGraph(AgentState)

    # Add Nodes
    workflow.add_node("classify", classify_node)
    workflow.add_node("clarify", clarify_node)
    workflow.add_node("refusal", refusal_node)
    workflow.add_node("retrieve_schema", retrieve_schema_node)
    workflow.add_node("generate_sql", generate_sql_node)
    workflow.add_node("validate", validate_node)
    workflow.add_node("human_approval", human_approval_node)
    workflow.add_node("execute", execute_node)
    workflow.add_node("repair", repair_node)
    workflow.add_node("answer", answer_node)

    # Add Edges & Conditional Routing
    workflow.add_edge(START, "classify")

    workflow.add_conditional_edges(
        "classify",
        route_intent,
        {
            "retrieve_schema": "retrieve_schema",
            "clarify": "clarify",
            "refusal": "refusal",
        },
    )

    workflow.add_edge("clarify", END)
    workflow.add_edge("refusal", END)

    workflow.add_edge("retrieve_schema", "generate_sql")
    workflow.add_edge("generate_sql", "validate")

    workflow.add_conditional_edges(
        "validate",
        route_validation,
        {
            "repair": "repair",
            "human_approval": "human_approval",
            "execute": "execute",
            "answer": "answer",
        },
    )

    workflow.add_conditional_edges(
        "human_approval",
        route_approval,
        {
            "execute": "execute",
            "refusal": "refusal",
        },
    )

    workflow.add_conditional_edges(
        "execute",
        route_execution,
        {
            "repair": "repair",
            "answer": "answer",
        },
    )

    # Self-repair loop: repaired query is fed back into validation
    workflow.add_edge("repair", "validate")

    workflow.add_edge("answer", END)

    saver = checkpointer or MemorySaver()
    return workflow.compile(checkpointer=saver)


sql_agent = create_text2sql_graph()
