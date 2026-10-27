import { useEffect, useRef, useState } from "react";

const API = "https://wealthflow-query-console.onrender.com";

const SAMPLES = [
  "How many aged breaks are there?",
  "What is the total break amount in USD?",
  "Which team has the highest number of breaks?",
  "What percentage of breaks are aged?",
  "Show the top ten largest reconciliation breaks.",
  "Compare aged and non-aged breaks.",
];

function Bars({ data = [] }) {
  if (!data.length) return null;

  const max = Math.max(
    ...data.map((item) => Number(item.value) || 0),
    1
  );

  return (
    <div className="bars">
      {data.map((item, index) => (
        <div className="bar-row" key={`${item.label}-${index}`}>
          <span className="bar-label">{item.label}</span>
          <span className="bar-track">
            <span
              className="bar-fill"
              style={{
                width: `${(100 * (Number(item.value) || 0)) / max}%`,
              }}
            />
          </span>
          <span className="bar-value">
            {(Number(item.value) || 0).toLocaleString()}
          </span>
        </div>
      ))}
    </div>
  );
}

function Message({ m }) {
  if (m.role === "user") {
    return <div className="msg user">{m.text}</div>;
  }

  const result = m.result || {};

  return (
    <div className={`msg bot ${m.error ? "error" : ""}`}>
      <pre className="answer">
        {m.error || result.answer || "No answer was returned."}
      </pre>

      {result.chart && <Bars data={result.chart} />}

      {Array.isArray(result.notes) && result.notes.length > 0 && (
        <ul className="notes">
          {result.notes.map((note, index) => (
            <li key={index}>{note}</li>
          ))}
        </ul>
      )}

      {result.sql && (
        <details className="source">
          <summary>View source SQL</summary>
          {result.fields && (
            <p>Fields used: {result.fields.join(", ")}</p>
          )}
          <code>{result.sql}</code>
        </details>
      )}
    </div>
  );
}

