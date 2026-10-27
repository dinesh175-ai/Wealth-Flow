import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import db
import knowledge
from rules import answer_question, detect

app = FastAPI(title="WealthFlow Query Console")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"],
                   allow_methods=["*"], allow_headers=["*"])


class Ask(BaseModel):
    question: str
    role: str = "analyst"


@app.on_event("startup")
def startup():
    db.ensure_history_table()

    if os.path.exists(db.CSV_PATH):
        n, _ = db.load_csv_to_sqlite()
        print(f"Loaded {n:,} records")
    else:
        print(f"CSV file not found: {db.CSV_PATH}")
        print("History table is ready.")


@app.post("/api/ask")
def ask(body: Ask):
    try:
        res = answer_question(body.question, body.role)
        res["notes"] = knowledge.retrieve(body.question)
        db.log_history(body.role, body.question, res.get("sql", ""), res["answer"])
        return res
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except LookupError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, f"Query failed: {e}")


@app.get("/api/history")
def history():
    return db.get_history()


@app.get("/api/schema")
def schema():
    return {"columns": db.columns(), "detected": detect()}
