# WealthFlow Query Console

Ask questions in plain English about the reconciliation dataset. No paid AI API needed:
questions are matched to predefined rules and answered with read-only SQL on SQLite.

## Structure
```
wealthflow-query-console/
├── README.md
├── backend/
│   ├── requirements.txt
│   ├── main.py          # FastAPI app (load, ask, history, schema)
│   ├── db.py            # CSV -> SQLite, read-only querying
│   ├── rules.py         # question understanding + permissions
│   ├── knowledge.py     # tiny RAG / knowledge retrieval (keyword based)
│   └── data/
│       └── finance_operations_01.csv   <-- put your dataset here
└── frontend/
    ├── package.json
    ├── vite.config.js
    ├── index.html
    └── src/
        ├── main.jsx
        ├── App.jsx
        └── styles.css
```

## Run
Backend:
```
cd backend
python -m venv venv && source venv/bin/activate     # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```
Frontend (new terminal):
```
cd frontend
npm install
npm run dev
```
Open http://localhost:5173

## Column names
The code finds columns by common names (see `COLUMN_ALIASES` in `rules.py`).
Open `http://localhost:8000/api/schema` to see what was detected, then edit the aliases to match your CSV.
