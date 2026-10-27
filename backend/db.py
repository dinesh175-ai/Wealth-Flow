
import os
import sqlite3
import pandas as pd

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE, "data")
CSV_PATH = os.path.join(DATA_DIR, "finance_operations_01.csv")
DB_PATH = os.path.join(BASE, "wealthflow.db")
TABLE = "breaks"


def ensure_history_table():
    """Create the history table even if the CSV is unavailable."""
    with sqlite3.connect(DB_PATH) as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT DEFAULT CURRENT_TIMESTAMP,
                role TEXT,
                question TEXT,
                sql TEXT,
                answer TEXT
            )
        """)


def load_csv_to_sqlite():
    """Load finance operations CSV into SQLite."""
    if not os.path.exists(CSV_PATH):
        raise FileNotFoundError(f"CSV file not found: {CSV_PATH}")

    df = pd.read_csv(CSV_PATH)
    df.columns = [
        str(c).strip().lower().replace(" ", "_")
        for c in df.columns
    ]

    with sqlite3.connect(DB_PATH) as con:
        df.to_sql(TABLE, con, if_exists="replace", index=False)

    ensure_history_table()
    return len(df), list(df.columns)


def read_only_query(sql, params=()):
    """Execute SELECT queries only."""
    if not sql.strip().lower().startswith("select"):
        raise ValueError("Only SELECT queries are allowed.")

    con = sqlite3.connect(
        f"file:{DB_PATH}?mode=ro",
        uri=True
    )
    try:
        cur = con.execute(sql, params)
        cols = [d[0] for d in cur.description]
        return cols, cur.fetchall()
    finally:
        con.close()


def columns():
    if not os.path.exists(DB_PATH):
        return []

    con = sqlite3.connect(DB_PATH)
    try:
        return [
            row[1]
            for row in con.execute(
                f"PRAGMA table_info({TABLE})"
            )
        ]
    finally:
        con.close()


def log_history(role, question, sql, answer):
    ensure_history_table()

    with sqlite3.connect(DB_PATH) as con:
        con.execute(
            """
            INSERT INTO history (role, question, sql, answer)
            VALUES (?, ?, ?, ?)
            """,
            (role, question, sql, answer),
        )


def get_history(limit=50):
    ensure_history_table()

    with sqlite3.connect(DB_PATH) as con:
        rows = con.execute(
            """
            SELECT ts, role, question, answer
            FROM history
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [
        {
            "ts": row[0],
            "role": row[1],
            "question": row[2],
            "answer": row[3],
        }
        for row in rows
    ]
