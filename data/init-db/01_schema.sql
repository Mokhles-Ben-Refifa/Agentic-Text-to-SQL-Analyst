-- =============================================================================
-- Insurance Warehouse Schema (01_schema.sql)
-- Designed with intentional real-world nuances:
--   1. Ambiguous columns: 'status' across agents, customers, policies
--   2. Multi-hop relationships and bridge tables (policy_coverages)
--   3. Nullable fields (cancellation_reason, denial_reason, notes, phone)
--   4. Sensitive PII columns (national_id, email, phone)
--   5. A forbidden internal table (internal_audit)
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. Reference: Countries
CREATE TABLE IF NOT EXISTS countries (
    country_code VARCHAR(3) PRIMARY KEY,
    country_name VARCHAR(100) NOT NULL,
    region VARCHAR(50) NOT NULL,
    currency VARCHAR(3) NOT NULL
);

-- 2. Dimension: Insurance Agents
CREATE TABLE IF NOT EXISTS agents (
    agent_id VARCHAR(36) PRIMARY KEY,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    email VARCHAR(150) NOT NULL,
    country_code VARCHAR(3) NOT NULL REFERENCES countries(country_code),
    agency_name VARCHAR(150) NOT NULL,
    status VARCHAR(20) NOT NULL, -- 'ACTIVE', 'INACTIVE', 'SUSPENDED'
    commission_rate NUMERIC(4, 2) NOT NULL,
    hire_date DATE NOT NULL
);

-- 3. Dimension: Customers (includes PII)
CREATE TABLE IF NOT EXISTS customers (
    customer_id VARCHAR(36) PRIMARY KEY,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    email VARCHAR(150) NOT NULL,
    phone VARCHAR(50),
    national_id VARCHAR(50) NOT NULL, -- Sensitive PII: should be masked
    date_of_birth DATE NOT NULL,
    country_code VARCHAR(3) NOT NULL REFERENCES countries(country_code),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) NOT NULL -- 'ACTIVE', 'CHURNED', 'PROSPECT'
);

