"""Synthetic Insurance Warehouse Data Generator using Faker and Pandas."""

import random
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

import pandas as pd
from faker import Faker


class InsuranceDataGenerator:
    """Generates realistic synthetic insurance data with controlled domain quirks."""

    def __init__(self, seed: int = 42):
        self.seed = seed
        self.fake = Faker()
        Faker.seed(seed)
        random.seed(seed)

    def generate_countries(self) -> pd.DataFrame:
        countries_data = [
            {
                "country_code": "NL",
                "country_name": "Netherlands",
                "region": "Western Europe",
                "currency": "EUR",
            },
            {
                "country_code": "DE",
                "country_name": "Germany",
                "region": "Western Europe",
                "currency": "EUR",
            },
            {
                "country_code": "FR",
                "country_name": "France",
                "region": "Western Europe",
                "currency": "EUR",
            },
            {
                "country_code": "BE",
                "country_name": "Belgium",
                "region": "Western Europe",
                "currency": "EUR",
            },
            {
                "country_code": "HU",
                "country_name": "Hungary",
                "region": "Central Europe",
                "currency": "HUF",
            },
            {
                "country_code": "UK",
                "country_name": "United Kingdom",
                "region": "Northern Europe",
                "currency": "GBP",
            },
        ]
        return pd.DataFrame(countries_data)

    def generate_products(self) -> pd.DataFrame:
        products_data = [
            {
                "product_id": str(uuid.uuid4()),
                "product_code": "AUTO_COMP",
                "product_name": "Comprehensive Auto",
                "product_line": "AUTO",
                "base_annual_premium": Decimal("1200.00"),
                "is_active": True,
            },
            {
                "product_id": str(uuid.uuid4()),
                "product_code": "AUTO_TP",
                "product_name": "Third Party Auto",
                "product_line": "AUTO",
                "base_annual_premium": Decimal("650.00"),
                "is_active": True,
            },
            {
                "product_id": str(uuid.uuid4()),
                "product_code": "HOME_BUILD",
                "product_name": "Building & Structures",
                "product_line": "HOME",
                "base_annual_premium": Decimal("480.00"),
                "is_active": True,
            },
            {
                "product_id": str(uuid.uuid4()),
                "product_code": "HOME_CONT",
                "product_name": "Contents & Valuables",
                "product_line": "HOME",
                "base_annual_premium": Decimal("320.00"),
                "is_active": True,
            },
            {
                "product_id": str(uuid.uuid4()),
                "product_code": "LIFE_TERM",
                "product_name": "Term Life 20yr",
                "product_line": "LIFE",
                "base_annual_premium": Decimal("850.00"),
                "is_active": True,
            },
            {
                "product_id": str(uuid.uuid4()),
                "product_code": "HEALTH_CRIT",
                "product_name": "Critical Illness Cover",
                "product_line": "HEALTH",
                "base_annual_premium": Decimal("920.00"),
                "is_active": True,
            },
        ]
        return pd.DataFrame(products_data)

    def generate_agents(self, count: int, country_codes: list[str]) -> pd.DataFrame:
        statuses = ["ACTIVE", "ACTIVE", "ACTIVE", "INACTIVE", "SUSPENDED"]
        agents = []
        for _ in range(count):
            c_code = random.choice(country_codes)
            hire_date = self.fake.date_between(start_date="-8y", end_date="-6m")
            agents.append(
                {
                    "agent_id": str(uuid.uuid4()),
                    "first_name": self.fake.first_name(),
                    "last_name": self.fake.last_name(),
                    "email": self.fake.unique.company_email(),
                    "country_code": c_code,
                    "agency_name": f"{self.fake.company()} Insurance Agency",
                    "status": random.choice(statuses),
                    "commission_rate": Decimal(str(round(random.uniform(0.04, 0.15), 2))),
                    "hire_date": hire_date,
                }
            )
        return pd.DataFrame(agents)

    def generate_customers(self, count: int, country_codes: list[str]) -> pd.DataFrame:
        statuses = ["ACTIVE", "ACTIVE", "ACTIVE", "ACTIVE", "CHURNED", "PROSPECT"]
        customers = []
        for _ in range(count):
            c_code = random.choice(country_codes)
            dob = self.fake.date_of_birth(minimum_age=18, maximum_age=80)
            created_at = self.fake.date_time_between(start_date="-4y", end_date="now")
            has_phone = random.random() > 0.10
            customers.append(
                {
                    "customer_id": str(uuid.uuid4()),
                    "first_name": self.fake.first_name(),
                    "last_name": self.fake.last_name(),
                    "email": self.fake.unique.email(),
                    "phone": self.fake.phone_number() if has_phone else None,
                    "national_id": f"{c_code}-{random.randint(10000000, 99999999)}",
                    "date_of_birth": dob,
                    "country_code": c_code,
                    "created_at": created_at,
                    "status": random.choice(statuses),
                }
            )
        return pd.DataFrame(customers)

    def generate_policies(
        self,
        count: int,
        customer_ids: list[str],
        agent_ids: list[str],
        products_df: pd.DataFrame,
    ) -> pd.DataFrame:
        frequencies = ["MONTHLY", "MONTHLY", "QUARTERLY", "ANNUAL"]
        cancellation_reasons = [
            "Customer switched provider",
            "Non-payment of premium",
            "Sold insured property",
            "Customer request",
        ]

        products_list = products_df.to_dict(orient="records")
        today = date.today()
        policies = []

        for i in range(count):
            prod = random.choice(products_list)
            cust_id = random.choice(customer_ids)
            agent_id = random.choice(agent_ids)

            start_date = self.fake.date_between(start_date="-3y", end_date="-1m")
            duration_days = 365
            end_date = start_date + timedelta(days=duration_days)

            base_prem = float(prod["base_annual_premium"])
            premium = Decimal(str(round(base_prem * random.uniform(0.85, 1.35), 2)))
            deductible = Decimal(str(random.choice([250, 500, 1000, 2000])))
            freq = random.choice(frequencies)

            if end_date < today:
                status = "EXPIRED"
                reason = None
            else:
                rand_val = random.random()
                if rand_val < 0.08:
                    status = "CANCELLED"
                    reason = random.choice(cancellation_reasons)
                elif rand_val < 0.12:
                    status = "LAPSED"
                    reason = "Overdue payment"
                else:
                    status = "ACTIVE"
                    reason = None

            policies.append(
                {
                    "policy_id": str(uuid.uuid4()),
                    "policy_number": f"POL-{1000000 + i}",
                    "customer_id": cust_id,
                    "agent_id": agent_id,
                    "product_id": prod["product_id"],
                    "start_date": start_date,
                    "end_date": end_date,
                    "premium_amount": premium,
                    "deductible_amount": deductible,
                    "payment_frequency": freq,
                    "status": status,
                    "cancellation_reason": reason,
                }
            )
        return pd.DataFrame(policies)

    def generate_coverages(self, policies_df: pd.DataFrame) -> pd.DataFrame:
        coverages = []
        for pol in policies_df.itertuples():
            num_cov = random.randint(1, 3)
            # Pick a coverage pool
            cov_types = random.sample(
                ["COLLISION", "LIABILITY", "FIRE", "THEFT", "FLOOD", "MEDICAL"],
                k=num_cov,
            )
            for cov_type in cov_types:
                limit = Decimal(str(random.choice([25000, 50000, 100000, 250000])))
                deductible = Decimal(str(random.choice([100, 250, 500])))
                coverages.append(
                    {
                        "coverage_id": str(uuid.uuid4()),
                        "policy_id": pol.policy_id,
                        "coverage_type": cov_type,
                        "limit_amount": limit,
                        "deductible": deductible,
                    }
                )
        return pd.DataFrame(coverages)

    def generate_claims(self, policies_df: pd.DataFrame) -> pd.DataFrame:
        claim_statuses = ["SETTLED", "SETTLED", "APPROVED", "OPEN", "INVESTIGATING", "REJECTED"]
        denial_reasons = [
            "Fraudulent activity detected",
            "Pre-existing condition",
            "Excluded peril under policy terms",
            "Late reporting beyond notification window",
        ]

        claims = []
        claim_counter = 100000

        # ~20% of policies experience a claim
        eligible_policies = policies_df[
            policies_df["status"].isin(["ACTIVE", "EXPIRED", "CANCELLED"])
        ]
        sampled_policies = eligible_policies.sample(frac=0.20, random_state=self.seed)

        for pol in sampled_policies.itertuples():
            claim_counter += 1
            # Incident occurs between policy start and min(policy end, today)
            max_incident = min(pol.end_date, date.today())
            if max_incident <= pol.start_date:
                incident_date = pol.start_date
            else:
                incident_date = self.fake.date_between(
                    start_date=pol.start_date, end_date=max_incident
                )

            # Reported within 0 to 45 days after incident
            reported_date = min(incident_date + timedelta(days=random.randint(0, 45)), date.today())

            status = random.choice(claim_statuses)
            claimed_amount = Decimal(str(round(random.uniform(300.0, 18000.0), 2)))

            if status in ["SETTLED", "APPROVED"]:
                # Approved amount is claimed amount minus deductible, capped
                deductible = float(pol.deductible_amount)
                approved_float = max(100.0, float(claimed_amount) - deductible)
                approved = Decimal(str(round(approved_float, 2)))
                paid = approved if status == "SETTLED" else Decimal("0.00")
                denial = None
            elif status == "REJECTED":
                approved = Decimal("0.00")
                paid = Decimal("0.00")
                denial = random.choice(denial_reasons)
            else:  # OPEN, INVESTIGATING
                approved = Decimal("0.00")
                paid = Decimal("0.00")
                denial = None

            claims.append(
                {
                    "claim_id": str(uuid.uuid4()),
                    "claim_number": f"CLM-{claim_counter}",
                    "policy_id": pol.policy_id,
                    "incident_date": incident_date,
                    "reported_date": reported_date,
                    "claim_status": status,
                    "claimed_amount": claimed_amount,
                    "approved_amount": approved,
                    "paid_amount": paid,
                    "denial_reason": denial,
                }
            )
        return pd.DataFrame(claims)

    def generate_claim_events(self, claims_df: pd.DataFrame) -> pd.DataFrame:
        events = []
        for clm in claims_df.itertuples():
            # Initial filing event
            base_time = datetime.combine(clm.reported_date, datetime.min.time()) + timedelta(
                hours=random.randint(8, 17), minutes=random.randint(0, 59)
            )
            events.append(
                {
                    "event_id": str(uuid.uuid4()),
                    "claim_id": clm.claim_id,
                    "event_type": "FILED",
                    "event_timestamp": base_time,
                    "notes": "Initial claim filed by customer or representative",
                    "handled_by": self.fake.name(),
                }
            )

            # Intermediate event
            if clm.claim_status in ["SETTLED", "APPROVED", "REJECTED", "INVESTIGATING"]:
                inspect_time = base_time + timedelta(days=random.randint(2, 7))
                events.append(
                    {
                        "event_id": str(uuid.uuid4()),
                        "claim_id": clm.claim_id,
                        "event_type": "INSPECTION_SCHEDULED",
                        "event_timestamp": inspect_time,
                        "notes": "Independent damage assessment completed",
                        "handled_by": self.fake.name(),
                    }
                )

            # Resolution event
            if clm.claim_status in ["SETTLED", "APPROVED"]:
                res_time = base_time + timedelta(days=random.randint(8, 20))
                events.append(
                    {
                        "event_id": str(uuid.uuid4()),
                        "claim_id": clm.claim_id,
                        "event_type": "PAYMENT_ISSUED"
                        if clm.claim_status == "SETTLED"
                        else "OFFER_MADE",
                        "event_timestamp": res_time,
                        "notes": f"Settlement processed for {clm.paid_amount}",
                        "handled_by": self.fake.name(),
                    }
                )
            elif clm.claim_status == "REJECTED":
                rej_time = base_time + timedelta(days=random.randint(5, 12))
                events.append(
                    {
                        "event_id": str(uuid.uuid4()),
                        "claim_id": clm.claim_id,
                        "event_type": "CLOSED",
                        "event_timestamp": rej_time,
                        "notes": f"Claim denied: {clm.denial_reason}",
                        "handled_by": self.fake.name(),
                    }
                )

        return pd.DataFrame(events)

    def generate_payments(self, policies_df: pd.DataFrame) -> pd.DataFrame:
        methods = ["CREDIT_CARD", "DIRECT_DEBIT", "DIRECT_DEBIT", "BANK_TRANSFER"]
        payments = []
        payment_counter = 500000

        for pol in policies_df.itertuples():
            freq = pol.payment_frequency
            intervals = 1 if freq == "ANNUAL" else (4 if freq == "QUARTERLY" else 12)
            installment_amt = Decimal(str(round(float(pol.premium_amount) / intervals, 2)))

            for period in range(intervals):
                payment_counter += 1
                if freq == "ANNUAL":
                    p_date = pol.start_date
                elif freq == "QUARTERLY":
                    p_date = pol.start_date + timedelta(days=period * 90)
                else:
                    p_date = pol.start_date + timedelta(days=period * 30)

                if p_date > date.today():
                    break

                # 96% success rate
                rand = random.random()
                if rand < 0.96:
                    p_status = "SUCCESS"
                elif rand < 0.99:
                    p_status = "FAILED"
                else:
                    p_status = "REFUNDED"

                payments.append(
                    {
                        "payment_id": str(uuid.uuid4()),
                        "policy_id": pol.policy_id,
                        "payment_date": p_date,
                        "amount": installment_amt,
                        "payment_method": random.choice(methods),
                        "payment_status": p_status,
                        "transaction_reference": f"TXN-{payment_counter}-{uuid.uuid4().hex[:6].upper()}",
                    }
                )

        return pd.DataFrame(payments)

    def generate_audit_logs(self, count: int = 500) -> pd.DataFrame:
        actions = [
            "ADMIN_OVERRIDE",
            "SECURITY_SCAN",
            "PII_EXPORT",
            "ROLE_ELEVATION",
            "SCHEMA_MIGRATION",
        ]
        actors = ["sysadmin", "secops_bot", "migration_service", "compliance_officer"]
        logs = []
        for _ in range(count):
            logs.append(
                {
                    "audit_id": str(uuid.uuid4()),
                    "table_name": random.choice(
                        ["customers", "policies", "claims", "system_credentials"]
                    ),
                    "action": random.choice(actions),
                    "actor": random.choice(actors),
                    "logged_at": self.fake.date_time_between(start_date="-1y", end_date="now"),
                    "confidential_payload": f"CONFIDENTIAL_PAYLOAD_TOKEN_{uuid.uuid4().hex}: actor accessed privileged data",
                }
            )
        return pd.DataFrame(logs)

    def generate_all(self, scale: str = "dev") -> dict[str, pd.DataFrame]:
        """Generates the full relational dataset based on the specified scale."""
        if scale == "full":
            # 100k - 500k scale
            customer_count = 25000
            agent_count = 250
            policy_count = 50000
            audit_count = 2000
        else:
            # Quick dev scale (~15k total rows, fast and lightweight)
            customer_count = 1500
            agent_count = 40
            policy_count = 3000
            audit_count = 150

        countries_df = self.generate_countries()
        products_df = self.generate_products()
        country_codes = countries_df["country_code"].tolist()

        agents_df = self.generate_agents(agent_count, country_codes)
        customers_df = self.generate_customers(customer_count, country_codes)

        policies_df = self.generate_policies(
            policy_count,
            customers_df["customer_id"].tolist(),
            agents_df["agent_id"].tolist(),
            products_df,
        )

        coverages_df = self.generate_coverages(policies_df)
        claims_df = self.generate_claims(policies_df)
        events_df = self.generate_claim_events(claims_df)
        payments_df = self.generate_payments(policies_df)
        audit_df = self.generate_audit_logs(audit_count)

        return {
            "countries": countries_df,
            "products": products_df,
            "agents": agents_df,
            "customers": customers_df,
            "policies": policies_df,
            "policy_coverages": coverages_df,
            "claims": claims_df,
            "claim_events": events_df,
            "payments": payments_df,
            "internal_audit": audit_df,
        }
