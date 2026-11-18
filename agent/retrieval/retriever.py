"""SchemaRetriever orchestrating hybrid search, FK expansion, and prompt construction."""

import logging

from agent.retrieval.fk_expander import fk_expander
from agent.retrieval.hybrid import HybridSearcher
from agent.retrieval.models import RetrievalResult
from semantic.manager import SemanticManager, semantic_manager
from semantic.models import FewShotExample, GlossaryTerm

logger = logging.getLogger(__name__)


class SchemaRetriever:
    """End-to-end schema retriever combining dense Chroma + sparse BM25 + FK graph expansion."""

    def __init__(self, manager: SemanticManager = semantic_manager):
        self.manager = manager
        self.fk_expander = fk_expander

        # Initialize hybrid searchers for collections
        self.table_searcher = HybridSearcher(collection_name="schema_tables")
        self.column_searcher = HybridSearcher(collection_name="schema_columns")
        self.glossary_searcher = HybridSearcher(collection_name="schema_glossary")
        self.example_searcher = HybridSearcher(collection_name="schema_examples")

        self.index_all()

    def index_all(self):
        """Indexes all semantic layer assets into hybrid search collections."""
        self.index_tables()
        self.index_columns()
        self.index_glossary()
        self.index_examples()

    def index_tables(self):
        """Creates one rich searchable document per table."""
        doc_ids = []
        documents = []
        metadatas = []

        for name, tbl in self.manager.tables.items():
            col_summary = ", ".join([f"{c.name} ({c.type})" for c in tbl.columns])
            meanings = ", ".join(
                [f"{c.name}: {c.business_meaning}" for c in tbl.columns if c.business_meaning]
            )

            doc_text = (
                f"Table name: {name}. Description: {tbl.description}. "
                f"Domain notes: {tbl.domain_notes or ''}. "
                f"Columns: {col_summary}. Column meanings: {meanings}."
            )
            doc_ids.append(f"table_{name}")
            documents.append(doc_text)
            metadatas.append({"table_name": name, "type": "table"})

        if doc_ids:
            self.table_searcher.index(doc_ids, documents, metadatas)

    def index_columns(self):
        """Creates one searchable document per column to capture lexical column names."""
        doc_ids = []
        documents = []
        metadatas = []

        for tbl_name, tbl in self.manager.tables.items():
            for col in tbl.columns:
                doc_text = (
                    f"Column name: {col.name}. Table: {tbl_name}. "
                    f"Type: {col.type}. Description: {col.description}. "
                    f"Business meaning: {col.business_meaning or ''}. "
                    f"Sample values: {col.sample_values}."
                )
                doc_ids.append(f"col_{tbl_name}_{col.name}")
                documents.append(doc_text)
                metadatas.append(
                    {"table_name": tbl_name, "column_name": col.name, "type": "column"}
                )

        if doc_ids:
            self.column_searcher.index(doc_ids, documents, metadatas)

    def index_glossary(self):
        """Indexes business definitions and metrics."""
        doc_ids = []
        documents = []
        metadatas = []

        for idx, term in enumerate(self.manager.glossary):
            doc_text = (
                f"Business term: {term.term}. Definition: {term.definition}. "
                f"SQL Expression: {term.sql_expression}. "
                f"Tables: {', '.join(term.applicable_tables)}. "
                f"Examples: {' '.join(term.examples)}."
            )
            doc_ids.append(f"glossary_{idx}")
            documents.append(doc_text)
            metadatas.append({"term": term.term, "idx": idx, "type": "glossary"})

        if doc_ids:
            self.glossary_searcher.index(doc_ids, documents, metadatas)

    def index_examples(self):
        """Indexes verified few-shot question and SQL pairs."""
        doc_ids = []
        documents = []
        metadatas = []

        for ex in self.manager.examples:
            doc_text = (
                f"Question: {ex.question}. Evidence: {ex.evidence or ''}. "
                f"Reasoning: {ex.reasoning or ''}. Tables: {', '.join(ex.tables_used)}. "
                f"SQL: {ex.sql}."
            )
            doc_ids.append(f"example_{ex.question_id}")
            documents.append(doc_text)
            metadatas.append({"question_id": ex.question_id, "type": "example"})

        if doc_ids:
            self.example_searcher.index(doc_ids, documents, metadatas)

    def retrieve(
        self,
        query: str,
        top_k_tables: int = 3,
        top_k_glossary: int = 3,
        top_k_examples: int = 3,
    ) -> RetrievalResult:
        """Executes full hybrid retrieval with foreign key expansion and prompt formatting."""
        # 1. Search tables directly
        table_hits = self.table_searcher.search(query, top_k=top_k_tables)
        candidate_tables = [
            h["metadata"].get("table_name") for h in table_hits if h["metadata"].get("table_name")
        ]

        # 2. Search columns (helps when query mentions specific column names like 'A11', 'balance', 'gender')
        col_hits = self.column_searcher.search(query, top_k=top_k_tables)
        for h in col_hits:
            tbl = h["metadata"].get("table_name")
            if tbl and tbl not in candidate_tables:
                candidate_tables.append(tbl)

        candidate_tables = candidate_tables[:top_k_tables]

        # 3. Expand candidate tables through foreign key graph to bridge joins
        expanded_tables = self.fk_expander.expand_tables(candidate_tables)

        # 4. Search glossary
        glossary_hits = self.glossary_searcher.search(query, top_k=top_k_glossary)
        selected_glossary: list[GlossaryTerm] = []
        for h in glossary_hits:
            idx = h["metadata"].get("idx")
            if idx is not None and 0 <= idx < len(self.manager.glossary):
                selected_glossary.append(self.manager.glossary[idx])

        # 5. Search few-shot examples
        example_hits = self.example_searcher.search(query, top_k=top_k_examples)
        selected_examples: list[FewShotExample] = []
        for h in example_hits:
            qid = h["metadata"].get("question_id")
            for ex in self.manager.examples:
                if ex.question_id == qid:
                    selected_examples.append(ex)
                    break

        # Fallback if no examples hit
        if not selected_examples:
            selected_examples = self.manager.get_relevant_examples(
                expanded_tables, limit=top_k_examples
            )

        # 6. Format prompt sections
        formatted_schema = self.manager.format_schema_for_prompt(expanded_tables)
        formatted_glossary = self.manager.format_glossary_for_prompt(
            [g.term for g in selected_glossary]
        )
        formatted_examples = self.manager.format_examples_for_prompt(selected_examples)

        formatted_context = (
            f"=== RETRIEVED SCHEMA CONTEXT ===\n{formatted_schema}\n\n"
            f"=== BUSINESS GLOSSARY & DEFINITIONS ===\n{formatted_glossary}\n\n"
            f"=== VERIFIED FEW-SHOT EXAMPLES ===\n{formatted_examples}"
        )

        return RetrievalResult(
            query=query,
            tables=candidate_tables,
            expanded_tables=expanded_tables,
            glossary_terms=selected_glossary,
            examples=selected_examples,
            formatted_schema=formatted_schema,
            formatted_glossary=formatted_glossary,
            formatted_examples=formatted_examples,
            formatted_context=formatted_context,
        )


schema_retriever = SchemaRetriever()
