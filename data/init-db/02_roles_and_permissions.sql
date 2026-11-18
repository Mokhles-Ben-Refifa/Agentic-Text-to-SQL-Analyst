-- =============================================================================
-- Roles and Security Boundary (02_roles_and_permissions.sql)
-- Defense in depth:
--   1. Admin role: full DDL/DML access for migrations and seeding.
--   2. Readonly Agent role: strictly read-only SELECT permissions on allowed tables.
--   3. Hard database timeout (10s) and read-only transaction defaults.
--   4. Zero access to 'internal_audit'.
-- =============================================================================

-- Create the readonly agent role if it doesn't already exist
DO
$do$
BEGIN
   IF NOT EXISTS (
      SELECT FROM pg_catalog.pg_roles
      WHERE rolname = 'readonly_agent') THEN
      CREATE ROLE readonly_agent WITH LOGIN PASSWORD 'readonly_secret_pass';
   END IF;
END
$do$;

-- Revoke default public permissions
REVOKE ALL ON DATABASE insurance_warehouse FROM PUBLIC;
REVOKE ALL ON SCHEMA public FROM PUBLIC;

-- Grant database connection & schema usage
GRANT CONNECT ON DATABASE insurance_warehouse TO admin;
GRANT CONNECT ON DATABASE insurance_warehouse TO readonly_agent;

GRANT ALL ON SCHEMA public TO admin;
GRANT USAGE ON SCHEMA public TO readonly_agent;

-- Grant admin full rights on all tables
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO admin;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO admin;

-- Allowlist for readonly_agent: ONLY grant SELECT on safe analytics tables
GRANT SELECT ON TABLE
    countries,
    agents,
    customers,
    products,
    policies,
    policy_coverages,
    claims,
    claim_events,
    payments
TO readonly_agent;

-- HARD DEFENSE: Explicitly ensure readonly_agent can NEVER touch internal_audit
REVOKE ALL ON TABLE internal_audit FROM readonly_agent;
REVOKE ALL ON TABLE internal_audit FROM PUBLIC;

-- Enforce session constraints at the database role level
ALTER ROLE readonly_agent SET statement_timeout = '10000ms';
ALTER ROLE readonly_agent SET default_transaction_read_only = on;
