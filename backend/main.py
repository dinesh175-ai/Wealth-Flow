
import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI

import db
import knowledge
from rules import answer_question, detect


# Load environment variables from this backend folder's .env file
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE_DIR, ".env")
load_dotenv(ENV_PATH, override=True)

API_KEY = os.getenv("GROQ_API_KEY", "").strip()
MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b").strip()

CHUNK_MAX_CHARS = int(os.getenv("CHUNK_MAX_CHARS", "60000"))

# Groq supports the OpenAI-compatible Python client
client = (
    OpenAI(
        api_key=API_KEY,
        base_url="https://api.groq.com/openai/v1",
    )
    if API_KEY and not API_KEY.startswith("YOUR_")
    else None
)

app = FastAPI(title="WealthFlow Query Console")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


class Ask(BaseModel):
    question: str
    role: str = "analyst"


def interpret_question(question: str) -> str:
    """Rewrite unsupported question wording for the local rules engine."""

    if client is None:
        raise LookupError(
            "Groq AI is not configured. Add GROQ_API_KEY to backend/.env."
        )

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You interpret questions about reconciliation breaks. "
                    "Do not answer the financial question and do not generate SQL. "
                    "Rewrite the user's question into one short, clear question "
                    "for a local analytics rules engine. Preserve the requested "
                    "metric, ranking, filters, and number of results. "
                    "For largest break amounts, use wording such as "
                    "'Show the top 1 largest breaks by amount'. "
                    "For top-N requests, preserve the requested number N. "
                    "Return only the rewritten question."
                ),
            },
            {"role": "user", "content": question},
        ],
        temperature=0,
    )

    rewritten = response.choices[0].message.content

    if not rewritten:
        raise LookupError("Groq could not interpret this question.")

    return rewritten.strip()


@app.on_event("startup")
def startup():
    db.ensure_history_table()

    if os.path.exists(db.CSV_PATH):
        n, _ = db.load_csv_to_sqlite()
        print(f"Loaded {n:,} records")
    else:
        print(f"CSV file not found: {db.CSV_PATH}")
        print("History table is ready.")

    print(f"Groq configured: {client is not None}")
    print(f"Groq model: {MODEL}")
    print(f"Chunk maximum characters: {CHUNK_MAX_CHARS}")


@app.post("/api/ask")
def ask(body: Ask):
    try:
        question = body.question.strip()

        if not question:
            raise HTTPException(
                status_code=400,
                detail="Please enter a question.",
            )

        # Try local rules first; supported questions need no API call.
        try:
            res = answer_question(question, body.role)

        except LookupError:
            # Use Groq only when the local rules engine cannot interpret
            # the question. Financial results are still calculated locally.
            rewritten = interpret_question(question)
            res = answer_question(rewritten, body.role)
            res["interpreted_question"] = rewritten

        res["notes"] = knowledge.retrieve(question)

        db.log_history(
            body.role,
            question,
            res.get("sql", ""),
            res["answer"],
        )

        return res

    except HTTPException:
        raise

    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))

    except Exception as e:
        print(f"Query error: {type(e).__name__}: {e}")
        raise HTTPException(
            status_code=500,
            detail=(
                "The query failed. Check the backend terminal, "
                "Groq API key, model access, and database configuration."
            ),
        )


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "groq_configured": client is not None,
        "model": MODEL,
    }


@app.get("/api/history")
def history():
    return db.get_history()


@app.get("/api/schema")
def schema():
    return {
        "columns": db.columns(),
        "detected": detect(),
    }