export default function App() {
  const [messages, setMessages] = useState([]);
  const [text, setText] = useState("");
  const [role, setRole] = useState("analyst");
  const [history, setHistory] = useState([]);
  const [busy, setBusy] = useState(false);
  const [activePage, setActivePage] = useState("chat");
  const [error, setError] = useState("");
  const end = useRef(null);

  async function parseResponse(response) {
    const contentType = response.headers.get("content-type") || "";

    if (!contentType.includes("application/json")) {
      const responseText = await response.text();

      throw new Error(
        `Server error (${response.status}). ${
          responseText.slice(0, 160) || "Unexpected server response."
        }`
      );
    }

    const data = await response.json();

    if (!response.ok) {
      throw new Error(
        data.detail || data.error || `Request failed: ${response.status}`
      );
    }

    return data;
  }

  async function loadHistory() {
    try {
      const response = await fetch(`${API}/api/history`);
      const data = await parseResponse(response);

      const items = Array.isArray(data)
        ? data
        : data.history || data.items || [];

      setHistory(items);
    } catch (err) {
      console.error("History loading failed:", err);
    }
  }

  useEffect(() => {
    loadHistory();
  }, []);

  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  async function ask(query) {
    const question = (query ?? text).trim();

    if (!question || busy) return;

    setError("");
    setText("");
    setActivePage("chat");
    setBusy(true);

    setMessages((previous) => [
      ...previous,
      { role: "user", text: question },
    ]);

    try {
      const response = await fetch(`${API}/api/ask`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          question,
          role,
        }),
      });

      const data = await parseResponse(response);

      setMessages((previous) => [
        ...previous,
        {
          role: "bot",
          result: data,
        },
      ]);

      await loadHistory();
    } catch (err) {
      const message =
        err.message ||
        "Unable to contact the backend. Please try again.";

      setError(message);

      setMessages((previous) => [
        ...previous,
        {
          role: "bot",
          error: message,
        },
      ]);
    } finally {
      setBusy(false);
    }
  }

  function newChat() {
    setMessages([]);
    setText("");
    setError("");
    setActivePage("chat");
  }

  function openHistoryItem(item) {
    const question = item.question || item.query || "";
    const answer = item.answer || item.response || "";

    if (!question) return;

    setMessages([
      { role: "user", text: question },
      ...(answer
        ? [{ role: "bot", result: { answer, sql: item.sql || "" } }]
        : []),
    ]);

    setError("");
    setActivePage("chat");
  }

  function exportResults() {
    const rows = messages
      .filter((message) => message.role === "bot")
      .map((message) => ({
        question: "",
        answer: message.error || message.result?.answer || "",
        sql: message.result?.sql || "",
      }));

    if (rows.length === 0) {
      setError("There are no answers to export yet.");
      setActivePage("chat");
      return;
    }

    const escapeCsv = (value) =>
      `"${String(value ?? "").replace(/"/g, '""')}"`;

    const csv = [
      ["Answer", "SQL"].map(escapeCsv).join(","),
      ...rows.map((row) =>
        [row.answer, row.sql].map(escapeCsv).join(",")
      ),
    ].join("\r\n");

    const blob = new Blob(["\uFEFF", csv], {
      type: "text/csv;charset=utf-8;",
    });

    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");

    link.href = url;
    link.download = "wealthflow-query-results.csv";
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);

    setError("");
  }

  return (
    <div className="layout">
      <aside className="side">
        <h1>WealthFlow Query Console</h1>

        <label>
          Role
          <select
            value={role}
            onChange={(event) => setRole(event.target.value)}
          >
            <option value="analyst">Analyst</option>
            <option value="relationship_manager">
              Relationship manager
            </option>
            <option value="viewer">Viewer</option>
          </select>
        </label>

        <h2>Navigation</h2>

        <button className="chip" onClick={newChat}>
          + New conversation
        </button>

        <button
          className="chip"
          onClick={() => {
            setActivePage("chat");
            setError("");
          }}
        >
          Query Console
        </button>

        <button
          className="chip"
          onClick={() => {
            setActivePage("history");
            setError("");
            loadHistory();
          }}
        >
          Query History ({history.length})
        </button>

        <button
          className="chip"
          onClick={() => {
            setActivePage("export");
            setError("");
          }}
        >
          Export Results
        </button>

        <h2>Try asking</h2>

        {SAMPLES.map((sample) => (
          <button
            key={sample}
            className="chip"
            onClick={() => ask(sample)}
            disabled={busy}
          >
            {sample}
          </button>
        ))}

        <h2>Recent queries</h2>

        {history.length === 0 ? (
          <p className="empty">No saved queries yet.</p>
        ) : (
          <ul className="history">
            {history.slice(0, 10).map((item, index) => (
              <li
                key={item.id ?? item.ts ?? index}
                onClick={() => openHistoryItem(item)}
                title={item.ts || item.created_at || ""}
                style={{ cursor: "pointer" }}
              >
                {item.question || item.query || "Previous query"}
              </li>
            ))}
          </ul>
        )}
      </aside>

      <main className="chat">
        <header className="page-header">
          <h2>
            {activePage === "chat"
              ? "Query Console"
              : activePage === "history"
              ? "Query History"
              : "Export Results"}
          </h2>
          <p>Financial operations intelligence</p>
        </header>

        {error && (
          <div className="msg bot error" role="alert">
            {error}
            <button onClick={() => setError("")}>Dismiss</button>
          </div>
        )}

        {activePage === "chat" && (
          <>
            <div className="feed">
              {messages.length === 0 && (
                <div className="empty">
                  <h2>Welcome to WealthFlow</h2>
                  <p>
                    Ask a question about reconciliation data in plain English.
                  </p>
                </div>
              )}

              {messages.map((message, index) => (
                <Message key={index} m={message} />
              ))}

              {busy && (
                <div className="msg bot">
                  Analyzing your question…
                </div>
              )}

              <div ref={end} />
            </div>

            <form
              className="composer"
              onSubmit={(event) => {
                event.preventDefault();
                ask();
              }}
            >
              <input
                value={text}
                onChange={(event) => setText(event.target.value)}
                placeholder="e.g. How many aged breaks are there?"
                disabled={busy}
              />

              <button type="submit" disabled={busy || !text.trim()}>
                {busy ? "Running…" : "Ask"}
              </button>
            </form>
          </>
        )}

        {activePage === "history" && (
          <section className="feed">
            <h2>Query History</h2>

            <button className="chip" onClick={loadHistory}>
              Refresh history
            </button>

            {history.length === 0 ? (
              <p className="empty">
                No saved queries found. Submit a query first.
              </p>
            ) : (
              <ul className="history">
                {history.map((item, index) => (
                  <li
                    key={item.id ?? item.ts ?? index}
                    onClick={() => openHistoryItem(item)}
                    style={{ cursor: "pointer", marginBottom: "12px" }}
                  >
                    <strong>
                      {item.question || item.query || "Previous query"}
                    </strong>
                    <br />
                    <span>
                      {item.ts || item.created_at || ""}
                    </span>
                    {item.answer && <p>{item.answer}</p>}
                  </li>
                ))}
              </ul>
            )}
          </section>
        )}

        {activePage === "export" && (
          <section className="feed">
            <h2>Export Results</h2>
            <p>
              Download answers and SQL queries from this conversation as a CSV
              file that you can open in Excel.
            </p>

            <button className="chip" onClick={exportResults}>
              Download CSV
            </button>
          </section>
        )}
      </main>
    </div>
  );
}