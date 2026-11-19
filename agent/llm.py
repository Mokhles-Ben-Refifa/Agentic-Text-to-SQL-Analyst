"""LLM Model Provider and Mock Factory for the SQL Agent."""

import os
from typing import Any
from dotenv import load_dotenv

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from pydantic import BaseModel

from agent.state import FinalAnswer, IntentClassification, SQLGeneration, SQLRepair

load_dotenv()


class MockStructuredChatModel:
    """Mock LLM capable of returning valid Pydantic structured outputs for testing and CI."""

    def __init__(self, model_name: str = "mock-llm"):
        self.model_name = model_name

    def with_structured_output(
        self, schema: type[BaseModel], **_kwargs: Any
    ) -> "MockStructuredChatModel":
        self._target_schema = schema
        return self

    def invoke(self, messages: list[BaseMessage] | str, **_kwargs: Any) -> Any:
        if isinstance(messages, list) and len(messages) > 0:
            last_msg = messages[-1]
            user_text = getattr(last_msg, "content", str(last_msg)).lower()
        else:
            user_text = str(messages).lower()

        # Intent classification
        if hasattr(self, "_target_schema") and self._target_schema == IntentClassification:
            if any(k in user_text for k in ["ignore", "hack", "weather", "president", "poem"]):
                return IntentClassification(
                    category="out_of_scope",
                    refusal="I am a specialized SQL analyst and can only assist with querying database analytics.",
                )
            if any(
                k in user_text for k in ["check that", "is it good", "vague", "show me the good"]
            ):
                return IntentClassification(
                    category="ambiguous",
                    clarification="Could you please specify which accounts, loans, or metrics you would like to analyze?",
                )
            return IntentClassification(category="answerable")

        # SQL Generation
        if hasattr(self, "_target_schema") and self._target_schema == SQLGeneration:
            if "loan" in user_text or "status" in user_text:
                return SQLGeneration(
                    reasoning="Query loans and compute average amount grouped by status.",
                    sql="SELECT status, AVG(amount) AS avg_amount FROM loan GROUP BY status",
                )
            if "client" in user_text and "prague" in user_text:
                return SQLGeneration(
                    reasoning="Join client with disp, loan, and district to find clients in Prague.",
                    sql=(
                        "SELECT T1.client_id, T1.gender FROM client AS T1 "
                        "INNER JOIN district AS T2 ON T1.district_id = T2.district_id "
                        "WHERE T2.A2 = 'Hl.m. Praha'"
                    ),
                )
            return SQLGeneration(
                reasoning="Select accounts order by date.",
                sql="SELECT account_id, frequency, date FROM account ORDER BY date DESC",
            )

        # SQL Repair
        if hasattr(self, "_target_schema") and self._target_schema == SQLRepair:
            return SQLRepair(
                explanation="Removed forbidden table and corrected join condition to allowed table 'loan'.",
                fixed_sql="SELECT loan_id, amount, status FROM loan",
            )

        # Final Answer Synthesis
        if hasattr(self, "_target_schema") and self._target_schema == FinalAnswer:
            return FinalAnswer(
                summary="The analysis returned the requested records from the database successfully.",
                chart_type="bar",
                markdown_table="| status | avg_amount |\n|---|---|\n| A | 80952 |\n| B | 30276 |",
            )

        return AIMessage(content="Analysis complete.")


def get_llm(
    model_name: str | None = None,
    temperature: float = 0.0,
    force_mock: bool = False,
) -> BaseChatModel | MockStructuredChatModel:
    """Returns a configured LangChain chat model or mock model."""
    if force_mock or os.getenv("FORCE_MOCK_LLM", "").lower() in ["true", "1", "yes"]:
        return MockStructuredChatModel()

    gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")

    if gemini_key and not gemini_key.startswith("your_"):
        from langchain_google_genai import ChatGoogleGenerativeAI

        target_model = model_name or os.getenv("DEFAULT_MODEL", "gemini-3.5-flash-lite")
        return ChatGoogleGenerativeAI(
            model=target_model,
            google_api_key=gemini_key,
            temperature=temperature,
        )

    if openai_key and not openai_key.startswith("your_"):
        from langchain_openai import ChatOpenAI

        target_model = model_name or os.getenv("DEFAULT_MODEL", "gpt-4o-mini")
        return ChatOpenAI(model=target_model, temperature=temperature)

    if anthropic_key and not anthropic_key.startswith("your_"):
        from langchain_anthropic import ChatAnthropic

        target_model = model_name or "claude-3-5-sonnet-20241022"
        return ChatAnthropic(model=target_model, temperature=temperature)

    # Deterministic fallback when no live keys are configured
    return MockStructuredChatModel()
