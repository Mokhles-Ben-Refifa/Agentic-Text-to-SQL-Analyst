"""Tests for data generation, warehouse schema, and relationships."""

from decimal import Decimal

import pytest
from sqlalchemy import create_engine

from data.config import DatabaseSettings
from data.generator import InsuranceDataGenerator
from data.models import Base


@pytest.fixture(scope="module")
def sample_dataset():
    """Generate a small synthetic dataset for testing."""
    generator = InsuranceDataGenerator(seed=123)
    return generator.generate_all(scale="dev")


def test_generator_contains_all_required_tables(sample_dataset):
    expected_tables = {
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
    }
    assert set(sample_dataset.keys()) == expected_tables


def test_ambiguous_status_columns_exist(sample_dataset):
    """Verify intentional ambiguous 'status' column across multiple entities."""
    assert "status" in sample_dataset["agents"].columns
    assert "status" in sample_dataset["customers"].columns
    assert "status" in sample_dataset["policies"].columns


def test_pii_columns_in_customers(sample_dataset):
    """Verify presence of PII column national_id that guardrails must protect."""
    customers_df = sample_dataset["customers"]
    assert "national_id" in customers_df.columns
    assert "email" in customers_df.columns
    assert customers_df["national_id"].nunique() == len(customers_df)


def test_foreign_key_referential_integrity(sample_dataset):
    """Verify referential integrity across generated datasets."""
    country_codes = set(sample_dataset["countries"]["country_code"])
    customer_ids = set(sample_dataset["customers"]["customer_id"])
    agent_ids = set(sample_dataset["agents"]["agent_id"])
    product_ids = set(sample_dataset["products"]["product_id"])
    policy_ids = set(sample_dataset["policies"]["policy_id"])
    claim_ids = set(sample_dataset["claims"]["claim_id"])

    # Customers and agents belong to known countries
    assert set(sample_dataset["customers"]["country_code"]).issubset(country_codes)
    assert set(sample_dataset["agents"]["country_code"]).issubset(country_codes)

    # Policies refer to valid customers, agents, and products
    assert set(sample_dataset["policies"]["customer_id"]).issubset(customer_ids)
    assert set(sample_dataset["policies"]["agent_id"]).issubset(agent_ids)
    assert set(sample_dataset["policies"]["product_id"]).issubset(product_ids)

    # Claims and payments refer to valid policies
    assert set(sample_dataset["claims"]["policy_id"]).issubset(policy_ids)
    assert set(sample_dataset["payments"]["policy_id"]).issubset(policy_ids)
    assert set(sample_dataset["policy_coverages"]["policy_id"]).issubset(policy_ids)

    # Claim events refer to valid claims
    assert set(sample_dataset["claim_events"]["claim_id"]).issubset(claim_ids)


def test_date_and_financial_logic(sample_dataset):
    """Verify dates and amounts respect realistic business logic."""
    policies_df = sample_dataset["policies"]
    for pol in policies_df.itertuples():
        assert pol.start_date < pol.end_date
        assert pol.premium_amount > Decimal("0.00")

    claims_df = sample_dataset["claims"]
    for clm in claims_df.itertuples():
        assert clm.incident_date <= clm.reported_date
        assert clm.claimed_amount > Decimal("0.00")
        if clm.claim_status == "SETTLED":
            assert clm.paid_amount > Decimal("0.00")
        elif clm.claim_status == "REJECTED":
            assert clm.paid_amount == Decimal("0.00")
            assert clm.denial_reason is not None


def test_sqlite_ddl_compilation():
    """Verify that SQLAlchemy declarative models compile into valid DDL."""
    engine = create_engine("sqlite:///:memory:")
    # Create all tables in SQLite memory engine to verify schema metadata
    Base.metadata.create_all(engine)
    table_names = set(Base.metadata.tables.keys())
    assert "policies" in table_names
    assert "claims" in table_names
    assert "internal_audit" in table_names


def test_database_settings_defaults():
    """Verify connection URL generation and default credentials."""
    settings = DatabaseSettings(db_dialect="postgres")
    assert "bird_warehouse" in settings.admin_database_url
    assert "admin" in settings.admin_database_url
    assert "readonly_agent" in settings.readonly_database_url
    assert settings.statement_timeout_ms == 10000
