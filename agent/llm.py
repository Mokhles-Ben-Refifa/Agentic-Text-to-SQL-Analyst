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
            raw_text = getattr(last_msg, "content", str(last_msg)).lower()
        else:
            raw_text = str(messages).lower()

        # Extract only the user business question if wrapped in prompt templates
        if "=== user business question ===" in raw_text:
            user_text = raw_text.split("=== user business question ===")[1].split("===")[0].strip()
        elif "user question:" in raw_text:
            user_text = raw_text.split("user question:")[1].strip()
        else:
            user_text = raw_text

        # Intent classification
        if hasattr(self, "_target_schema") and self._target_schema == IntentClassification:
            if any(k in user_text for k in ["client name", "client names", "list client names", "names of client"]):
                return IntentClassification(
                    category="out_of_scope",
                    refusal="Client names are not stored in the database for privacy and anonymization. Only client_id, gender, birth_date, and district_id exist.",
                )
            if any(k in user_text for k in ["next year", "predict", "prediction", "forecast"]):
                return IntentClassification(
                    category="out_of_scope",
                    refusal="Forecasting future metrics like next year's default rate requires predictive modeling and is outside the scope of historical SQL database queries.",
                )
            if any(k in user_text for k in ["ignore", "hack", "weather", "president", "poem", "drop the loan", "drop table"]):
                return IntentClassification(
                    category="out_of_scope",
                    refusal="I am a specialized SQL analyst and can only assist with querying database analytics.",
                )
            if any(k in user_text for k in ["best customer", "best customers", "show me the best"]):
                return IntentClassification(
                    category="ambiguous",
                    clarification="Could you clarify what you mean by 'best' customers? (e.g. highest account balance, highest transaction volume, longest tenure, or most loans?)",
                )
            if any(k in user_text for k in ["accounts are bad", "bad accounts", "which accounts are bad"]):
                return IntentClassification(
                    category="ambiguous",
                    clarification="Could you clarify what you mean by 'bad' accounts? (e.g. loans terminated in default (status B), loans currently delinquent in debt (status D), or accounts with negative balances?)",
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
            if "currently in debt" in user_text:
                return SQLGeneration(
                    reasoning="Loans currently in debt correspond to status 'D'.",
                    sql="SELECT COUNT(*) AS loans_in_debt FROM loan WHERE status = 'D'",
                )
            if "percentage" in user_text and ("without problem" in user_text or "finished" in user_text):
                return SQLGeneration(
                    reasoning="Status 'A' represents finished loans repaid without problems.",
                    sql="SELECT ROUND(CAST(SUM(CASE WHEN status = 'A' THEN 1 ELSE 0 END) AS REAL) * 100.0 / COUNT(*), 2) AS pct_finished_without_problems FROM loan",
                )
            if "weekly" in user_text:
                return SQLGeneration(
                    reasoning="Weekly statement frequency code is 'POPLATEK TYDNE'.",
                    sql="SELECT COUNT(*) AS weekly_statement_accounts FROM account WHERE frequency = 'POPLATEK TYDNE'",
                )
            if "highest average salary" in user_text:
                return SQLGeneration(
                    reasoning="Region is A3 and average salary is A11 in the district table.",
                    sql="SELECT A3 AS region, AVG(A11) AS avg_salary FROM district GROUP BY A3 ORDER BY avg_salary DESC LIMIT 1",
                )
            if "crimes in 1996" in user_text and "district" in user_text and "male" not in user_text:
                return SQLGeneration(
                    reasoning="1996 crimes column is A16; sort descending to get the top district.",
                    sql="SELECT A2 AS district_name, A16 AS crimes_1996 FROM district ORDER BY A16 DESC LIMIT 1",
                )
            if "male" in user_text and "1996" in user_text:
                return SQLGeneration(
                    reasoning="Filter male clients in the district with maximum 1996 crimes (A16).",
                    sql="SELECT COUNT(*) AS male_clients FROM client WHERE gender = 'M' AND district_id = (SELECT district_id FROM district ORDER BY A16 DESC LIMIT 1)",
                )
            if "total loan amount per region" in user_text:
                return SQLGeneration(
                    reasoning="Join loan -> account -> district, filter status='D' for loans in debt, group by region A3.",
                    sql="SELECT T3.A3 AS region, SUM(T1.amount) AS total_debt FROM loan AS T1 INNER JOIN account AS T2 ON T1.account_id = T2.account_id INNER JOIN district AS T3 ON T2.district_id = T3.district_id WHERE T1.status = 'D' GROUP BY T3.A3 ORDER BY total_debt DESC",
                )
            if "gold card" in user_text:
                return SQLGeneration(
                    reasoning="Join client -> disp -> card, filter card.type = 'gold'.",
                    sql="SELECT DISTINCT T1.gender, T1.birth_date FROM client AS T1 INNER JOIN disp AS T2 ON T1.client_id = T2.client_id INNER JOIN card AS T3 ON T2.disp_id = T3.disp_id WHERE T3.type = 'gold'",
                )
            if "running loan in debt" in user_text:
                return SQLGeneration(
                    reasoning="Filter disp.type='OWNER' and loan.status='D'.",
                    sql="SELECT DISTINCT T1.client_id FROM client AS T1 INNER JOIN disp AS T2 ON T1.client_id = T2.client_id INNER JOIN loan AS T3 ON T2.account_id = T3.account_id WHERE T2.type = 'OWNER' AND T3.status = 'D'",
                )
            if "distinct clients have a loan" in user_text or ("how many" in user_text and "clients have a loan" in user_text):
                return SQLGeneration(
                    reasoning="Join client -> disp -> loan with disp.type='OWNER' to prevent double counting disponents.",
                    sql="SELECT COUNT(DISTINCT T1.client_id) AS distinct_borrowers FROM client AS T1 INNER JOIN disp AS T2 ON T1.client_id = T2.client_id INNER JOIN loan AS T3 ON T2.account_id = T3.account_id WHERE T2.type = 'OWNER'",
                )
            if "average number of transactions per account" in user_text:
                return SQLGeneration(
                    reasoning="Aggregate transactions per account first to avoid fan-out duplication.",
                    sql="SELECT AVG(trans_count) AS avg_transactions FROM (SELECT T1.account_id, COUNT(T2.trans_id) AS trans_count FROM loan AS T1 LEFT JOIN trans AS T2 ON T1.account_id = T2.account_id GROUP BY T1.account_id)",
                )
            if "total loan amount per district" in user_text and "transactions" in user_text:
                return SQLGeneration(
                    reasoning="Use separate CTEs for loans and transactions to avoid Cartesian double-counting.",
                    sql="WITH district_loans AS (SELECT T2.district_id, SUM(T1.amount) AS total_loans FROM loan AS T1 JOIN account AS T2 ON T1.account_id = T2.account_id GROUP BY T2.district_id), district_trans AS (SELECT T2.district_id, COUNT(T1.trans_id) AS total_trans FROM trans AS T1 JOIN account AS T2 ON T1.account_id = T2.account_id GROUP BY T2.district_id) SELECT T1.district_id, T1.A2 AS district_name, COALESCE(T2.total_loans, 0) AS total_loans, COALESCE(T3.total_trans, 0) AS total_transactions FROM district AS T1 LEFT JOIN district_loans AS T2 ON T1.district_id = T2.district_id LEFT JOIN district_trans AS T3 ON T1.district_id = T3.district_id ORDER BY total_loans DESC",
                )
            if "opened in 1995" in user_text:
                return SQLGeneration(
                    reasoning="Filter accounts opened in 1995 using strftime.",
                    sql="SELECT COUNT(*) AS accounts_opened_1995 FROM account WHERE strftime('%Y', date) = '1995'",
                )
            if "withdrawals in 1997" in user_text:
                return SQLGeneration(
                    reasoning="Group withdrawals by month in 1997.",
                    sql="SELECT strftime('%m', date) AS month, SUM(amount) AS total_withdrawals FROM trans WHERE strftime('%Y', date) = '1997' AND type IN ('VYBER', 'VYDAJ') GROUP BY strftime('%m', date) ORDER BY month ASC",
                )
            if "days between account opening and loan date" in user_text:
                return SQLGeneration(
                    reasoning="Calculate average date difference using julianday for status 'D'.",
                    sql="SELECT AVG(julianday(T1.date) - julianday(T2.date)) AS avg_days FROM loan AS T1 JOIN account AS T2 ON T1.account_id = T2.account_id WHERE T1.status = 'D'",
                )
            if "top 3 districts by average loan amount" in user_text:
                return SQLGeneration(
                    reasoning="Rank districts by average loan amount using RANK() window function.",
                    sql="SELECT T3.A2 AS district_name, ROUND(AVG(T1.amount), 2) AS avg_amount, RANK() OVER (ORDER BY AVG(T1.amount) DESC) AS rank FROM loan AS T1 JOIN account AS T2 ON T1.account_id = T2.account_id JOIN district AS T3 ON T2.district_id = T3.district_id GROUP BY T3.district_id, T3.A2 ORDER BY avg_amount DESC LIMIT 3",
                )
            if "over 50 when they took their loan" in user_text:
                return SQLGeneration(
                    reasoning="Filter borrowers aged 50 or older on their loan approval date.",
                    sql="SELECT DISTINCT T1.client_id, T1.birth_date, T3.date AS loan_date FROM client AS T1 JOIN disp AS T2 ON T1.client_id = T2.client_id JOIN loan AS T3 ON T2.account_id = T3.account_id WHERE T2.type = 'OWNER' AND ((julianday(T3.date) - julianday(T1.birth_date)) / 365.25) >= 50",
                )
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
