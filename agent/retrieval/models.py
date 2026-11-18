"""Data models for retrieval results."""

from pydantic import BaseModel, Field

from semantic.models import FewShotExample, GlossaryTerm


class RetrievalResult(BaseModel):
    """Container for retrieved schema, business glossary, and examples."""

    query: str
    tables: list[str] = Field(default_factory=list)
    expanded_tables: list[str] = Field(default_factory=list)
    glossary_terms: list[GlossaryTerm] = Field(default_factory=list)
    examples: list[FewShotExample] = Field(default_factory=list)
    formatted_schema: str = ""
    formatted_glossary: str = ""
    formatted_examples: str = ""
    formatted_context: str = ""
