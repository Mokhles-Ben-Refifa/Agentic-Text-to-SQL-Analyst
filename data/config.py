"""Database configuration and connection utilities."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    # Dialect selection: "postgres" or "sqlite"
    db_dialect: str = "postgres"

    # PostgreSQL configuration
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "bird_warehouse"

    # Admin credentials for migrations and seeding
    postgres_admin_user: str = "admin"
    postgres_admin_password: str = "admin_secret_pass"

    # Read-only agent credentials for MCP queries
    postgres_readonly_user: str = "readonly_agent"
    postgres_readonly_password: str = "readonly_secret_pass"

    # SQLite configuration
    sqlite_db_path: str = "./data/benchmarks/bird/financial/financial.sqlite"

    statement_timeout_ms: int = 10000
    max_row_limit: int = 1000

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def admin_database_url(self) -> str:
        if self.db_dialect.lower() == "sqlite":
            path = Path(self.sqlite_db_path).resolve()
            return f"sqlite:///{path}"
        return (
            f"postgresql+psycopg://{self.postgres_admin_user}:{self.postgres_admin_password}@"
            f"{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def readonly_database_url(self) -> str:
        if self.db_dialect.lower() == "sqlite":
            path = Path(self.sqlite_db_path).resolve()
            return f"sqlite:///{path}"
        return (
            f"postgresql+psycopg://{self.postgres_readonly_user}:{self.postgres_readonly_password}@"
            f"{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


db_settings = DatabaseSettings()
