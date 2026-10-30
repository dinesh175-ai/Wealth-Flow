
"""Role-aware keyword-based knowledge retrieval."""

KNOWLEDGE = [
    # Analyst domain
    {
        "role": "analyst",
        "keys": ["aged", "old", "older", "longest", "aging"],
        "text": (
            "An aged break is a reconciliation break flagged as aged "
            "in the dataset (aged_break column)."
        ),
    },
    {
        "role": "analyst",
        "keys": ["confidence", "auto-match", "auto match", "manual"],
        "text": (
            "Auto-match confidence is the system's score for how reliably "
            "a break can be matched automatically. Low scores usually "
            "need manual review."
        ),
    },
    {
        "role": "analyst",
        "keys": ["amount", "usd", "value"],
        "text": (
            "Break amounts are taken from the amount column in USD "
            "as stored in the dataset."
        ),
    },
    {
        "role": "analyst",
        "keys": ["team", "assigned team"],
        "text": (
            "Teams are the operations teams that own the reconciliation breaks."
        ),
    },

    # Relationship Manager domain
    {
        "role": "relationship_manager",
        "keys": ["client", "customer", "portfolio", "relationship"],
        "text": (
            "Relationship Management covers client accounts, client segments, "
            "portfolio information and client exposure. These answers require "
            "corresponding client and portfolio data."
        ),
    },

    # Risk Officer domain
    {
        "role": "risk_officer",
        "keys": ["risk", "exposure", "high-risk", "high risk"],
        "text": (
            "Risk assessment evaluates financial exposure, aged breaks, "
            "high-value breaks and operational risk indicators."
        ),
    },

    # Compliance domain
    {
        "role": "compliance",
        "keys": ["regulatory", "compliance", "regulation", "audit"],
        "text": (
            "Compliance monitoring covers breaks flagged for regulatory "
            "reporting impact. Regulatory interpretations require approved "
            "policy and regulatory documents."
        ),
    },
]


def retrieve(question, role="analyst"):
    """Retrieve knowledge only from the selected role's domain."""

    role = (role or "").strip().lower()

    allowed_roles = {
        "analyst",
        "relationship_manager",
        "risk_officer",
        "compliance",
    }

    if role not in allowed_roles:
        raise PermissionError("Invalid workspace role.")

    q = (question or "").lower()

    return [
        item["text"]
        for item in KNOWLEDGE
        if item["role"] == role
        and any(word in q for word in item["keys"])
    ][:3]
