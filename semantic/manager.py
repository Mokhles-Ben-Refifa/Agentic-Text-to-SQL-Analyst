"""Semantic Layer Manager: loads YAML schemas, glossaries, and few-shot examples."""

from pathlib import Path

import yaml

from semantic.models import ColumnMetadata, FewShotExample, GlossaryTerm, TableMetadata

SEMANTIC_DIR = Path(__file__).parent


class SemanticManager:
    """Manages the semantic layer, business glossary, and verified examples."""

    def __init__(self, semantic_dir: Path = SEMANTIC_DIR):
        self.semantic_dir = Path(semantic_dir)
        self.tables_dir = self.semantic_dir / "tables"
        self.tables: dict[str, TableMetadata] = {}
        self.glossary: list[GlossaryTerm] = []
        self.examples: list[FewShotExample] = []
        self.load_all()

    def load_all(self):
        """Loads all semantic assets from disk."""
        self.load_tables()
        self.load_glossary()
        self.load_examples()

    def load_tables(self):
        """Loads all table YAML definitions from semantic/tables/."""
        self.tables.clear()
        if not self.tables_dir.exists():
            return

        for file_path in self.tables_dir.glob("*.yaml"):
            with open(file_path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if not data or "name" not in data:
                continue

            columns = []
            for col in data.get("columns", []):
                columns.append(
                    ColumnMetadata(
                        name=col["name"],
                        type=col.get("type", "TEXT"),
                        description=col.get("description", ""),
                        sample_values=col.get("sample_values", []),
                        primary_key=col.get("primary_key", False),
                        foreign_key=col.get("foreign_key"),
                        business_meaning=col.get("business_meaning"),
                    )
                )

            self.tables[data["name"]] = TableMetadata(
                name=data["name"],
                description=data.get("description", ""),
                primary_keys=data.get("primary_keys", []),
                columns=columns,
                domain_notes=data.get("domain_notes"),
            )

    def load_glossary(self):
        """Loads glossary terms from semantic/glossary.yaml."""
        self.glossary.clear()
        glossary_file = self.semantic_dir / "glossary.yaml"
        if not glossary_file.exists():
            return

        with open(glossary_file, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not data or "glossary" not in data:
            return

        for item in data["glossary"]:
            self.glossary.append(
                GlossaryTerm(
                    term=item["term"],
                    definition=item["definition"],
                    sql_expression=item["sql_expression"],
                    applicable_tables=item.get("applicable_tables", []),
                    examples=item.get("examples", []),
                )
            )

    def load_examples(self):
        """Loads few-shot question-SQL pairs from semantic/examples.yaml."""
        self.examples.clear()
        examples_file = self.semantic_dir / "examples.yaml"
        if not examples_file.exists():
            return

        with open(examples_file, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not data or "examples" not in data:
            return

        for ex in data["examples"]:
            self.examples.append(
                FewShotExample(
                    question_id=ex["question_id"],
                    question=ex["question"],
                    evidence=ex.get("evidence"),
                    reasoning=ex.get("reasoning"),
                    tables_used=ex.get("tables_used", []),
                    sql=ex["sql"].strip(),
                    difficulty=ex.get("difficulty", "moderate"),
                )
            )

    def get_table(self, table_name: str) -> TableMetadata | None:
        return self.tables.get(table_name)

    def list_tables(self) -> list[str]:
        return sorted(self.tables.keys())

    def format_schema_for_prompt(self, table_names: list[str] | None = None) -> str:
        """Formats target tables into an LLM-ready markdown schema block."""
        target_names = table_names or self.list_tables()
        lines = []

        for name in target_names:
            tbl = self.get_table(name)
            if not tbl:
                continue

            lines.append(f"### Table: `{tbl.name}`")
            lines.append(f"Description: {tbl.description}")
            if tbl.domain_notes:
                lines.append(f"Domain Notes: {tbl.domain_notes.strip()}")

            lines.append("Columns:")
            for col in tbl.columns:
                pk_tag = " [PRIMARY KEY]" if col.primary_key else ""
                fk_tag = f" [REFERENCES {col.foreign_key}]" if col.foreign_key else ""
                meaning = f" (Meaning: {col.business_meaning})" if col.business_meaning else ""
                samples = f" (Samples: {col.sample_values[:4]})" if col.sample_values else ""
                lines.append(
                    f"  - `{col.name}` ({col.type}){pk_tag}{fk_tag}: {col.description}{meaning}{samples}"
                )
            lines.append("")

        return "\n".join(lines).strip()

    def format_glossary_for_prompt(self, terms: list[str] | None = None) -> str:
        """Formats business glossary entries into a markdown block."""
        lines = ["### Business Glossary & Metrics:"]
        selected = [
            g
            for g in self.glossary
            if terms is None or g.term.lower() in [t.lower() for t in terms]
        ]

        if not selected:
            selected = self.glossary

        for g in selected:
            lines.append(f"- **{g.term}**: {g.definition}")
            lines.append(f"  SQL Expression: `{g.sql_expression}`")
            if g.applicable_tables:
                lines.append(f"  Applicable Tables: {', '.join(g.applicable_tables)}")

        return "\n".join(lines).strip()

    def get_relevant_examples(
        self,
        table_names: list[str] | None = None,
        limit: int = 3,
    ) -> list[FewShotExample]:
        """Finds verified few-shot examples matching requested tables."""
        if not table_names:
            return self.examples[:limit]

        target_set = {t.lower() for t in table_names}
        scored = []
        for ex in self.examples:
            ex_tables = {t.lower() for t in ex.tables_used}
            overlap = len(target_set.intersection(ex_tables))
            scored.append((overlap, ex))

        # Sort by highest overlap, then return top limit
        scored.sort(key=lambda x: x[0], reverse=True)
        return [ex for _, ex in scored[:limit]]

    def format_examples_for_prompt(self, examples: list[FewShotExample]) -> str:
        """Formats few-shot examples into an LLM prompt block."""
        lines = ["### Verified Example Query Pairs:"]
        for idx, ex in enumerate(examples, start=1):
            lines.append(f"Example {idx}:")
            lines.append(f"Question: {ex.question}")
            if ex.evidence:
                lines.append(f"Business Evidence: {ex.evidence}")
            if ex.reasoning:
                lines.append(f"Reasoning: {ex.reasoning}")
            lines.append("SQL:")
            lines.append("```sql")
            lines.append(ex.sql)
            lines.append("```")
            lines.append("")

        return "\n".join(lines).strip()


semantic_manager = SemanticManager()
