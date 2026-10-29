import re
from db import read_only_query, columns, TABLE

# Map logical names to possible CSV column names.
# Keep aliases in sync with the column names created by db.py.
COLUMN_ALIASES = {
    "aged": ["aged_break", "is_aged", "aged"],
    "amount": ["break_amount_usd", "amount_usd", "break_amount", "amount"],
    "team": ["team", "assigned_team", "owner_team"],
    "category": ["category", "break_category", "recon_category", "reconciliation_category"],
    "priority": ["priority"],
    "confidence": [
        "auto_match_confidence_score",
        "auto_match_confidence",
        "match_confidence",
        "auto_match_score",
    ],
    "age_days": ["age_days", "break_age_days", "days_open", "aging_days"],
    "repeat": ["repeat_break", "is_repeat", "repeated"],
    "reg": [
        "regulatory_reporting_impacted",
        "regulatory_impact",
        "regulatory_reporting",
        "reg_reporting_impact",
    ],
}

# Logical fields each role is not allowed to query.
ROLE_BLOCKED = {
    "analyst": set(),
    "relationship_manager": {"amount"},
    "viewer": {"amount", "confidence"},
}


def detect():
    """Match logical fields to columns that actually exist in the database."""
    available = set(columns())
    found = {}
    for logical, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in available:
                found[logical] = alias
                break
    return found


def check_permission(role, needed):
    role = (role or "analyst").strip().lower()
    blocked = ROLE_BLOCKED.get(role, set())
    denied = [name for name in needed if name in blocked]
    if denied:
        raise PermissionError(
            f"Your role '{role}' cannot access: {', '.join(denied)}."
        )


def fmt(value):
    if isinstance(value, float):
        return f"{value:,.2f}"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def run(sql, params=()):
    """Execute a read-only SQL query through db.py."""
    return read_only_query(sql, params)


