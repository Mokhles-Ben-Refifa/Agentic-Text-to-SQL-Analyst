"""SQLAlchemy declarative models for the Insurance Warehouse."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Country(Base):
    __tablename__ = "countries"

    country_code: Mapped[str] = mapped_column(String(3), primary_key=True)
    country_name: Mapped[str] = mapped_column(String(100), nullable=False)
    region: Mapped[str] = mapped_column(String(50), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)

    agents: Mapped[list["Agent"]] = relationship(back_populates="country")
    customers: Mapped[list["Customer"]] = relationship(back_populates="country")


class Agent(Base):
    __tablename__ = "agents"

    agent_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(150), nullable=False)
    country_code: Mapped[str] = mapped_column(
        String(3), ForeignKey("countries.country_code"), nullable=False
    )
    agency_name: Mapped[str] = mapped_column(String(150), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # ACTIVE, INACTIVE, SUSPENDED
    commission_rate: Mapped[Decimal] = mapped_column(Numeric(4, 2), nullable=False)
    hire_date: Mapped[date] = mapped_column(Date, nullable=False)

    country: Mapped["Country"] = relationship(back_populates="agents")
    policies: Mapped[list["Policy"]] = relationship(back_populates="agent")


class Customer(Base):
    __tablename__ = "customers"

    customer_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(150), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    national_id: Mapped[str] = mapped_column(String(50), nullable=False)  # PII
    date_of_birth: Mapped[date] = mapped_column(Date, nullable=False)
    country_code: Mapped[str] = mapped_column(
        String(3), ForeignKey("countries.country_code"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # ACTIVE, CHURNED, PROSPECT

    country: Mapped["Country"] = relationship(back_populates="customers")
    policies: Mapped[list["Policy"]] = relationship(back_populates="customer")


class Product(Base):
    __tablename__ = "products"

    product_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    product_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    product_name: Mapped[str] = mapped_column(String(100), nullable=False)
    product_line: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # AUTO, HOME, LIFE, HEALTH
    base_annual_premium: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    policies: Mapped[list["Policy"]] = relationship(back_populates="product")


class Policy(Base):
    __tablename__ = "policies"

    policy_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    policy_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    customer_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("customers.customer_id"), nullable=False
    )
    agent_id: Mapped[str] = mapped_column(String(36), ForeignKey("agents.agent_id"), nullable=False)
    product_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("products.product_id"), nullable=False
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    premium_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    deductible_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    payment_frequency: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # ACTIVE, EXPIRED, CANCELLED, LAPSED
    cancellation_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    customer: Mapped["Customer"] = relationship(back_populates="policies")
    agent: Mapped["Agent"] = relationship(back_populates="policies")
    product: Mapped["Product"] = relationship(back_populates="policies")
    coverages: Mapped[list["PolicyCoverage"]] = relationship(
        back_populates="policy", cascade="all, delete-orphan"
    )
    claims: Mapped[list["Claim"]] = relationship(back_populates="policy")
    payments: Mapped[list["Payment"]] = relationship(back_populates="policy")


class PolicyCoverage(Base):
    __tablename__ = "policy_coverages"

    coverage_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    policy_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("policies.policy_id"), nullable=False
    )
    coverage_type: Mapped[str] = mapped_column(String(50), nullable=False)
    limit_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    deductible: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    policy: Mapped["Policy"] = relationship(back_populates="coverages")


class Claim(Base):
    __tablename__ = "claims"

    claim_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    claim_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    policy_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("policies.policy_id"), nullable=False
    )
    incident_date: Mapped[date] = mapped_column(Date, nullable=False)
    reported_date: Mapped[date] = mapped_column(Date, nullable=False)
    claim_status: Mapped[str] = mapped_column(String(30), nullable=False)
    claimed_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    approved_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"), nullable=False
    )
    paid_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"), nullable=False
    )
    denial_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    policy: Mapped["Policy"] = relationship(back_populates="claims")
    events: Mapped[list["ClaimEvent"]] = relationship(
        back_populates="claim", cascade="all, delete-orphan"
    )


class ClaimEvent(Base):
    __tablename__ = "claim_events"

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    claim_id: Mapped[str] = mapped_column(String(36), ForeignKey("claims.claim_id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    event_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    handled_by: Mapped[str] = mapped_column(String(100), nullable=False)

    claim: Mapped["Claim"] = relationship(back_populates="events")


class Payment(Base):
    __tablename__ = "payments"

    payment_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    policy_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("policies.policy_id"), nullable=False
    )
    payment_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    payment_method: Mapped[str] = mapped_column(String(50), nullable=False)
    payment_status: Mapped[str] = mapped_column(String(30), nullable=False)
    transaction_reference: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)

    policy: Mapped["Policy"] = relationship(back_populates="payments")


class InternalAudit(Base):
    """Forbidden table - agent has NO access."""

    __tablename__ = "internal_audit"

    audit_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    table_name: Mapped[str] = mapped_column(String(100), nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    actor: Mapped[str] = mapped_column(String(100), nullable=False)
    logged_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    confidential_payload: Mapped[str] = mapped_column(Text, nullable=False)
