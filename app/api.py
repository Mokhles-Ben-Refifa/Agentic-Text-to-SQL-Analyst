"""FastAPI Server exposing Text-to-SQL Agent query execution and streaming endpoints."""

import sys
from pathlib import Path

# Ensure project root is in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import json
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agent.graph import sql_agent
from agent.observability import get_langfuse_callback
from mcp_server.server import describe_table, list_tables

app = FastAPI(
    title="Agentic Text-to-SQL Analyst API",
    description="Production-grade LangGraph and FastMCP SQL Analyst API with guardrails and self-repair.",
    version="1.0.0",
)

# Enable CORS for Streamlit and web frontends
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class QueryRequest(BaseModel):
    question: str = Field(description="Natural language business question.")
    dialect: str = Field(
        default="sqlite", description="Target SQL dialect: 'sqlite' or 'postgres'."
    )
    db_target: str | None = Field(
        default="./data/benchmarks/bird/financial/financial.sqlite",
        description="Path to SQLite database or None for default PostgreSQL.",
    )
    thread_id: str | None = Field(
        default=None,
        description="Conversation thread ID for stateful checkpointer memory.",
    )


class QueryResponse(BaseModel):
    thread_id: str
    intent: str
    question: str
    sql: str
    answer: str
    row_count: int
    result_data: list[dict[str, Any]] | None
    suggested_chart: str | None
    needs_approval: bool
    approval_reason: str | None


class ApprovalRequest(BaseModel):
    thread_id: str
    approved: bool
    reason: str | None = None


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "healthy", "service": "sql-agent-api"}


@app.get("/api/tables")
def get_tables(db_target: str | None = None) -> list[str]:
    """Returns available allowed tables."""
    return list_tables(db_target=db_target)


@app.get("/api/tables/{name}")
def get_table_details(name: str, db_target: str | None = None) -> dict[str, Any]:
    """Retrieves schema and semantic details for a specific table."""
    details = describe_table(table_name=name, db_target=db_target)
    if "error" in details:
        raise HTTPException(status_code=403, detail=details["error"])
    return details


@app.post("/api/query", response_model=QueryResponse)
def execute_query(req: QueryRequest) -> QueryResponse:
    """Synchronous execution of a business question through the LangGraph agent."""
    thread_id = req.thread_id or f"thread_{uuid.uuid4().hex[:8]}"
    config: dict[str, Any] = {"configurable": {"thread_id": thread_id}}

    langfuse_handler = get_langfuse_callback()
    if langfuse_handler:
        config["callbacks"] = [langfuse_handler]

    initial_state = {
        "question": req.question,
        "dialect": req.dialect,
        "db_target": req.db_target,
        "max_attempts": 3,
    }

    try:
        final_state = sql_agent.invoke(initial_state, config=config)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent execution failed: {str(e)}") from e

    return QueryResponse(
        thread_id=thread_id,
        intent=final_state.get("intent", "answerable"),
        question=req.question,
        sql=final_state.get("sql", ""),
        answer=final_state.get("answer", ""),
        row_count=final_state.get("row_count", 0),
        result_data=final_state.get("result_data"),
        suggested_chart=final_state.get("suggested_chart"),
        needs_approval=final_state.get("needs_approval", False),
        approval_reason=final_state.get("approval_reason"),
    )


@app.post("/api/query/stream")
async def stream_query(req: QueryRequest) -> StreamingResponse:
    """Server-Sent Events (SSE) streaming live step-by-step agent progress."""
    thread_id = req.thread_id or f"thread_{uuid.uuid4().hex[:8]}"

    async def event_generator() -> AsyncGenerator[str, None]:
        config = {"configurable": {"thread_id": thread_id}}
        initial_state = {
            "question": req.question,
            "dialect": req.dialect,
            "db_target": req.db_target,
            "max_attempts": 3,
        }

        yield f"data: {json.dumps({'step': 'started', 'thread_id': thread_id})}\n\n"

        for step in sql_agent.stream(initial_state, config=config, stream_mode="updates"):
            for node_name, node_output in step.items():
                event_payload = {
                    "step": node_name,
                    "sql": node_output.get("sql"),
                    "intent": node_output.get("intent"),
                    "answer": node_output.get("answer"),
                    "needs_approval": node_output.get("needs_approval"),
                }
                yield f"data: {json.dumps(event_payload)}\n\n"

        yield f"data: {json.dumps({'step': 'completed', 'thread_id': thread_id})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/api/approval")
def submit_approval(req: ApprovalRequest) -> dict[str, Any]:
    """Submits human review decision to resume an interrupted high-cost query."""
    config = {"configurable": {"thread_id": req.thread_id}}
    approval_decision = {"status": "approved" if req.approved else "rejected", "reason": req.reason}

    # Resume graph execution with approval decision
    try:
        resumed_state = sql_agent.invoke(approval_decision, config=config)
        return {
            "success": True,
            "thread_id": req.thread_id,
            "answer": resumed_state.get("answer"),
            "sql": resumed_state.get("sql"),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to resume execution: {str(e)}") from e
