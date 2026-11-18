"""Streamlit Interactive Web Dashboard for the Agentic Text-to-SQL Analyst."""

import pandas as pd
import plotly.express as px
import streamlit as st

from agent.graph import sql_agent
from mcp_server.server import describe_table, list_tables

st.set_page_config(
    page_title="Text-to-SQL Analyst",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom Styling
st.markdown(
    """
    <style>
    .main-header { font-size: 2.2rem; font-weight: 700; color: #1E3A8A; margin-bottom: 0.2rem; }
    .sub-header { font-size: 1.05rem; color: #4B5563; margin-bottom: 1.5rem; }
    .step-box { background-color: #F3F4F6; border-radius: 8px; padding: 12px; margin-bottom: 8px; }
    </style>
    """,
    unsafe_allow_html=True,
)

# Initialize Session State
if "messages" not in st.session_state:
    st.session_state.messages = []
if "thread_id" not in st.session_state:
    st.session_state.thread_id = "streamlit_session_001"
if "pending_approval" not in st.session_state:
    st.session_state.pending_approval = None


# Sidebar: Database & Settings
with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/database.png", width=64)
    st.title("Settings & Schema")

    db_option = st.selectbox(
        "Select Target Database",
        [
            "BIRD Financial (Banking Demo)",
            "PostgreSQL (Docker Warehouse)",
            "Custom SQLite File",
        ],
    )

    if db_option == "BIRD Financial (Banking Demo)":
        db_target = "./data/benchmarks/bird/financial/financial.sqlite"
        dialect = "sqlite"
    elif db_option == "PostgreSQL (Docker Warehouse)":
        db_target = None
        dialect = "postgres"
    else:
        db_target = st.text_input(
            "SQLite File Path", value="./data/benchmarks/bird/financial/financial.sqlite"
        )
        dialect = "sqlite"

    # Schema Explorer
    with st.expander("📚 Explore Database Tables", expanded=False):
        try:
            tables = list_tables(db_target=db_target)
            st.write(f"**Found {len(tables)} tables:**")
            selected_tbl = st.selectbox("View Columns", tables)
            if selected_tbl:
                desc = describe_table(selected_tbl, db_target=db_target)
                if desc and "columns" in desc:
                    cols_df = pd.DataFrame(desc["columns"])
                    st.dataframe(
                        cols_df[["name", "type"]], hide_index=True, use_container_width=True
                    )
        except Exception as e:
            st.warning(f"Could not inspect database: {e}")

    # Verified Sample Prompts
    st.subheader("💡 Sample Questions")
    sample_queries = [
        "What is the average loan amount for each loan status?",
        "Which district has the highest average salary?",
        "How many accounts have monthly statement fees?",
        "List the top 5 largest loans and their duration in months.",
        "What is the total number of deposits vs withdrawals in transactions?",
    ]
    for q in sample_queries:
        if st.button(q, key=f"btn_{q}"):
            st.session_state.input_query = q


# Main Header
st.markdown('<div class="main-header">🤖 Agentic Text-to-SQL Analyst</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-header">Safe, evaluated, self-correcting AI analyst powered by LangGraph, FastMCP, and AST guardrails.</div>',
    unsafe_allow_html=True,
)

# Display Chat History
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"], unsafe_allow_html=True)
        if msg.get("df") is not None:
            st.dataframe(msg["df"], use_container_width=True)
        if msg.get("chart") is not None:
            st.plotly_chart(msg["chart"], use_container_width=True)


# Render Auto Plotly Chart
def render_chart(df: pd.DataFrame, chart_type: str):
    if df.empty or len(df.columns) < 2 or chart_type == "none":
        return None

    cols = list(df.columns)
    # Detect numeric columns
    numeric_cols = [c for c in cols if pd.api.types.is_numeric_dtype(df[c])]
    categorical_cols = [c for c in cols if c not in numeric_cols]

    if not numeric_cols:
        return None

    y_col = numeric_cols[0]
    x_col = categorical_cols[0] if categorical_cols else cols[0]

    try:
        if chart_type == "line" or "date" in str(x_col).lower():
            fig = px.line(
                df,
                x=x_col,
                y=y_col,
                title=f"{y_col.replace('_', ' ').title()} over {x_col}",
                markers=True,
            )
        else:
            fig = px.bar(
                df,
                x=x_col,
                y=y_col,
                title=f"{y_col.replace('_', ' ').title()} by {x_col}",
                color=x_col,
            )
        fig.update_layout(template="plotly_white", margin={"l": 20, "r": 20, "t": 40, "b": 20})
        return fig
    except Exception:
        return None


# Input Query Processing
user_query = st.chat_input("Ask a business question in plain language...")
if "input_query" in st.session_state and st.session_state.input_query:
    user_query = st.session_state.input_query
    st.session_state.input_query = None

if user_query:
    # Append user question
    st.session_state.messages.append({"role": "user", "content": user_query})
    with st.chat_message("user"):
        st.write(user_query)

    # Agent Execution Container
    with st.chat_message("assistant"):
        step_container = st.status("🧠 Agent reasoning and execution...", expanded=True)

        config = {"configurable": {"thread_id": st.session_state.thread_id}}
        initial_state = {
            "question": user_query,
            "dialect": dialect,
            "db_target": db_target,
            "max_attempts": 3,
        }

        # Stream node updates
        final_state = {}
        for step in sql_agent.stream(initial_state, config=config, stream_mode="updates"):
            for node_name, node_output in step.items():
                if node_name == "classify":
                    step_container.write(f"🎯 **Intent Classified:** `{node_output.get('intent')}`")
                elif node_name == "retrieve_schema":
                    step_container.write(
                        f"📚 **Schema RAG:** Retrieved {len(node_output.get('retrieved_tables', []))} tables with FK expansion."
                    )
                elif node_name == "generate_sql":
                    step_container.write(
                        "✍️ **SQL Generated:** Synthesized structured query with reasoning plan."
                    )
                elif node_name == "validate":
                    if node_output.get("validation_error"):
                        step_container.write(
                            f"⚠️ **Validation Failed:** `{node_output.get('validation_error')}`"
                        )
                    else:
                        step_container.write(
                            "🛡️ **FastMCP Guardrails:** Passed AST check, forced LIMIT & cost estimate."
                        )
                elif node_name == "repair":
                    step_container.write(
                        "🔧 **Self-Repair Loop:** Fixed query based on FastMCP diagnostic error."
                    )
                elif node_name == "execute":
                    step_container.write(
                        f"⚡ **Query Executed:** Fetched {node_output.get('row_count', 0)} rows securely."
                    )
                elif node_name == "answer":
                    step_container.write("📊 **Answer Ready:** Synthesized business summary.")
                final_state.update(node_output)

        step_container.update(label="Execution complete!", state="complete", expanded=False)

        # Process Results
        answer_text = final_state.get("answer", "No answer generated.")
        st.markdown(answer_text, unsafe_allow_html=True)

        result_df = None
        data = final_state.get("result_data")
        if data:
            result_df = pd.DataFrame(data)
            st.dataframe(result_df, use_container_width=True)

        chart_fig = None
        if result_df is not None and not result_df.empty:
            chart_fig = render_chart(result_df, final_state.get("suggested_chart", "bar"))
            if chart_fig:
                st.plotly_chart(chart_fig, use_container_width=True)

        # Store in session messages
        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": answer_text,
                "df": result_df,
                "chart": chart_fig,
            }
        )
