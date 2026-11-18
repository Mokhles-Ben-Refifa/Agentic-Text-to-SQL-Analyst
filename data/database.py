"""Unified database manager supporting PostgreSQL and SQLite for BIRD and Spider."""

from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

from data.config import db_settings


class DatabaseManager:
    """Manages connections, schema inspection, and query execution across dialects."""

    def __init__(self, settings=db_settings):
        self.settings = settings
        self._engines: dict[str, Engine] = {}

    def get_engine(self, is_admin: bool = False, sqlite_path: str | Path | None = None) -> Engine:
        """Returns a cached SQLAlchemy engine for the requested target."""
        if sqlite_path:
            path = Path(sqlite_path).resolve()
            key = f"sqlite_{path}"
            if key not in self._engines:
                self._engines[key] = create_engine(f"sqlite:///{path}", echo=False)
            return self._engines[key]

        if self.settings.db_dialect.lower() == "sqlite":
            path = Path(self.settings.sqlite_db_path).resolve()
            path.parent.mkdir(parents=True, exist_ok=True)
            key = f"sqlite_{path}"
            if key not in self._engines:
                self._engines[key] = create_engine(f"sqlite:///{path}", echo=False)
            return self._engines[key]

        # PostgreSQL engine
        key = "pg_admin" if is_admin else "pg_readonly"
        if key not in self._engines:
            url = (
                self.settings.admin_database_url
                if is_admin
                else self.settings.readonly_database_url
            )
            self._engines[key] = create_engine(
                url,
                echo=False,
                pool_pre_ping=True,
            )
        return self._engines[key]

    def execute_query(
        self,
        sql: str,
        is_admin: bool = False,
        sqlite_path: str | Path | None = None,
    ) -> list[dict[str, Any]]:
        """Executes a query and returns results as a list of dictionaries."""
        engine = self.get_engine(is_admin=is_admin, sqlite_path=sqlite_path)
        with engine.connect() as conn:
            result = conn.execute(text(sql))
            if result.returns_rows:
                columns = list(result.keys())
                rows = result.fetchall()
                return [dict(zip(columns, row, strict=False)) for row in rows]
            conn.commit()
            return []

    def get_table_names(self, sqlite_path: str | Path | None = None) -> list[str]:
        """Lists available table names in the target database."""
        engine = self.get_engine(sqlite_path=sqlite_path)
        inspector = inspect(engine)
        return inspector.get_table_names()

    def get_schema_metadata(
        self,
        sqlite_path: str | Path | None = None,
        tables: list[str] | None = None,
    ) -> dict[str, Any]:
        """Extracts comprehensive schema metadata including columns, types, primary keys, and foreign keys."""
        engine = self.get_engine(sqlite_path=sqlite_path)
        inspector = inspect(engine)
        available_tables = inspector.get_table_names()

        target_tables = [t for t in available_tables if tables is None or t in tables]
        schema = {}

        for table in target_tables:
            columns = inspector.get_columns(table)
            pk = inspector.get_pk_constraint(table).get("constrained_columns", [])
            fks = inspector.get_foreign_keys(table)

            schema[table] = {
                "columns": [
                    {
                        "name": col["name"],
                        "type": str(col["type"]),
                        "nullable": col.get("nullable", True),
                        "primary_key": col["name"] in pk,
                    }
                    for col in columns
                ],
                "foreign_keys": [
                    {
                        "constrained_columns": fk["constrained_columns"],
                        "referred_table": fk["referred_table"],
                        "referred_columns": fk["referred_columns"],
                    }
                    for fk in fks
                ],
            }

        return schema

    def explain_query(
        self,
        sql: str,
        sqlite_path: str | Path | None = None,
    ) -> dict[str, Any]:
        """Performs EXPLAIN query planning to estimate query complexity."""
        engine = self.get_engine(sqlite_path=sqlite_path)
        dialect = engine.dialect.name.lower()

        try:
            with engine.connect() as conn:
                if dialect == "postgresql":
                    explain_sql = f"EXPLAIN (FORMAT JSON) {sql}"
                    res = conn.execute(text(explain_sql)).scalar()
                    plan = res[0]["Plan"] if isinstance(res, list) else res
                    return {
                        "dialect": dialect,
                        "total_cost": plan.get("Total Cost", 0.0),
                        "plan_rows": plan.get("Plan Rows", 0),
                        "plan_type": plan.get("Node Type", "Unknown"),
                    }
                else:
                    # SQLite EXPLAIN QUERY PLAN
                    explain_sql = f"EXPLAIN QUERY PLAN {sql}"
                    rows = conn.execute(text(explain_sql)).fetchall()
                    scan_count = sum(1 for r in rows if "SCAN" in str(r))
                    return {
                        "dialect": dialect,
                        "raw_plan": [str(r) for r in rows],
                        "scan_count": scan_count,
                        "has_full_table_scan": scan_count > 0,
                    }
        except Exception as e:
            return {"dialect": dialect, "error": str(e)}


db_manager = DatabaseManager()
