"""Pydantic data models for the Semantic Layer."""

from typing import Any

from pydantic import BaseModel, Field


class ColumnMetadata(BaseModel):
    name: str
    type: str
    description: str
    sample_values: list[Any] = Field(default_factory=list)
    primary_key: bool = False
    foreign_key: str | None = None  # Format: "target_table.target_column"
    business_meaning: str | None = None


class TableMetadata(BaseModel):
    name: str
    description: str
    primary_keys: list[str] = Field(default_factory=list)
    columns: list[ColumnMetadata] = Field(default_factory=list)
    domain_notes: str | None = None


class GlossaryTerm(BaseModel):
    term: str
    definition: str
    sql_expression: str
    applicable_tables: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)


class FewShotExample(BaseModel):
    question_id: int | str
    question: str
    evidence: str | None = None
    reasoning: str | None = None
    tables_used: list[str] = Field(default_factory=list)
    sql: str
    difficulty: str = "moderate"