-- 4. Dimension: Insurance Products
CREATE TABLE IF NOT EXISTS products (
    product_id VARCHAR(36) PRIMARY KEY,
    product_code VARCHAR(50) UNIQUE NOT NULL,
    product_name VARCHAR(100) NOT NULL,
    product_line VARCHAR(50) NOT NULL, -- 'AUTO', 'HOME', 'LIFE', 'HEALTH'
    base_annual_premium NUMERIC(10, 2) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

-- 5. Fact/Core: Policies
CREATE TABLE IF NOT EXISTS policies (
    policy_id VARCHAR(36) PRIMARY KEY,
    policy_number VARCHAR(50) UNIQUE NOT NULL,
    customer_id VARCHAR(36) NOT NULL REFERENCES customers(customer_id),
    agent_id VARCHAR(36) NOT NULL REFERENCES agents(agent_id),
    product_id VARCHAR(36) NOT NULL REFERENCES products(product_id),
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    premium_amount NUMERIC(10, 2) NOT NULL,
    deductible_amount NUMERIC(10, 2) NOT NULL,
    payment_frequency VARCHAR(20) NOT NULL, -- 'MONTHLY', 'QUARTERLY', 'ANNUAL'
    status VARCHAR(20) NOT NULL, -- 'ACTIVE', 'EXPIRED', 'CANCELLED', 'LAPSED'
    cancellation_reason VARCHAR(255)
);

-- 6. Dimension/Bridge: Policy Coverages (Many-to-Many bridge between policy & coverage options)
CREATE TABLE IF NOT EXISTS policy_coverages (
    coverage_id VARCHAR(36) PRIMARY KEY,
    policy_id VARCHAR(36) NOT NULL REFERENCES policies(policy_id) ON DELETE CASCADE,
    coverage_type VARCHAR(50) NOT NULL, -- 'COLLISION', 'LIABILITY', 'FIRE', 'THEFT', 'FLOOD', 'MEDICAL'
    limit_amount NUMERIC(12, 2) NOT NULL,
    deductible NUMERIC(10, 2) NOT NULL
);

-- 7. Fact: Claims
CREATE TABLE IF NOT EXISTS claims (
    claim_id VARCHAR(36) PRIMARY KEY,
    claim_number VARCHAR(50) UNIQUE NOT NULL,
    policy_id VARCHAR(36) NOT NULL REFERENCES policies(policy_id),
    incident_date DATE NOT NULL,
    reported_date DATE NOT NULL,
    claim_status VARCHAR(30) NOT NULL, -- 'OPEN', 'APPROVED', 'REJECTED', 'SETTLED', 'INVESTIGATING'
    claimed_amount NUMERIC(12, 2) NOT NULL,
    approved_amount NUMERIC(12, 2) NOT NULL DEFAULT 0.00,
    paid_amount NUMERIC(12, 2) NOT NULL DEFAULT 0.00,
    denial_reason VARCHAR(255)
);

-- 8. Fact Detail: Claim Events (Audit lifecycle of claims)
CREATE TABLE IF NOT EXISTS claim_events (
    event_id VARCHAR(36) PRIMARY KEY,
    claim_id VARCHAR(36) NOT NULL REFERENCES claims(claim_id) ON DELETE CASCADE,
    event_type VARCHAR(50) NOT NULL, -- 'FILED', 'INSPECTION_SCHEDULED', 'OFFER_MADE', 'PAYMENT_ISSUED', 'CLOSED'
    event_timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    notes TEXT,
    handled_by VARCHAR(100) NOT NULL
);

-- 9. Fact: Premium Payments
CREATE TABLE IF NOT EXISTS payments (
    payment_id VARCHAR(36) PRIMARY KEY,
    policy_id VARCHAR(36) NOT NULL REFERENCES policies(policy_id),
    payment_date DATE NOT NULL,
    amount NUMERIC(10, 2) NOT NULL,
    payment_method VARCHAR(50) NOT NULL, -- 'CREDIT_CARD', 'DIRECT_DEBIT', 'BANK_TRANSFER'
    payment_status VARCHAR(30) NOT NULL, -- 'SUCCESS', 'FAILED', 'REFUNDED'
    transaction_reference VARCHAR(100) UNIQUE NOT NULL
);

-- 10. Sensitive/Forbidden Table: Internal Audit Log
-- The text-to-SQL agent MUST NEVER have access to this table.
CREATE TABLE IF NOT EXISTS internal_audit (
    audit_id VARCHAR(36) PRIMARY KEY,
    table_name VARCHAR(100) NOT NULL,
    action VARCHAR(50) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    logged_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    confidential_payload TEXT NOT NULL
);

-- =============================================================================
-- Indexes for performance
-- =============================================================================
CREATE INDEX IF NOT EXISTS idx_policies_customer ON policies(customer_id);
CREATE INDEX IF NOT EXISTS idx_policies_agent ON policies(agent_id);
CREATE INDEX IF NOT EXISTS idx_policies_product ON policies(product_id);
CREATE INDEX IF NOT EXISTS idx_policies_status ON policies(status);
CREATE INDEX IF NOT EXISTS idx_policies_dates ON policies(start_date, end_date);

CREATE INDEX IF NOT EXISTS idx_claims_policy ON claims(policy_id);
CREATE INDEX IF NOT EXISTS idx_claims_status ON claims(claim_status);
CREATE INDEX IF NOT EXISTS idx_claims_incident_date ON claims(incident_date);

CREATE INDEX IF NOT EXISTS idx_payments_policy ON payments(policy_id);
CREATE INDEX IF NOT EXISTS idx_payments_date ON payments(payment_date);

CREATE INDEX IF NOT EXISTS idx_customers_country ON customers(country_code);
CREATE INDEX IF NOT EXISTS idx_customers_status ON customers(status);
CREATE INDEX IF NOT EXISTS idx_agents_country ON agents(country_code);
CREATE INDEX IF NOT EXISTS idx_agents_status ON agents(status);
