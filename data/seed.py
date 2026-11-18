"""Database Seeder Script for the Insurance Warehouse."""

import argparse
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

from data.config import db_settings
from data.generator import InsuranceDataGenerator


def execute_sql_file(engine, file_path: Path):
    """Executes all statements in a raw SQL script file."""
    print(f"Executing SQL file: {file_path.name}...")
    with open(file_path, encoding="utf-8") as f:
        sql = f.read()
    with engine.connect() as conn:
        # Split or run entire block
        conn.execute(text(sql))
        conn.commit()


def seed_database(scale: str = "dev", init_schema: bool = True):
    """Seeds the database with generated synthetic data."""
    print(
        f"Connecting to database via admin URL: {db_settings.postgres_host}:{db_settings.postgres_port}/{db_settings.postgres_db}"
    )
    engine = create_engine(db_settings.admin_database_url, echo=False)

    init_dir = Path(__file__).parent / "init-db"

    if init_schema:
        schema_file = init_dir / "01_schema.sql"
        roles_file = init_dir / "02_roles_and_permissions.sql"
        if schema_file.exists():
            execute_sql_file(engine, schema_file)
        if roles_file.exists():
            try:
                execute_sql_file(engine, roles_file)
            except Exception as e:
                print(f"Warning executing roles script (may already exist): {e}")

    print(f"Generating synthetic insurance data (scale: {scale})...")
    generator = InsuranceDataGenerator(seed=42)
    datasets = generator.generate_all(scale=scale)

    insertion_order = [
        "countries",
        "products",
        "agents",
        "customers",
        "policies",
        "policy_coverages",
        "claims",
        "claim_events",
        "payments",
        "internal_audit",
    ]

    print("Populating database tables...")
    with engine.begin() as conn:
        for table_name in insertion_order:
            df = datasets[table_name]
            print(f"  Inserting {len(df):,} rows into '{table_name}'...")
            df.to_sql(
                table_name,
                conn,
                if_exists="append",
                index=False,
                method="multi",
                chunksize=1000,
            )

    print("\nVerification & Row Count Summary:")
    print("=" * 45)
    with engine.connect() as conn:
        for table_name in insertion_order:
            count = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar()
            print(f"  {table_name.ljust(22)}: {count:,} rows")
    print("=" * 45)
    print("Database seeding completed successfully.")


def main():
    parser = argparse.ArgumentParser(description="Seed Insurance Warehouse Database")
    parser.add_argument(
        "--scale",
        choices=["dev", "full"],
        default="dev",
        help="Data scale: 'dev' (~15k total rows) or 'full' (100k-500k rows)",
    )
    parser.add_argument(
        "--no-init",
        action="store_true",
        help="Skip schema and role initialization (tables must already exist)",
    )
    args = parser.parse_args()

    try:
        seed_database(scale=args.scale, init_schema=not args.no_init)
    except Exception as e:
        print(f"Seeding failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
