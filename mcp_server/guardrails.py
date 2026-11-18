"""AST-level SQL Validation and Defense-in-Depth Guardrail Engine using sqlglot."""

import logging

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from mcp_server.models import ErrorType, ValidationResult

logger = logging.getLogger(__name__)

# System tables and forbidden audit logs
FORBIDDEN_TABLES: set[str] = {
    "internal_audit",
    "pg_shadow",
    "pg_authid",
    "pg_user",
    "sqlite_master",
    "sqlite_temp_master",
    "sqlite_sequence",
    "information_schema",
}

# Functions known for DOS or timing-based injection attacks
PROHIBITED_FUNCTIONS: set[str] = {
    "pg_sleep",
    "sleep",
    "benchmark",
    "load_file",
    "sys_eval",
    "sys_exec",
}

# Unmasked sensitive PII columns blocked from raw select
SENSITIVE_PII_COLUMNS: set[str] = {
    "national_id",
    "ssn",
    "social_security_number",
    "password",
    "password_hash",
    "secret_key",
}

DEFAULT_MAX_LIMIT: int = 1000


class SQLGuardrailEngine:
    """Validates SQL statements at the Abstract Syntax Tree (AST) level."""

    def __init__(
        self,
        forbidden_tables: set[str] = FORBIDDEN_TABLES,
        prohibited_functions: set[str] = PROHIBITED_FUNCTIONS,
        sensitive_columns: set[str] = SENSITIVE_PII_COLUMNS,
        max_limit: int = DEFAULT_MAX_LIMIT,
    ):
        self.forbidden_tables = {t.lower() for t in forbidden_tables}
        self.prohibited_functions = {f.lower() for f in prohibited_functions}
        self.sensitive_columns = {c.lower() for c in sensitive_columns}
        self.max_limit = max_limit

    def validate_and_sanitize(
        self,
        sql: str,
        dialect: str = "postgres",
        allowed_tables: list[str] | set[str] | None = None,
    ) -> ValidationResult:
        """Applies multi-layered AST checks: single statement, SELECT only, allowlist, PII, and forced LIMIT."""
        if not sql or not sql.strip():
            return ValidationResult(
                is_valid=False,
                error_type=ErrorType.SYNTAX_ERROR,
                error_message="Query is empty.",
                repair_hint="Provide a valid SQL query.",
            )

        # 1. Parse AST
        try:
            statements = sqlglot.parse(sql, read=dialect)
        except ParseError as e:
            return ValidationResult(
                is_valid=False,
                error_type=ErrorType.SYNTAX_ERROR,
                error_message=f"SQL syntax error: {str(e)}",
                repair_hint="Fix syntax error and ensure query conforms to the specified dialect.",
            )

        # 2. Enforce exactly one statement (blocks stacked injections like '; DROP TABLE')
        if len(statements) == 0:
            return ValidationResult(
                is_valid=False,
                error_type=ErrorType.SYNTAX_ERROR,
                error_message="No valid SQL statement found.",
                repair_hint="Provide an executable SQL statement.",
            )

        if len(statements) > 1:
            return ValidationResult(
                is_valid=False,
                error_type=ErrorType.GUARDRAIL_VIOLATION,
                error_message=f"Multiple SQL statements ({len(statements)}) detected. Only single queries are allowed.",
                repair_hint="Submit only one SELECT statement at a time.",
            )

        tree = statements[0]

        # 3. Enforce SELECT-only queries
        valid_query_types = (exp.Select, exp.Union)
        if not isinstance(tree, valid_query_types):
            return ValidationResult(
                is_valid=False,
                error_type=ErrorType.GUARDRAIL_VIOLATION,
                error_message=f"Statement type '{type(tree).__name__}' is blocked. Only SELECT queries are permitted.",
                repair_hint="Change query to a SELECT statement. Data modifications are strictly forbidden.",
            )

        # Check for any embedded write, DDL, or command expressions
        blocked_nodes = (
            exp.Insert,
            exp.Update,
            exp.Delete,
            exp.Drop,
            exp.Alter,
            exp.Create,
            exp.TruncateTable,
            exp.Command,
            exp.Transaction,
            exp.Commit,
            exp.Rollback,
        )
        for node in tree.walk():
            if isinstance(node, blocked_nodes):
                return ValidationResult(
                    is_valid=False,
                    error_type=ErrorType.GUARDRAIL_VIOLATION,
                    error_message=f"Prohibited operation '{type(node).__name__}' detected within query.",
                    repair_hint="Remove all write or schema modification operations.",
                )

        # 4. Check for prohibited / dangerous functions (sleep, benchmark, file access)
        for func_node in tree.find_all(exp.Anonymous, exp.Func):
            func_name = func_node.name.lower() if func_node.name else ""
            if func_name in self.prohibited_functions:
                return ValidationResult(
                    is_valid=False,
                    error_type=ErrorType.PROHIBITED_FUNCTION,
                    error_message=f"Execution of prohibited function '{func_name}' is blocked.",
                    repair_hint=f"Remove function '{func_name}' from the query.",
                )

        # 5. Table Allowlist & Denylist Check
        referenced_tables: set[str] = set()
        for table_node in tree.find_all(exp.Table):
            if table_node.name:
                t_name = table_node.name.lower()
                referenced_tables.add(t_name)

                # Check forbidden system/audit tables
                if t_name in self.forbidden_tables:
                    return ValidationResult(
                        is_valid=False,
                        error_type=ErrorType.FORBIDDEN_TABLE,
                        error_message=f"Access to forbidden table '{t_name}' is strictly blocked.",
                        repair_hint=f"Remove table '{t_name}'. The agent does not have permission to query internal tables.",
                    )

        # Check allowlist if configured
        if allowed_tables is not None:
            allowed_set = {t.lower() for t in allowed_tables}
            disallowed = referenced_tables - allowed_set
            if disallowed:
                return ValidationResult(
                    is_valid=False,
                    error_type=ErrorType.FORBIDDEN_TABLE,
                    error_message=f"Query references unapproved tables: {disallowed}.",
                    repair_hint=f"Query only allowed tables: {sorted(allowed_set)}.",
                )

        # 6. Sensitive PII column checks
        for col_node in tree.find_all(exp.Column):
            col_name = col_node.name.lower() if col_node.name else ""
            if col_name in self.sensitive_columns:
                return ValidationResult(
                    is_valid=False,
                    error_type=ErrorType.PII_VIOLATION,
                    error_message=f"Access to sensitive PII column '{col_name}' is blocked.",
                    repair_hint=f"Remove sensitive column '{col_name}' or query anonymized aggregations instead.",
                )

        # 7. Forced LIMIT Enforcement
        has_forced_limit = False
        original_limit = None
        enforced_limit = None

        limit_node = tree.args.get("limit")
        if not limit_node:
            tree = tree.limit(self.max_limit)
            has_forced_limit = True
            enforced_limit = self.max_limit
        else:
            try:
                curr_val = int(str(limit_node.expression))
                original_limit = curr_val
                if curr_val > self.max_limit:
                    tree.set("limit", exp.Limit(expression=exp.Literal.number(self.max_limit)))
                    has_forced_limit = True
                    enforced_limit = self.max_limit
                else:
                    enforced_limit = curr_val
            except (ValueError, TypeError):
                tree.set("limit", exp.Limit(expression=exp.Literal.number(self.max_limit)))
                has_forced_limit = True
                enforced_limit = self.max_limit

        sanitized_sql = tree.sql(dialect=dialect)

        return ValidationResult(
            is_valid=True,
            sanitized_sql=sanitized_sql,
            tables_referenced=sorted(referenced_tables),
            has_forced_limit=has_forced_limit,
            original_limit=original_limit,
            enforced_limit=enforced_limit,
        )


guardrail_engine = SQLGuardrailEngine()
