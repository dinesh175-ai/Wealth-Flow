"""Small keyword-based knowledge retrieval (the 'RAG' step).
Replace with a vector store if you add real policy documents."""

KNOWLEDGE = [
    {"keys": ["aged", "old", "older", "longest"],
     "text": "An aged break is a reconciliation break flagged as aged in the dataset (aged_break column)."},
    {"keys": ["confidence", "auto", "match", "manual"],
     "text": "Auto-match confidence is the system's score for how reliably a break can be matched automatically. Low scores usually need manual review."},
    {"keys": ["amount", "usd", "value"],
     "text": "Break amounts are taken from the amount column in USD as stored in the dataset."},
    {"keys": ["team"],
     "text": "Teams are the operations teams that own the reconciliation breaks."},
]


def retrieve(question):
    q = question.lower()
    return [k["text"] for k in KNOWLEDGE if any(w in q for w in k["keys"])][:3]
