"""BIRD and Spider benchmark loader and SQLite-to-PostgreSQL sync manager."""

import json
import logging
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

from data.config import db_settings

logger = logging.getLogger(__name__)

BENCHMARKS_DIR = Path(__file__).parent / "benchmarks"
BIRD_DIR = BENCHMARKS_DIR / "bird"
SPIDER_DIR = BENCHMARKS_DIR / "spider"

# Official download links
BIRD_MINI_DEV_URL = "https://bird-bench.oss-cn-beijing.aliyuncs.com/mini_dev_postgresql.zip"
BIRD_DEV_SQLITE_URL = "https://bird-bench.oss-cn-beijing.aliyuncs.com/dev.zip"
SPIDER_DEV_URL = "https://drive.google.com/uc?export=download&id=1_AckYkinAnHQmRNeCj09h52EBPOekhBa"


class BenchmarkLoader:
    """Handles downloading, loading, and syncing BIRD and Spider benchmarks."""

    def __init__(self, base_dir: Path = BENCHMARKS_DIR):
        self.base_dir = Path(base_dir)
        self.bird_dir = self.base_dir / "bird"
        self.spider_dir = self.base_dir / "spider"

    def setup_directories(self):
        """Creates target directories."""
        self.bird_dir.mkdir(parents=True, exist_ok=True)
        self.spider_dir.mkdir(parents=True, exist_ok=True)

    def download_and_extract(self, url: str, target_dir: Path) -> Path:
        """Downloads a zip archive and extracts its contents."""
        target_dir.mkdir(parents=True, exist_ok=True)
        zip_path = target_dir / "dataset.zip"

        logger.info(f"Downloading benchmark from {url}...")
        urllib.request.urlretrieve(url, zip_path)

        logger.info(f"Extracting {zip_path.name} to {target_dir}...")
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(target_dir)

        if zip_path.exists():
            zip_path.unlink()
        return target_dir

    def create_mock_financial_database(self) -> Path:
        """Creates the BIRD 'financial' schema and sample data for offline testing and fast verification.

        The BIRD 'financial' database contains:
          - account (account_id, district_id, frequency, date)
          - client (client_id, gender, birth_date, district_id)
          - disp (disp_id, client_id, account_id, type)
          - district (district_id, A2, A3, A4, A11)
          - loan (loan_id, account_id, date, amount, duration, payments, status)
          - trans (trans_id, account_id, date, type, operation, amount, balance)
          - internal_audit (forbidden table for guardrail testing)
        """
        db_dir = self.bird_dir / "financial"
        db_dir.mkdir(parents=True, exist_ok=True)
        sqlite_file = db_dir / "financial.sqlite"

        engine = create_engine(f"sqlite:///{sqlite_file.resolve()}")

        with engine.begin() as conn:
            # District table
            conn.execute(
                text("""
                CREATE TABLE IF NOT EXISTS district (
                    district_id INTEGER PRIMARY KEY,
                    A2 TEXT NOT NULL, -- district name
                    A3 TEXT NOT NULL, -- region
                    A4 INTEGER NOT NULL, -- population
                    A11 REAL NOT NULL -- average salary
                );
            """)
            )

            # Account table
            conn.execute(
                text("""
                CREATE TABLE IF NOT EXISTS account (
                    account_id INTEGER PRIMARY KEY,
                    district_id INTEGER NOT NULL,
                    frequency TEXT NOT NULL,
                    date TEXT NOT NULL,
                    FOREIGN KEY (district_id) REFERENCES district(district_id)
                );
            """)
            )

            # Client table
            conn.execute(
                text("""
                CREATE TABLE IF NOT EXISTS client (
                    client_id INTEGER PRIMARY KEY,
                    gender TEXT NOT NULL,
                    birth_date TEXT NOT NULL,
                    district_id INTEGER NOT NULL,
                    FOREIGN KEY (district_id) REFERENCES district(district_id)
                );
            """)
            )

            # Disposition table
            conn.execute(
                text("""
                CREATE TABLE IF NOT EXISTS disp (
                    disp_id INTEGER PRIMARY KEY,
                    client_id INTEGER NOT NULL,
                    account_id INTEGER NOT NULL,
                    type TEXT NOT NULL, -- 'OWNER' or 'DISPONENT'
                    FOREIGN KEY (client_id) REFERENCES client(client_id),
                    FOREIGN KEY (account_id) REFERENCES account(account_id)
                );
            """)
            )

            # Loan table
            conn.execute(
                text("""
                CREATE TABLE IF NOT EXISTS loan (
                    loan_id INTEGER PRIMARY KEY,
                    account_id INTEGER NOT NULL,
                    date TEXT NOT NULL,
                    amount INTEGER NOT NULL,
                    duration INTEGER NOT NULL,
                    payments REAL NOT NULL,
                    status TEXT NOT NULL, -- 'A', 'B', 'C', 'D'
                    FOREIGN KEY (account_id) REFERENCES account(account_id)
                );
            """)
            )

            # Transaction table
            conn.execute(
                text("""
                CREATE TABLE IF NOT EXISTS trans (
                    trans_id INTEGER PRIMARY KEY,
                    account_id INTEGER NOT NULL,
                    date TEXT NOT NULL,
                    type TEXT NOT NULL, -- 'PRIJEM' (credit), 'VYDAJ' (withdrawal)
                    operation TEXT,
                    amount REAL NOT NULL,
                    balance REAL NOT NULL,
                    FOREIGN KEY (account_id) REFERENCES account(account_id)
                );
            """)
            )

            # Forbidden table for agent guardrail tests
            conn.execute(
                text("""
                CREATE TABLE IF NOT EXISTS internal_audit (
                    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    logged_at TEXT NOT NULL
                );
            """)
            )

            # Seed sample rows if empty
            count = conn.execute(text("SELECT COUNT(*) FROM district")).scalar()
            if count == 0:
                conn.execute(
                    text("""
                    INSERT INTO district VALUES
                        (1, 'Hl.m. Praha', 'Prague', 1204953, 12541),
                        (2, 'Benesov', 'Central Bohemia', 88884, 8507),
                        (3, 'Beroun', 'Central Bohemia', 77014, 8980)
                    """)
                )
                conn.execute(
                    text("""
                    INSERT INTO account VALUES
                        (1, 1, 'POPLATEK MESICNE', '1995-03-24'),
                        (2, 2, 'POPLATEK MESICNE', '1993-02-26'),
                        (3, 3, 'POPLATEK TYDNE', '1997-07-07')
                    """)
                )
                conn.execute(
                    text("""
                    INSERT INTO client VALUES
                        (1, 'F', '1970-12-13', 1),
                        (2, 'M', '1945-08-14', 2),
                        (3, 'F', '1968-10-09', 3)
                    """)
                )
                conn.execute(
                    text("""
                    INSERT INTO disp VALUES
                        (1, 1, 1, 'OWNER'),
                        (2, 2, 2, 'OWNER'),
                        (3, 3, 3, 'OWNER')
                    """)
                )
                conn.execute(
                    text("""
                    INSERT INTO loan VALUES
                        (1, 1, '1996-04-29', 80952, 24, 3373.0, 'A'),
                        (2, 2, '1994-01-05', 30276, 12, 2523.0, 'B')
                    """)
                )
                conn.execute(
                    text("""
                    INSERT INTO trans VALUES
                        (1, 1, '1995-03-24', 'PRIJEM', 'VKLAD', 1000.0, 1000.0),
                        (2, 1, '1995-04-13', 'PRIJEM', 'PREVOD Z UCTU', 3679.0, 4679.0),
                        (3, 2, '1993-02-26', 'PRIJEM', 'VKLAD', 1100.0, 1100.0)
                    """)
                )
                conn.execute(
                    text("""
                    INSERT INTO internal_audit (action, actor, logged_at) VALUES
                        ('SECURITY_SCAN', 'sysadmin', '2026-11-18 20:00:00')
                    """)
                )

        # Create sample BIRD dev questions file for financial
        questions_file = self.bird_dir / "dev_financial.json"
        if not questions_file.exists():
            sample_questions = [
                {
                    "question_id": 1,
                    "db_id": "financial",
                    "question": "What is the average loan amount for each loan status?",
                    "evidence": "loan status is in loan.status, amount is loan.amount",
                    "SQL": "SELECT status, AVG(amount) FROM loan GROUP BY status",
                    "difficulty": "simple",
                },
                {
                    "question_id": 2,
                    "db_id": "financial",
                    "question": "List all clients who have an active loan greater than 50000 in Prague.",
                    "evidence": "Prague district name is 'Hl.m. Praha', loan status 'A' or 'C'",
                    "SQL": "SELECT T1.client_id, T1.gender FROM client AS T1 INNER JOIN disp AS T2 ON T1.client_id = T2.client_id INNER JOIN loan AS T3 ON T2.account_id = T3.account_id INNER JOIN district AS T4 ON T1.district_id = T4.district_id WHERE T4.A2 = 'Hl.m. Praha' AND T3.amount > 50000",
                    "difficulty": "challenging",
                },
                {
                    "question_id": 3,
                    "db_id": "financial",
                    "question": "How many total accounts are there with monthly fees?",
                    "evidence": "frequency for monthly fee is 'POPLATEK MESICNE'",
                    "SQL": "SELECT COUNT(*) FROM account WHERE frequency = 'POPLATEK MESICNE'",
                    "difficulty": "simple",
                },
            ]
            questions_file.write_text(json.dumps(sample_questions, indent=2), encoding="utf-8")

        return sqlite_file

    def sync_sqlite_to_postgres(
        self,
        sqlite_path: Path,
        pg_engine: Engine | None = None,
        allowlist: list[str] | None = None,
    ) -> list[str]:
        """Copies tables from a SQLite database into PostgreSQL and secures roles."""
        if pg_engine is None:
            pg_engine = create_engine(db_settings.admin_database_url, echo=False)

        sqlite_engine = create_engine(f"sqlite:///{sqlite_path.resolve()}")
        sqlite_inspector = inspect(sqlite_engine)
        tables = sqlite_inspector.get_table_names()

        synced_tables = []
        for table_name in tables:
            if allowlist and table_name not in allowlist:
                continue

            df = pd.read_sql_table(table_name, sqlite_engine)
            with pg_engine.begin() as conn:
                df.to_sql(table_name, conn, if_exists="replace", index=False)
            synced_tables.append(table_name)

        # Apply readonly role permissions on PostgreSQL if possible
        try:
            with pg_engine.begin() as conn:
                # Grant usage on schema public
                conn.execute(text("GRANT USAGE ON SCHEMA public TO readonly_agent;"))
                for t in synced_tables:
                    if t != "internal_audit":
                        conn.execute(text(f"GRANT SELECT ON TABLE {t} TO readonly_agent;"))
                if "internal_audit" in synced_tables:
                    conn.execute(text("REVOKE ALL ON TABLE internal_audit FROM readonly_agent;"))
        except Exception as e:
            logger.warning(
                f"Could not apply readonly permissions (roles may not exist in test DB): {e}"
            )

        return synced_tables

    def load_questions(self, db_id: str | None = None) -> list[dict[str, Any]]:
        """Loads questions from BIRD / Spider json files, filtering by database id."""
        questions = []
        for file in self.bird_dir.glob("*.json"):
            try:
                data = json.loads(file.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    for q in data:
                        if db_id is None or q.get("db_id") == db_id:
                            questions.append(q)
            except Exception as e:
                logger.warning(f"Failed to read {file}: {e}")
        return questions


benchmark_loader = BenchmarkLoader()
