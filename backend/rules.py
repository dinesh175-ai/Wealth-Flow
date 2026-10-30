
import re
from db import read_only_query, columns, TABLE


# =========================================================
# 1. ROLE-BASED ACCESS CONTROL
# =========================================================

VALID_ROLES = {
    "analyst",
    "relationship_manager",
    "risk_officer",
    "compliance",
}

ROLE_LABELS = {
    "analyst": "Analyst",
    "relationship_manager": "Relationship Manager",
    "risk_officer": "Risk Officer",
    "compliance": "Compliance",
}


def normalize_role(role):
    """Validate the selected workspace role."""
    role = (role or "").strip().lower()

    if role not in VALID_ROLES:
        raise PermissionError(
            "Invalid workspace role. Select Analyst, "
            "Relationship Manager, Risk Officer, or Compliance."
        )

    return role


def classify_domain(question):
    """Classify a question into one business domain."""
    q = re.sub(r"\s+", " ", (question or "").lower().strip())

    compliance_terms = [
        "regulatory", "regulation", "compliance",
        "reg reporting", "audit requirement",
        "compliance review", "regulatory impact",
    ]

    if any(term in q for term in compliance_terms):
        return "compliance"

    relationship_terms = [
        "client", "clients", "customer", "customers",
        "portfolio", "portfolios", "relationship manager",
        "client segment", "client account", "customer account",
        "client relationship",
    ]

    if any(term in q for term in relationship_terms):
        return "relationship_manager"

    risk_terms = [
        "risk", "exposure", "high-risk", "high risk",
        "financial risk", "operational risk",
        "risk monitoring", "risk assessment",
        "risk priority", "high-value", "high value",
        "unusual pattern",
    ]

    if any(term in q for term in risk_terms):
        return "risk_officer"

    return "analyst"


def check_role_access(role, question):
    """Reject questions belonging to another workspace."""
    role = normalize_role(role)
    domain = classify_domain(question)

    if role != domain:
        raise PermissionError(
            f"Access Restricted: This question belongs to the "
            f"{ROLE_LABELS[domain]} domain. "
            f"Your {ROLE_LABELS[role]} workspace cannot access "
            f"this domain. Please switch to the appropriate role."
        )

    return domain


# =========================================================
# 2. DATABASE COLUMN ALIASES
# =========================================================

COLUMN_ALIASES = {
    "aged": [
        "aged_break", "is_aged", "aged",
    ],
    "amount": [
        "break_amount_usd", "amount_usd",
        "break_amount", "amount",
    ],
    "team": [
        "team", "assigned_team", "owner_team",
    ],
    "category": [
        "category", "break_category",
        "recon_category", "reconciliation_category",
    ],
    "priority": [
        "priority_flag", "priority",
    ],
    "confidence": [
        "auto_match_confidence_score",
        "auto_match_confidence",
        "match_confidence",
        "auto_match_score",
    ],
    "age_days": [
        "age_days", "break_age_days",
        "days_open", "aging_days",
    ],
    "repeat": [
        "break_is_repeat", "repeat_break",
        "is_repeat", "repeated",
    ],
    "reg": [
        "regulatory_reporting_impacted",
        "regulatory_impact", "regulatory_reporting",
        "reg_reporting_impact",
    ],
}


ROLE_BLOCKED = {
    "analyst": set(),
    "relationship_manager": {"confidence"},
    "risk_officer": set(),
    "compliance": set(),
}


# =========================================================
# 3. DATABASE FIELD DETECTION
# =========================================================

def detect():
    """Match logical fields to available database columns."""
    available = set(columns())
    found = {}

    for logical, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in available:
                found[logical] = alias
                break

    return found


def check_permission(role, needed):
    """Check permission to access individual logical fields."""
    role = normalize_role(role)
    blocked = ROLE_BLOCKED[role]

    denied = [name for name in needed if name in blocked]

    if denied:
        raise PermissionError(
            f"Your role '{ROLE_LABELS[role]}' cannot access: "
            f"{', '.join(denied)}."
        )


# =========================================================
# 4. FORMATTING AND SQL HELPERS
# =========================================================

