import re
from db import read_only_query, columns, TABLE

# Map logical names to possible CSV column names. Edit these to match your file.
COLUMN_ALIASES = {
    "aged": ["aged_break", "is_aged", "aged"],
    "amount": ["break_amount_usd", "amount_usd", "break_amount", "amount"],
    "team": ["team", "assigned_team", "owner_team"],
    "category": ["category", "break_category", "recon_category", "reconciliation_category"],
    "priority": ["priority"],
    "confidence": ["auto_match_confidence", "match_confidence", "auto_match_score"],
    "age_days": ["age_days", "break_age_days", "days_open", "aging_days"],
    "repeat": ["repeat_break", "is_repeat", "repeated"],
    "reg": ["regulatory_impact", "regulatory_reporting", "reg_reporting_impact"],
}

# Role-based access: columns each role may NOT query.
ROLE_BLOCKED = {
    "analyst": set(),
    "relationship_manager": {"amount"},   # example restriction
    "viewer": {"amount", "confidence"},
}


def detect():
    cols = columns()
    found = {}
    for logical, names in COLUMN_ALIASES.items():
        for n in names:
            if n in cols:
                found[logical] = n
                break
    return found


def check_permission(role, needed):
    blocked = ROLE_BLOCKED.get(role, set())
    hit = [n for n in needed if n in blocked]
    if hit:
        raise PermissionError(f"Your role '{role}' cannot access: {', '.join(hit)}.")


def fmt(v):
    if isinstance(v, float):
        return f"{v:,.2f}"
    if isinstance(v, int):
        return f"{v:,}"
    return str(v)


def run(sql, params=()):
    return read_only_query(sql, params)


