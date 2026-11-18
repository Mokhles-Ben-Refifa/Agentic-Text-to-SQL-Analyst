"""Tests for Hybrid Schema Retrieval, Foreign Key Expansion, and Prompt Formatting."""

from agent.retrieval.fk_expander import ForeignKeyExpander
from agent.retrieval.hybrid import BM25Index, HybridSearcher, tokenize
from agent.retrieval.retriever import SchemaRetriever
from semantic.manager import semantic_manager


def test_tokenize():
    tokens = tokenize("What is the average salary in district A11?")
    assert "salary" in tokens
    assert "district" in tokens
    assert "a11" in tokens


def test_bm25_lexical_search():
    index = BM25Index()
    docs = [
        "Table district with column A11 meaning average salary",
        "Table loan with column amount and status",
        "Table account with column frequency POPLATEK MESICNE",
    ]
    index.index(
        doc_ids=["doc_1", "doc_2", "doc_3"],
        documents=docs,
        metadatas=[{"table": "district"}, {"table": "loan"}, {"table": "account"}],
    )

    results = index.search("A11 salary", top_k=2)
    assert len(results) > 0
    top_doc_id, score, meta = results[0]
    assert top_doc_id == "doc_1"
    assert meta["table"] == "district"
    assert score > 0


def test_fk_expansion_bridges_tables():
    expander = ForeignKeyExpander(manager=semantic_manager)

    # 1. client and account must be bridged by disp
    expanded = expander.expand_tables(["client", "account"])
    assert "disp" in expanded
    assert "client" in expanded
    assert "account" in expanded

    # 2. client and loan must be bridged by disp and account
    # client -> disp -> account -> loan
    expanded_loan = expander.expand_tables(["client", "loan"])
    assert "disp" in expanded_loan
    assert "account" in expanded_loan
    assert "loan" in expanded_loan
    assert "client" in expanded_loan


def test_hybrid_searcher_rrf():
    searcher = HybridSearcher(collection_name="test_rrf_collection")
    searcher.index(
        doc_ids=["t1", "t2", "t3"],
        documents=[
            "Active loan contracts and payment delinquency",
            "Customer bank accounts opened in Prague",
            "Credit card withdrawals and transaction ledger",
        ],
        metadatas=[{"topic": "loans"}, {"topic": "accounts"}, {"topic": "transactions"}],
    )

    hits = searcher.search("active loan payment", top_k=2)
    assert len(hits) > 0
    assert hits[0]["id"] == "t1"
    assert hits[0]["metadata"]["topic"] == "loans"
    assert hits[0]["score"] > 0


def test_schema_retriever_end_to_end():
    retriever = SchemaRetriever(manager=semantic_manager)

    # Question about active loans
    result = retriever.retrieve("What is the total amount of active loans?")
    assert "loan" in result.expanded_tables

    glossary_terms = [g.term for g in result.glossary_terms]
    assert any("Active Loan" in t for t in glossary_terms)

    # Verify formatted context is populated
    assert "=== RETRIEVED SCHEMA CONTEXT ===" in result.formatted_context
    assert "=== BUSINESS GLOSSARY & DEFINITIONS ===" in result.formatted_context
    assert "=== VERIFIED FEW-SHOT EXAMPLES ===" in result.formatted_context


def test_schema_retriever_multi_table_with_expansion():
    retriever = SchemaRetriever(manager=semantic_manager)

    # Question requiring multi-table join
    result = retriever.retrieve("Show all clients who hold an active loan in Prague")
    assert "loan" in result.expanded_tables
    assert "client" in result.expanded_tables
    # FK expansion must have pulled bridge table disp
    assert "disp" in result.expanded_tables
