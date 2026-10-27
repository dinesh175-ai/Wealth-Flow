import { useEffect, useRef, useState } from "react";

const SAMPLES = [
  "How many aged breaks are there?",
  "What is the total break amount in USD?",
  "Which team has the highest number of breaks?",
  "What percentage of breaks are aged?",
  "Show the top ten largest reconciliation breaks.",
  "Compare aged and non-aged breaks.",
];

function Bars({ data }) {
  const max = Math.max(...data.map((d) => Number(d.value) || 0), 1);
  return (
    <div className="bars">
      {data.map((d) => (
        <div className="bar-row" key={d.label}>
          <span className="bar-label">{d.label}</span>
          <span className="bar-track">
            <span className="bar-fill" style={{ width: `${(100 * d.value) / max}%` }} />
          </span>
          <span className="bar-value">{Number(d.value).toLocaleString()}</span>
        </div>
      ))}
    </div>
  );
}

function Message({ m }) {
  if (m.role === "user") return <div className="msg user">{m.text}</div>;
  const r = m.result;
  return (
    <div className={`msg bot ${m.error ? "error" : ""}`}>
      <pre className="answer">{m.error || r.answer}</pre>
      {r?.chart && <Bars data={r.chart} />}
      {r?.notes?.length > 0 && (
        <ul className="notes">{r.notes.map((n, i) => <li key={i}>{n}</li>)}</ul>
      )}
      {r?.sql && (
        <details className="source">
          <summary>Source</summary>
          {r.fields && <p>Fields used: {r.fields.join(", ")}</p>}
          <code>{r.sql}</code>
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
  const end = useRef(null);

  const loadHistory = () =>
    fetch("/api/history").then((r) => r.json()).then(setHistory).catch(() => {});

  useEffect(() => { loadHistory(); }, []);
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  async function ask(q) {
    const question = (q ?? text).trim();
    if (!question || busy) return;
    setText("");
    setBusy(true);
    setMessages((m) => [...m, { role: "user", text: question }]);
    try {
      const res = await fetch("/api/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, role }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail);
      setMessages((m) => [...m, { role: "bot", result: data }]);
    } catch (e) {
      setMessages((m) => [...m, { role: "bot", error: e.message }]);
    }
    setBusy(false);
    loadHistory();
  }

  return (
    <div className="layout">
      <aside className="side">
        <h1>WealthFlow Query Console</h1>
        <label>
          Role
          <select value={role} onChange={(e) => setRole(e.target.value)}>
            <option value="analyst">Analyst</option>
            <option value="relationship_manager">Relationship manager</option>
            <option value="viewer">Viewer</option>
          </select>
        </label>
        <h2>Try asking</h2>
        {SAMPLES.map((s) => (
          <button key={s} className="chip" onClick={() => ask(s)}>{s}</button>
        ))}
        <h2>Query history</h2>
        <ul className="history">
          {history.slice(0, 10).map((h, i) => (
            <li key={i} onClick={() => ask(h.question)} title={h.ts}>{h.question}</li>
          ))}
        </ul>
      </aside>
      <main className="chat">
        <div className="feed">
          {messages.length === 0 && (
            <p className="empty">Ask a question about the reconciliation data, in plain English.</p>
          )}
          {messages.map((m, i) => <Message key={i} m={m} />)}
          <div ref={end} />
        </div>
        <div className="composer">
          <input
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && ask()}
            placeholder="e.g. How many aged breaks are there?"
          />
          <button onClick={() => ask()} disabled={busy}>{busy ? "Running…" : "Ask"}</button>
        </div>
      </main>
    </div>
  );
}