def answer_question(question, role="analyst"):
    """Steps 3-6. Returns dict: answer, sql, columns, rows, chart, fields."""
    q = question.lower().strip()
    c = detect()

    def need(*names):
        missing = [n for n in names if n not in c]
        if missing:
            raise LookupError(
                f"The dataset has no column matching: {', '.join(missing)}. "
                f"Update COLUMN_ALIASES in rules.py. Available: {', '.join(columns())}"
            )
        check_permission(role, names)

    def table_result(sql, title, label_col=0, value_col=1, chart=True, params=()):
        cols, rows = run(sql, params)
        text = title + "\n" + "\n".join(" | ".join(fmt(x) for x in r) for r in rows[:15])
        out = {"answer": text, "sql": sql, "columns": cols, "rows": rows}
        if chart and rows:
            out["chart"] = [{"label": str(r[label_col]), "value": r[value_col]} for r in rows[:15]]
        return out

    def scalar(sql, template, fields, params=()):
        _, rows = run(sql, params)
        v = rows[0][0]
        return {"answer": template.format(fmt(v if v is not None else 0)),
                "sql": sql, "fields": fields, "columns": ["value"], "rows": rows}

    aged_true = lambda: f"({c['aged']} IN (1,'1','Y','Yes','yes','TRUE','True','true'))"

    # ---- basic ----
    if "how many columns" in q or "columns are available" in q:
        cols = columns()
        return {"answer": f"The dataset has {len(cols)} columns: {', '.join(cols)}",
                "sql": "PRAGMA table_info(breaks)", "fields": cols}

    if re.search(r"how many (total )?(reconciliation )?breaks", q) and "aged" not in q and "team" not in q:
        return scalar(f"SELECT COUNT(*) FROM {TABLE}", "There are {} reconciliation breaks.", ["all rows"])

    if "percentage" in q and "aged" in q and "amount" not in q:
        need("aged")
        return scalar(f"SELECT ROUND(100.0*SUM({aged_true()})/COUNT(*),2) FROM {TABLE}",
                      "{}% of breaks are aged.", [c["aged"]])

    if "percentage" in q and "amount" in q and "aged" in q:
        need("aged", "amount")
        return scalar(f"SELECT ROUND(100.0*SUM(CASE WHEN {aged_true()} THEN {c['amount']} ELSE 0 END)/SUM({c['amount']}),2) FROM {TABLE}",
                      "{}% of the total break amount comes from aged breaks.", [c["aged"], c["amount"]])

    if "aged" in q and ("how many" in q or "count" in q or "number" in q) and "team" not in q:
        need("aged")
        return scalar(f"SELECT COUNT(*) FROM {TABLE} WHERE {aged_true()}",
                      "There are {} aged breaks.", [c["aged"]])

    if ("total break amount" in q or "total amount" in q) and "team" not in q and "each" not in q:
        need("amount")
        return scalar(f"SELECT ROUND(SUM({c['amount']}),2) FROM {TABLE}",
                      "The total break amount is USD {}.", [c["amount"]])

    if "average break amount" in q or "average amount" in q:
        need("amount")
        return scalar(f"SELECT ROUND(AVG({c['amount']}),2) FROM {TABLE}",
                      "The average break amount is USD {}.", [c["amount"]])

    if "largest" in q and "amount" in q and "top" not in q:
        need("amount")
        return scalar(f"SELECT MAX({c['amount']}) FROM {TABLE}", "The largest break is USD {}.", [c["amount"]])

    if "smallest" in q and "amount" in q:
        need("amount")
        return scalar(f"SELECT MIN({c['amount']}) FROM {TABLE}", "The smallest break is USD {}.", [c["amount"]])

    m = re.search(r"greater than \$?([\d,]+)", q)
    if m and "amount" in q:
        need("amount")
        n = float(m.group(1).replace(",", ""))
        return scalar(f"SELECT COUNT(*) FROM {TABLE} WHERE {c['amount']} > ?",
                      f"{{}} breaks have an amount greater than ${n:,.0f}.", [c["amount"]], (n,))

    if "different" in q and "categor" in q:
        need("category")
        return table_result(f"SELECT {c['category']}, COUNT(*) FROM {TABLE} GROUP BY 1 ORDER BY 2 DESC",
                            "Reconciliation categories (with break counts):")

    # ---- team-wise ----
    if "team" in q:
        need("team")
        t = c["team"]
        if "aged" in q:
            need("aged")
            return table_result(f"SELECT {t}, COUNT(*) FROM {TABLE} WHERE {aged_true()} GROUP BY 1 ORDER BY 2 DESC",
                                "Aged breaks by team:")
        if "amount" in q:
            need("amount")
            lim = " LIMIT 5" if "top five" in q or "top 5" in q else ""
            return table_result(f"SELECT {t}, ROUND(SUM({c['amount']}),2) FROM {TABLE} GROUP BY 1 ORDER BY 2 DESC{lim}",
                                "Total break amount by team (USD):")
        if "lowest" in q:
            return table_result(f"SELECT {t}, COUNT(*) FROM {TABLE} GROUP BY 1 ORDER BY 2 ASC LIMIT 1",
                                "Team with the lowest number of breaks:")
        if "compare" in q:
            extra = f", ROUND(SUM({c['amount']}),2)" if "amount" in c else ""
            return table_result(f"SELECT {t}, COUNT(*){extra} FROM {TABLE} GROUP BY 1 ORDER BY 2 DESC",
                                "Team comparison (breaks, amount):")
        lim = " LIMIT 1" if "highest" in q else ""
        return table_result(f"SELECT {t}, COUNT(*) FROM {TABLE} GROUP BY 1 ORDER BY 2 DESC{lim}",
                            "Breaks by team:")

    # ---- categories / priority ----
    if "categor" in q and ("amount" in q or "contribute" in q):
        need("category", "amount")
        return table_result(f"SELECT {c['category']}, ROUND(SUM({c['amount']}),2) FROM {TABLE} GROUP BY 1 ORDER BY 2 DESC",
                            "Total break amount by category (USD):")

    if "priority" in q:
        need("priority")
        return table_result(f"SELECT {c['priority']}, COUNT(*) FROM {TABLE} GROUP BY 1 ORDER BY 2 DESC",
                            "Breaks by priority:")

    # ---- risk / age ----
    m = re.search(r"older than (\d+) days", q)
    if m:
        need("age_days")
        return scalar(f"SELECT COUNT(*) FROM {TABLE} WHERE {c['age_days']} > ?",
                      f"{{}} breaks are older than {m.group(1)} days.", [c["age_days"]], (int(m.group(1)),))

    if "longest" in q or "unresolved" in q and "time" in q:
        need("age_days")
        return table_result(f"SELECT * FROM {TABLE} ORDER BY {c['age_days']} DESC LIMIT 10",
                            "Ten longest-open breaks:", chart=False)

    if "repeated" in q or "repeat" in q:
        need("repeat")
        return scalar(f"SELECT COUNT(*) FROM {TABLE} WHERE {c['repeat']} IN (1,'1','Y','Yes','TRUE','True','true')",
                      "{} breaks are repeated.", [c["repeat"]])

    # ---- automation ----
    if "confidence" in q:
        need("confidence")
        cf = c["confidence"]
        if "average" in q:
            return scalar(f"SELECT ROUND(AVG({cf}),3) FROM {TABLE}", "Average auto-match confidence is {}.", [cf])
        if "categor" in q and "category" in c:
            return table_result(f"SELECT {c['category']}, ROUND(AVG({cf}),3) FROM {TABLE} GROUP BY 1 ORDER BY 2 ASC",
                                "Average auto-match confidence by category (lowest first):")
        return scalar(f"SELECT COUNT(*) FROM {TABLE} WHERE {cf} < (SELECT AVG({cf})*0.5 FROM {TABLE})",
                      "{} breaks have low auto-match confidence (below half the average).", [cf])

    # ---- regulatory ----
    if "regulatory" in q or "compliance" in q:
        need("reg")
        return scalar(f"SELECT COUNT(*) FROM {TABLE} WHERE {c['reg']} IN (1,'1','Y','Yes','TRUE','True','true')",
                      "{} breaks affect regulatory reporting.", [c["reg"]])

    # ---- advanced ----
    if "top ten" in q or "top 10" in q:
        need("amount")
        return table_result(f"SELECT * FROM {TABLE} ORDER BY {c['amount']} DESC LIMIT 10",
                            "Ten largest breaks:", chart=False)

    if "compare aged" in q:
        need("aged", "amount")
        return table_result(f"SELECT CASE WHEN {aged_true()} THEN 'Aged' ELSE 'Not aged' END, COUNT(*), ROUND(SUM({c['amount']}),2) FROM {TABLE} GROUP BY 1",
                            "Aged vs non-aged (breaks, amount):", value_col=1)

    raise LookupError("I can't answer that yet. Try: 'How many aged breaks are there?' or 'Which team has the highest number of breaks?'")