def fmt(value):
    if isinstance(value, float):
        return f"{value:,.2f}"

    if isinstance(value, int):
        return f"{value:,}"

    return str(value)


def run(sql, params=()):
    """Execute read-only SQL."""
    return read_only_query(sql, params)


# =========================================================
# 5. MAIN QUESTION ANSWERING ENGINE
# =========================================================

def answer_question(question, role="analyst"):
    """Answer questions using role-controlled local SQL rules."""

    # Always authorize before executing SQL.
    role = normalize_role(role)
    check_role_access(role, question)

    q = re.sub(
        r"\s+",
        " ",
        (question or "").lower().strip()
    )

    c = detect()
    available_columns = set(columns())

    def need(*names):
        missing = [name for name in names if name not in c]

        if missing:
            raise LookupError(
                f"The dataset has no column matching: "
                f"{', '.join(missing)}. "
                f"Update COLUMN_ALIASES in rules.py. "
                f"Available columns: {', '.join(columns())}"
            )

        check_permission(role, names)

    def table_result(
        sql,
        title,
        label_col=0,
        value_col=1,
        chart=True,
        params=(),
    ):
        result_columns, rows = run(sql, params)

        body = "\n".join(
            " | ".join(fmt(value) for value in row)
            for row in rows[:15]
        )

        answer = title if not body else f"{title}\n{body}"

        result = {
            "answer": answer,
            "sql": sql,
            "columns": result_columns,
            "rows": rows,
        }

        if (
            chart
            and rows
            and len(rows[0]) > max(label_col, value_col)
        ):
            result["chart"] = [
                {
                    "label": str(row[label_col]),
                    "value": row[value_col],
                }
                for row in rows[:15]
            ]

        return result

    def scalar(sql, template, fields, params=()):
        _, rows = run(sql, params)
        value = rows[0][0] if rows else 0

        return {
            "answer": template.format(
                fmt(value if value is not None else 0)
            ),
            "sql": sql,
            "fields": fields,
            "columns": ["value"],
            "rows": rows,
        }

    def aged_true():
        return (
            f"({c['aged']} IN "
            "(1,'1','Y','y','Yes','yes','TRUE','True','true'))"
        )

    # =====================================================
    # 6. ANALYST DOMAIN
    # =====================================================

    # Dataset column information

    if (
        "how many columns" in q
        or "columns are available" in q
        or "what columns" in q
    ):
        available = columns()

        return {
            "answer": (
                f"The dataset has {len(available)} columns: "
                f"{', '.join(available)}"
            ),
            "sql": "PRAGMA table_info(breaks)",
            "fields": available,
        }

    # Total reconciliation breaks

    if (
        re.search(
            r"\bhow many (total )?(reconciliation )?breaks\b",
            q,
        )
        and "aged" not in q
        and "team" not in q
        and "regulatory" not in q
        and "compliance" not in q
        and "reg reporting" not in q
    ):
        return scalar(
            f"SELECT COUNT(*) FROM {TABLE}",
            "There are {} reconciliation breaks.",
            ["all rows"],
        )

    # Percentage of aged breaks

    if "percentage" in q and "aged" in q and "amount" not in q:
        need("aged")

        return scalar(
            f"SELECT ROUND(100.0 * SUM({aged_true()}) / COUNT(*), 2) "
            f"FROM {TABLE}",
            "{}% of breaks are aged.",
            [c["aged"]],
        )

    # Percentage of amount from aged breaks

    if "percentage" in q and "amount" in q and "aged" in q:
        need("aged", "amount")

        return scalar(
            f"SELECT ROUND(100.0 * SUM(CASE WHEN {aged_true()} "
            f"THEN {c['amount']} ELSE 0 END) / "
            f"NULLIF(SUM({c['amount']}), 0), 2) FROM {TABLE}",
            "{}% of the total break amount comes from aged breaks.",
            [c["aged"], c["amount"]],
        )

    # Number of aged breaks

    if (
        "aged" in q
        and any(word in q for word in ("how many", "count", "number"))
        and "team" not in q
    ):
        need("aged")

        return scalar(
            f"SELECT COUNT(*) FROM {TABLE} WHERE {aged_true()}",
            "There are {} aged breaks.",
            [c["aged"]],
        )

    # Total break amount

    if (
        ("total break amount" in q or "total amount" in q)
        and "team" not in q
        and "each" not in q
    ):
        need("amount")

        return scalar(
            f"SELECT ROUND(SUM({c['amount']}), 2) FROM {TABLE}",
            "The total break amount is USD {}.",
            [c["amount"]],
        )

    # Average amount

    if "average break amount" in q or "average amount" in q:
        need("amount")

        return scalar(
            f"SELECT ROUND(AVG({c['amount']}), 2) FROM {TABLE}",
            "The average break amount is USD {}.",
            [c["amount"]],
        )

    # Smallest amount

    if "smallest" in q and ("amount" in q or "break" in q):
        need("amount")

        return scalar(
            f"SELECT MIN({c['amount']}) FROM {TABLE}",
            "The smallest break amount is USD {}.",
            [c["amount"]],
        )

    # Amount above threshold

    threshold_match = re.search(
        r"greater than \$?([\d,]+(?:\.\d+)?)",
        q,
    )

    if threshold_match and "amount" in q:
        need("amount")
        threshold = float(
            threshold_match.group(1).replace(",", "")
        )

        return scalar(
            f"SELECT COUNT(*) FROM {TABLE} "
            f"WHERE {c['amount']} > ?",
            f"{{}} breaks have an amount greater than ${threshold:,.2f}.",
            [c["amount"]],
            (threshold,),
        )

    # Different categories

    if "different" in q and "categor" in q:
        need("category")

        return table_result(
            f"SELECT {c['category']}, COUNT(*) FROM {TABLE} "
            "GROUP BY 1 ORDER BY 2 DESC",
            "Reconciliation categories (with break counts):",
        )

    # =====================================================
    # 7. TEAM-WISE ANALYTICS
    # =====================================================

    if "team" in q:
        need("team")
        team_col = c["team"]

        if "aged" in q:
            need("aged")

            return table_result(
                f"SELECT {team_col}, COUNT(*) FROM {TABLE} "
                f"WHERE {aged_true()} GROUP BY 1 ORDER BY 2 DESC",
                "Aged breaks by team:",
            )

        if "amount" in q:
            need("amount")

            limit_clause = (
                " LIMIT 5"
                if re.search(r"\btop\s*(5|five)\b", q)
                else ""
            )

            return table_result(
                f"SELECT {team_col}, "
                f"ROUND(SUM({c['amount']}), 2) "
                f"FROM {TABLE} GROUP BY 1 "
                f"ORDER BY 2 DESC{limit_clause}",
                "Total break amount by team (USD):",
            )

        if "lowest" in q:
            return table_result(
                f"SELECT {team_col}, COUNT(*) FROM {TABLE} "
                "GROUP BY 1 ORDER BY 2 ASC LIMIT 1",
                "Team with the lowest number of breaks:",
            )

        if "compare" in q:
            extra = ""

            if "amount" in c:
                need("amount")
                extra = f", ROUND(SUM({c['amount']}), 2)"

            return table_result(
                f"SELECT {team_col}, COUNT(*){extra} "
                f"FROM {TABLE} GROUP BY 1 ORDER BY 2 DESC",
                "Team comparison (breaks, amount):",
            )

        limit_clause = (
            " LIMIT 1"
            if "highest" in q or "most" in q
            else ""
        )

        return table_result(
            f"SELECT {team_col}, COUNT(*) FROM {TABLE} "
            f"GROUP BY 1 ORDER BY 2 DESC{limit_clause}",
            "Breaks by team:",
        )

    # =====================================================
    # 8. RELATIONSHIP MANAGER ANALYTICS
    # IMPORTANT: Keep this BEFORE generic Top-N and Risk rules.
    # =====================================================

    relationship_terms = (
        "client", "clients", "customer", "customers",
        "counterparty", "counterparties",
    )

    exposure_terms = (
        "exposure", "highest", "top", "largest",
        "most", "greatest",
    )

    # Client/customer/counterparty exposure.
    # The dataset has counterparty_id, not verified client names.
    if (
        any(term in q for term in relationship_terms)
        and any(term in q for term in exposure_terms)
    ):
        need("amount")

        if "counterparty_id" not in available_columns:
            raise LookupError(
                "The dataset does not contain counterparty_id. "
                "Client-level exposure cannot be calculated "
                "from the available columns."
            )

        return table_result(
            f"SELECT counterparty_id, "
            f"ROUND(SUM({c['amount']}), 2) AS total_exposure "
            f"FROM {TABLE} "
            f"GROUP BY counterparty_id "
            f"ORDER BY total_exposure DESC LIMIT 10",
            "Top 10 counterparties by total break exposure (USD):",
            chart=True,
        )

    # Account exposure

    if (
        "account" in q
        and any(term in q for term in exposure_terms)
    ):
        need("amount")

        if "account_id" not in available_columns:
            raise LookupError(
                "The dataset does not contain account_id. "
                "Account-level exposure cannot be calculated."
            )

        return table_result(
            f"SELECT account_id, "
            f"ROUND(SUM({c['amount']}), 2) AS total_exposure "
            f"FROM {TABLE} "
            f"GROUP BY account_id "
            f"ORDER BY total_exposure DESC LIMIT 10",
            "Top 10 accounts by total break exposure (USD):",
            chart=True,
        )

    # Portfolio requests need actual portfolio data.

    if "portfolio" in q:
        raise LookupError(
            "Portfolio-level analytics are not available because "
            "the current dataset does not contain a portfolio_id "
            "or portfolio name column."
        )

    # =====================================================
    # 9. TOP-N LARGEST BREAKS
    # =====================================================

    number_words = {
        "one": 1, "two": 2, "three": 3, "four": 4,
        "five": 5, "six": 6, "seven": 7, "eight": 8,
        "nine": 9, "ten": 10,
    }

    top_match = re.search(r"\btop\s*(\d+)\b", q)

    top_word_match = re.search(
        r"\btop\s+(one|two|three|four|five|six|seven|eight|nine|ten)\b",
        q,
    )

    if top_match or top_word_match or "top ten" in q:
        need("amount")

        if top_match:
            limit = int(top_match.group(1))
        elif top_word_match:
            limit = number_words[top_word_match.group(1)]
        else:
            limit = 10

        limit = max(1, min(limit, 100))

        return table_result(
            f"SELECT * FROM {TABLE} "
            f"ORDER BY {c['amount']} DESC LIMIT {limit}",
            f"Top {limit} largest reconciliation breaks by amount:",
            chart=False,
        )

    if "largest" in q and "amount" in q:
        need("amount")

        return scalar(
            f"SELECT MAX({c['amount']}) FROM {TABLE}",
            "The largest break amount is USD {}.",
            [c["amount"]],
        )

    if "largest" in q and (
        "break" in q or "reconciliation" in q
    ):
        need("amount")

        return table_result(
            f"SELECT * FROM {TABLE} "
            f"ORDER BY {c['amount']} DESC LIMIT 1",
            "The largest reconciliation break by amount:",
            chart=False,
        )

    # =====================================================
    # 10. CATEGORY AND PRIORITY ANALYTICS
    # =====================================================

    if "categor" in q and (
        "amount" in q or "contribute" in q
    ):
        need("category", "amount")

        return table_result(
            f"SELECT {c['category']}, "
            f"ROUND(SUM({c['amount']}), 2) "
            f"FROM {TABLE} GROUP BY 1 ORDER BY 2 DESC",
            "Total break amount by category (USD):",
        )

    if "priority" in q:
        need("priority")

        return table_result(
            f"SELECT {c['priority']}, COUNT(*) FROM {TABLE} "
            "GROUP BY 1 ORDER BY 2 DESC",
            "Breaks by priority:",
        )

    # =====================================================
    # 11. RISK OFFICER ANALYTICS
    # =====================================================

    if "risk" in q or "exposure" in q:
        if "aged" in q:
            need("aged")

            return scalar(
                f"SELECT COUNT(*) FROM {TABLE} "
                f"WHERE {aged_true()}",
                "{} aged breaks require risk monitoring.",
                [c["aged"]],
            )

        if "confidence" in q:
            need("confidence")

            return scalar(
                f"SELECT COUNT(*) FROM {TABLE} "
                f"WHERE {c['confidence']} < "
                f"(SELECT AVG({c['confidence']}) * 0.5 "
                f"FROM {TABLE})",
                "{} breaks have low auto-match confidence.",
                [c["confidence"]],
            )

        need("amount")

        return table_result(
            f"SELECT * FROM {TABLE} "
            f"ORDER BY {c['amount']} DESC LIMIT 10",
            "Top 10 breaks requiring financial risk review:",
            chart=False,
        )

    # =====================================================
    # 12. AGE AND REPEAT ANALYTICS
    # =====================================================

    age_match = re.search(r"older than (\d+) days", q)

    if age_match:
        need("age_days")
        days = int(age_match.group(1))

        return scalar(
            f"SELECT COUNT(*) FROM {TABLE} "
            f"WHERE {c['age_days']} > ?",
            f"{{}} breaks are older than {days} days.",
            [c["age_days"]],
            (days,),
        )

    if "longest" in q or (
        "unresolved" in q and "time" in q
    ):
        need("age_days")

        return table_result(
            f"SELECT * FROM {TABLE} "
            f"ORDER BY {c['age_days']} DESC LIMIT 10",
            "Ten longest-open breaks:",
            chart=False,
        )

    if "repeated" in q or "repeat" in q:
        need("repeat")

        return scalar(
            f"SELECT COUNT(*) FROM {TABLE} "
            f"WHERE {c['repeat']} IN "
            "(1,'1','Y','y','Yes','yes','TRUE','True','true')",
            "{} breaks are repeated.",
            [c["repeat"]],
        )

    # =====================================================
    # 13. AUTOMATION ANALYTICS
    # =====================================================

    if "confidence" in q:
        need("confidence")
        confidence_col = c["confidence"]

        if "average" in q:
            return scalar(
                f"SELECT ROUND(AVG({confidence_col}), 3) "
                f"FROM {TABLE}",
                "Average auto-match confidence is {}.",
                [confidence_col],
            )

        if "categor" in q and "category" in c:
            need("category")

            return table_result(
                f"SELECT {c['category']}, "
                f"ROUND(AVG({confidence_col}), 3) "
                f"FROM {TABLE} GROUP BY 1 ORDER BY 2 ASC",
                "Average auto-match confidence by category "
                "(lowest first):",
            )

        return scalar(
            f"SELECT COUNT(*) FROM {TABLE} "
            f"WHERE {confidence_col} < "
            f"(SELECT AVG({confidence_col}) * 0.5 "
            f"FROM {TABLE})",
            "{} breaks have low auto-match confidence "
            "(below half the average).",
            [confidence_col],
        )

    # =====================================================
    # 14. COMPLIANCE ANALYTICS
    # =====================================================

    if (
        "regulatory" in q
        or "compliance" in q
        or "reg reporting" in q
    ):
        need("reg")

        return scalar(
            f"SELECT COUNT(*) FROM {TABLE} "
            f"WHERE {c['reg']} IN "
            "(1,'1','Y','y','Yes','yes','TRUE','True','true')",
            "{} breaks affect regulatory reporting.",
            [c["reg"]],
        )

    # =====================================================
    # 15. AGED VS NON-AGED COMPARISON
    # =====================================================

    if "compare aged" in q:
        need("aged", "amount")

        return table_result(
            f"SELECT CASE WHEN {aged_true()} "
            f"THEN 'Aged' ELSE 'Not aged' END, "
            f"COUNT(*), "
            f"ROUND(SUM({c['amount']}), 2) "
            f"FROM {TABLE} GROUP BY 1",
            "Aged vs non-aged (breaks, amount):",
            value_col=1,
        )

    # =====================================================
    # 16. UNSUPPORTED QUESTIONS
    # =====================================================

    raise LookupError(
        "I can't answer that question using the available dataset. "
        "Try a question supported by your selected workspace role."
    )
