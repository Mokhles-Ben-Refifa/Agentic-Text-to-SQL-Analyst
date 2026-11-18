"""Tests for the Semantic Layer: table metadata, glossary, and few-shot examples."""

from semantic.manager import SemanticManager


def test_semantic_manager_loads_tables():
    manager = SemanticManager()
    tables = manager.list_tables()

    expected = ["account", "client", "disp", "district", "loan", "trans"]
    assert set(expected).issubset(set(tables))


def test_table_metadata_details():
    manager = SemanticManager()
    loan = manager.get_table("loan")
    assert loan is not None
    assert loan.name == "loan"
    assert "loan_id" in loan.primary_keys

    col_names = [c.name for c in loan.columns]
    assert "amount" in col_names
    assert "status" in col_names
    assert "account_id" in col_names

    # Check foreign key
    account_id_col = next(c for c in loan.columns if c.name == "account_id")
    assert account_id_col.foreign_key == "account.account_id"


def test_cryptic_columns_have_business_meanings():
    manager = SemanticManager()
    district = manager.get_table("district")
    assert district is not None

    a2_col = next(c for c in district.columns if c.name == "A2")
    assert a2_col.business_meaning is not None
    assert "District name" in a2_col.business_meaning

    a11_col = next(c for c in district.columns if c.name == "A11")
    assert a11_col.business_meaning is not None
    assert "salary" in a11_col.business_meaning.lower()


def test_glossary_terms():
    manager = SemanticManager()
    assert len(manager.glossary) >= 10

    terms = [g.term for g in manager.glossary]
    assert "Active Loan" in terms
    assert "Defaulted Loan" in terms
    assert "Prague District" in terms

    active_term = next(g for g in manager.glossary if g.term == "Active Loan")
    assert active_term.sql_expression == "loan.status = 'C'"


def test_few_shot_examples():
    manager = SemanticManager()
    assert len(manager.examples) >= 10

    # Overlap search for loan and account
    relevant = manager.get_relevant_examples(table_names=["loan", "account"], limit=3)
    assert len(relevant) == 3
    assert all(
        "loan" in [t.lower() for t in ex.tables_used]
        or "account" in [t.lower() for t in ex.tables_used]
        for ex in relevant
    )


def test_prompt_formatting():
    manager = SemanticManager()

    schema_block = manager.format_schema_for_prompt(["loan", "district"])
    assert "### Table: `loan`" in schema_block
    assert "### Table: `district`" in schema_block
    assert "[PRIMARY KEY]" in schema_block

    glossary_block = manager.format_glossary_for_prompt(["Active Loan"])
    assert "Active Loan" in glossary_block
    assert "loan.status = 'C'" in glossary_block

    examples = manager.get_relevant_examples(table_names=["loan"], limit=2)
    example_block = manager.format_examples_for_prompt(examples)
    assert "```sql" in example_block
    assert "SELECT" in example_block