def answer_question(question, role="analyst"):
    """Answer supported finance-operations questions using local SQL rules."""
    q = re.sub(r"\s+", " ", (question or "").lower().strip())
    c = detect()

    def need(*names):
        missing = [name for name in names if name not in c]
        if missing:
            raise LookupError(
                f"The dataset has no column matching: {', '.join(missing)}. "
                f"Update COLUMN_ALIASES in rules.py. "
                f"Available columns: {', '.join(columns())}"
            )
        check_permission(role, names)

    def table_result(
        sql, title, label_col=0, value_col=1, chart=True, params=()
    ):
        result_columns, rows = run(sql, params)
        body = "\n".join(
            " | ".join(fmt(value) for value in row) for row in rows[:15]
        )
        answer = title if not body else f"{title}\n{body}"
        result = {
            "answer": answer,
            "sql": sql,
            "columns": result_columns,
            "rows": rows,
        }
        if chart and rows and len(rows[0]) > max(label_col, value_col):
            result["chart"] = [
                {"label": str(row[label_col]), "value": row[value_col]}
                for row in rows[:15]
            ]
        return result

    def scalar(sql, template, fields, params=()):
        _, rows = run(sql, params)
        value = rows[0][0] if rows else 0
        return {
            "answer": template.format(fmt(value if value is not None else 0)),
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

    # ---- basic dataset questions ----
    if (
        "how many columns" in q
        or "columns are available" in q
        or "what columns" in q
    ):
        available_columns = columns()
        return {
            "answer": (
                f"The dataset has {len(available_columns)} columns: "
                f"{', '.join(available_columns)}"
            ),
            "sql": "PRAGMA table_info(breaks)",
            "fields": available_columns,
        }

    if (
        re.search(r"\bhow many (total )?(reconciliation )?breaks\b", q)
        and "aged" not in q
        and "team" not in q
    ):
        return scalar(
            f"SELECT COUNT(*) FROM {TABLE}",
            "There are {} reconciliation breaks.",
            ["all rows"],
        )

    if "percentage" in q and "aged" in q and "amount" not in q:
        need("aged")
        return scalar(
            f"SELECT ROUND(100.0 * SUM({aged_true()}) / COUNT(*), 2) "
            f"FROM {TABLE}",
            "{}% of breaks are aged.",
            [c["aged"]],
        )

    if "percentage" in q and "amount" in q and "aged" in q:
        need("aged", "amount")
        return scalar(
            f"SELECT ROUND(100.0 * SUM(CASE WHEN {aged_true()} "
            f"THEN {c['amount']} ELSE 0 END) / "
            f"NULLIF(SUM({c['amount']}), 0), 2) FROM {TABLE}",
            "{}% of the total break amount comes from aged breaks.",
            [c["aged"], c["amount"]],
        )

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

    if "average break amount" in q or "average amount" in q:
        need("amount")
        return scalar(
            f"SELECT ROUND(AVG({c['amount']}), 2) FROM {TABLE}",
            "The average break amount is USD {}.",
            [c["amount"]],
        )

    if "smallest" in q and ("amount" in q or "break" in q):
        need("amount")
        return scalar(
            f"SELECT MIN({c['amount']}) FROM {TABLE}",
            "The smallest break amount is USD {}.",
            [c["amount"]],
        )

    threshold_match = re.search(r"greater than \$?([\d,]+(?:\.\d+)?)", q)
    if threshold_match and "amount" in q:
        need("amount")
        threshold = float(threshold_match.group(1).replace(",", ""))
        return scalar(
            f"SELECT COUNT(*) FROM {TABLE} WHERE {c['amount']} > ?",
            f"{{}} breaks have an amount greater than ${threshold:,.2f}.",
            [c["amount"]],
            (threshold,),
        )

    if "different" in q and "categor" in q:
        need("category")
        return table_result(
            f"SELECT {c['category']}, COUNT(*) FROM {TABLE} "
            "GROUP BY 1 ORDER BY 2 DESC",
            "Reconciliation categories (with break counts):",
        )

    # ---- team-wise questions ----
    # Handle team questions before generic top-N questions.
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
                " LIMIT 5" if re.search(r"\btop\s*(5|five)\b", q) else ""
            )
            return table_result(
                f"SELECT {team_col}, ROUND(SUM({c['amount']}), 2) "
                f"FROM {TABLE} GROUP BY 1 ORDER BY 2 DESC{limit_clause}",
                "Total break amount by team (USD):",
            )

        if "lowest" in q:
            return table_result(
                f"SELECT {team_col}, COUNT(*) FROM {TABLE} "
                "GROUP BY 1 ORDER BY 2 ASC LIMIT 1",
                "Team with the lowest number of breaks:",
            )

        if "compare" in q:
            extra = (
                f", ROUND(SUM({c['amount']}), 2)"
                if "amount" in c and not (
                    role in ("relationship_manager", "viewer")
                )
                else ""
            )
            return table_result(
                f"SELECT {team_col}, COUNT(*){extra} FROM {TABLE} "
                "GROUP BY 1 ORDER BY 2 DESC",
                "Team comparison (breaks, amount):",
            )

        limit_clause = " LIMIT 1" if "highest" in q or "most" in q else ""
        return table_result(
            f"SELECT {team_col}, COUNT(*) FROM {TABLE} "
            f"GROUP BY 1 ORDER BY 2 DESC{limit_clause}",
            "Breaks by team:",
        )

    # ---- top-N largest breaks ----
    # Supports "top1", "top 1", "top 5", "top ten", and "top 10".
    number_words = {
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
        "ten": 10,
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

        # Keep accidental or overly large requests bounded.
        limit = max(1, min(limit, 100))
        return table_result(
            f"SELECT * FROM {TABLE} "
            f"ORDER BY {c['amount']} DESC LIMIT {limit}",
            f"Top {limit} largest reconciliation breaks by amount:",
            chart=False,
        )

    # "Largest reconciliation break" without a top-N count means the single
    # largest record. A request for "largest amount" can return the max value.
    if "largest" in q and "amount" in q:
        need("amount")
        return scalar(
            f"SELECT MAX({c['amount']}) FROM {TABLE}",
            "The largest break amount is USD {}.",
            [c["amount"]],
        )

    if "largest" in q and ("break" in q or "reconciliation" in q):
        need("amount")
        return table_result(
            f"SELECT * FROM {TABLE} ORDER BY {c['amount']} DESC LIMIT 1",
            "The largest reconciliation break by amount:",
            chart=False,
        )

    # ---- categories and priority ----
    if "categor" in q and ("amount" in q or "contribute" in q):
        need("category", "amount")
        return table_result(
            f"SELECT {c['category']}, ROUND(SUM({c['amount']}), 2) "
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

    # ---- risk and age ----
    age_match = re.search(r"older than (\d+) days", q)
    if age_match:
        need("age_days")
        days = int(age_match.group(1))
        return scalar(
            f"SELECT COUNT(*) FROM {TABLE} WHERE {c['age_days']} > ?",
            f"{{}} breaks are older than {days} days.",
            [c["age_days"]],
            (days,),
        )

    if "longest" in q or ("unresolved" in q and "time" in q):
        need("age_days")
        return table_result(
            f"SELECT * FROM {TABLE} ORDER BY {c['age_days']} DESC LIMIT 10",
            "Ten longest-open breaks:",
            chart=False,
        )

    if "repeated" in q or "repeat" in q:
        need("repeat")
        return scalar(
            f"SELECT COUNT(*) FROM {TABLE} WHERE {c['repeat']} IN "
            "(1,'1','Y','y','Yes','yes','TRUE','True','true')",
            "{} breaks are repeated.",
            [c["repeat"]],
        )

    # ---- automation ----
    if "confidence" in q:
        need("confidence")
        confidence_col = c["confidence"]

        if "average" in q:
            return scalar(
                f"SELECT ROUND(AVG({confidence_col}), 3) FROM {TABLE}",
                "Average auto-match confidence is {}.",
                [confidence_col],
            )

        if "categor" in q and "category" in c:
            return table_result(
                f"SELECT {c['category']}, ROUND(AVG({confidence_col}), 3) "
                f"FROM {TABLE} GROUP BY 1 ORDER BY 2 ASC",
                "Average auto-match confidence by category (lowest first):",
            )

        return scalar(
            f"SELECT COUNT(*) FROM {TABLE} WHERE {confidence_col} < "
            f"(SELECT AVG({confidence_col}) * 0.5 FROM {TABLE})",
            "{} breaks have low auto-match confidence (below half the average).",
            [confidence_col],
        )

    # ---- regulatory and compliance ----
    if "regulatory" in q or "compliance" in q:
        need("reg")
        return scalar(
            f"SELECT COUNT(*) FROM {TABLE} WHERE {c['reg']} IN "
            "(1,'1','Y','y','Yes','yes','TRUE','True','true')",
            "{} breaks affect regulatory reporting.",
            [c["reg"]],
        )

    # ---- aged versus non-aged comparison ----
    if "compare aged" in q:
        need("aged", "amount")
        return table_result(
            f"SELECT CASE WHEN {aged_true()} THEN 'Aged' ELSE 'Not aged' END, "
            f"COUNT(*), ROUND(SUM({c['amount']}), 2) FROM {TABLE} GROUP BY 1",
            "Aged vs non-aged (breaks, amount):",
            value_col=1,
        )

    raise LookupError(
        "I can't answer that yet. Try: 'How many aged breaks are there?' "
        "or 'Which team has the highest number of breaks?' "
        "or 'What are the top 5 largest reconciliation breaks?'"
    )
