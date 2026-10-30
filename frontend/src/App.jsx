import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import "./styles.css";

// Local backend. If you deploy the frontend and backend together, change this to "".
const API = "http://127.0.0.1:8000";

const SAMPLE_QUESTIONS = [
  "How many aged breaks are there?",
  "What is the total break amount in USD?",
  "Which team has the highest number of breaks?",
  "What percentage of breaks are aged?",
  "Show the top ten largest reconciliation breaks.",
];

const ROLE_OPTIONS = [
  { value: "analyst", label: "Analyst" },
  { value: "relationship_manager", label: "Relationship Manager" },
  { value: "risk_officer", label: "Risk Officer" },
  { value: "compliance", label: "Compliance" },
];

function normaliseHistory(payload) {
  if (Array.isArray(payload)) return payload;
  if (Array.isArray(payload?.value)) return payload.value;
  if (Array.isArray(payload?.history)) return payload.history;
  if (Array.isArray(payload?.results)) return payload.results;
  return [];
}

function historyQuestion(item) {
  return item?.question ?? item?.query ?? item?.prompt ?? "Untitled query";
}

function historyAnswer(item) {
  return item?.answer ?? item?.result ?? item?.response ?? "";
}

function formatDate(value) {
  if (!value) return "Date unavailable";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? String(value)
    : date.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

function downloadHistory(rows) {
  const columns = ["date", "role", "question", "answer", "sql"];
  const escapeCsv = (value) => `"${String(value ?? "").replaceAll('"', '""')}"`;
  const csv = [
    columns.join(","),
    ...rows.map((row) =>
      columns.map((column) => escapeCsv(
        column === "date"
          ? row.ts ?? row.created_at ?? row.timestamp ?? row.date
          : column === "question"
            ? historyQuestion(row)
            : column === "answer"
              ? historyAnswer(row)
              : row[column]
      )).join(",")
    ),
  ].join("\r\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "wealthflow-query-history.csv";
  anchor.click();
  URL.revokeObjectURL(url);
}

function Brand({ compact = false }) {
  return (
    <div className={`brand ${compact ? "brand-compact" : ""}`}>
      <div className="brand-mark" aria-hidden="true">
        <svg viewBox="0 0 40 40" role="img">
          <path d="M5 27.5 13.3 19l6.2 5.4L34 9.5" />
          <path d="M25.5 9.5H34v8.5" />
          <path d="M7 32h26" className="brand-base" />
        </svg>
      </div>
      {!compact && (
        <div className="brand-copy">
          <span>WEALTHFLOW</span>
          <small>QUERY CONSOLE</small>
        </div>
      )}
    </div>
  );
}

function PageHeader({ eyebrow, title, description, action }) {
  return (
    <header className="page-header">
      <div>
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h1>{title}</h1>
        {description && <p className="page-description">{description}</p>}
      </div>
      {action && <div className="header-action">{action}</div>}
    </header>
  );
}

export default function App() {
  const [page, setPage] = useState("overview");
  const [role, setRole] = useState("analyst");
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState([]);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [error, setError] = useState("");
  const [historyError, setHistoryError] = useState("");
  const [apiStatus, setApiStatus] = useState("checking");
  const [searchHistory, setSearchHistory] = useState("");
  const [recentOnly, setRecentOnly] = useState(false);
  const inputRef = useRef(null);
  const conversationEndRef = useRef(null);

  const loadHistory = useCallback(async () => {
    setHistoryLoading(true);
    setHistoryError("");
    try {
      const response = await fetch(`${API}/api/history`);
      if (!response.ok) throw new Error(`History request failed (${response.status})`);
      const payload = await response.json();
      setHistory(normaliseHistory(payload));
    } catch (err) {
      setHistoryError(
        "Could not load query history. Check that the WealthFlow backend is running and that the frontend API URL is correct."
      );
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  useEffect(() => {
    let active = true;
    fetch(`${API}/api/health`)
  .then(async (response) => {
    const data = await response.json();

    if (active) {
      setApiStatus(
        response.ok && data.status === "ok"
          ? "online"
          : "offline"
      );
    }
  })
  .catch(() => {
    if (active) setApiStatus("offline");
  });
    loadHistory();
    return () => { active = false; };
  }, [loadHistory]);

  useEffect(() => {
    conversationEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, loading]);

  const submitQuestion = async (value = question) => {
    const cleanQuestion = value.trim();
    if (!cleanQuestion || loading) return;
    setPage("console");
    setError("");
    setQuestion("");
    setMessages((current) => [...current, { type: "user", text: cleanQuestion, id: `${Date.now()}-u` }]);
    setLoading(true);
    try {
      const response = await fetch(`${API}/api/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: cleanQuestion, role }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload.detail || payload.error || `Request failed (${response.status})`);
      }
      setMessages((current) => [
        ...current,
        {
          type: "assistant",
          text: payload.answer ?? payload.result ?? payload.response ?? "The query completed, but the backend returned no answer text.",
          sql: payload.sql,
          notes: payload.notes,
          fields: payload.fields,
          chart: payload.chart,
          id: `${Date.now()}-a`,
        },
      ]);
      await loadHistory();
    } catch (err) {
      setMessages((current) => [
        ...current,
        {
          type: "error",
          text: err.message || "Unable to contact the backend.",
          id: `${Date.now()}-e`,
        },
      ]);
      setError("Your question could not be processed. Check the backend terminal for details.");
    } finally {
      setLoading(false);
      window.setTimeout(() => inputRef.current?.focus(), 50);
    }
  };

  const filteredHistory = useMemo(() => {
    const term = searchHistory.trim().toLowerCase();
    const matching = history.filter((item) =>
      `${historyQuestion(item)} ${historyAnswer(item)} ${item?.role ?? ""}`
        .toLowerCase()
        .includes(term)
    );
    // Recent mode shows the five newest entries. This assumes the backend
    // returns history newest-first, which is the usual history ordering.
    return recentOnly ? matching.slice(0, 5) : matching;
  }, [history, searchHistory, recentOnly]);

  const openConsole = () => {
    setPage("console");
    setError("");
    window.setTimeout(() => inputRef.current?.focus(), 50);
  };

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <button className="sidebar-brand-button" onClick={() => setPage("overview")} aria-label="Go to overview">
          <Brand />
        </button>

        <div className="sidebar-section">
          <label className="sidebar-label" htmlFor="role-select">WORKSPACE ROLE</label>
          <div className="select-wrap">
            <select id="role-select" value={role} onChange={(event) => setRole(event.target.value)}>
              {ROLE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
            <span aria-hidden="true">⌄</span>
          </div>
        </div>

        <div className="sidebar-section nav-section">
          <p className="sidebar-label">WORKSPACE</p>
          <button className={`nav-link ${page === "overview" ? "active" : ""}`} onClick={() => setPage("overview")}>
            <span className="nav-icon">⌂</span><span>Project overview</span>
          </button>
          <button className={`nav-link ${page === "console" ? "active" : ""}`} onClick={openConsole}>
            <span className="nav-icon">⌘</span><span>Query Console</span>
          </button>
          <button className={`nav-link ${page === "history" ? "active" : ""}`} onClick={() => { setPage("history"); loadHistory(); }}>
            <span className="nav-icon">◷</span><span>Query History</span>
            <span className="nav-count">{history.length}</span>
          </button>
        </div>

        <div className="sidebar-status">
          <span className={`status-dot ${apiStatus}`} />
          <div>
            <strong>{apiStatus === "online" ? "Backend connected" : apiStatus === "checking" ? "Checking connection" : "Backend unavailable"}</strong>
            <small>{apiStatus === "online" ? "Ready for queries" : "Local API · port 8000"}</small>
          </div>
        </div>

        <div className="sidebar-footer">
          <span className="footer-lock">▣</span>
          <span>Financial operations intelligence</span>
        </div>
      </aside>

      <main className="main-panel">
        <div className="mobile-topbar">
          <button className="mobile-brand" onClick={() => setPage("overview")}><Brand compact /><span>WealthFlow</span></button>
          <button className="mobile-history" onClick={() => { setPage("history"); loadHistory(); }}>History</button>
        </div>

        {page === "overview" && (
          <section className="overview-page">
            <div className="overview-hero">
              <div className="hero-copy">
                <div className="hero-pill"><span className="hero-pill-dot" /> FINANCIAL OPERATIONS INTELLIGENCE</div>
                <h1>Make complex financial data <span>easy to understand.</span></h1>
                <p className="hero-description">
                  WealthFlow Query Console is a conversational analytics platform that helps financial operations teams explore reconciliation data using plain-English questions instead of writing SQL manually.
                </p>
                <div className="hero-actions">
                  <button className="primary-button" onClick={openConsole}>Open Query Console <span>↗</span></button>
                  <button className="secondary-button" onClick={() => { setPage("history"); loadHistory(); }}>View query history</button>
                </div>
                <div className="hero-trust"><span>✓</span> Designed for faster, traceable operational analysis</div>
              </div>
              <div className="hero-visual" aria-label="Illustration of financial analytics">
                <div className="visual-glow" />
                <div className="visual-card visual-card-main">
                  <div className="visual-card-top"><span>BREAK ANALYTICS</span><span className="visual-live"><i /> LIVE VIEW</span></div>
                  <div className="visual-big-number">134,464 <small>records</small></div>
                  <div className="visual-caption">Reconciliation data at a glance</div>
                  <div className="mini-chart">
                    {[38, 54, 43, 68, 48, 78, 60, 91, 66, 82, 72, 100, 76, 88, 63, 94].map((height, index) => (
                      <span key={index} style={{ height: `${height}%` }} />
                    ))}
                  </div>
                  <div className="visual-legend"><span><i className="legend-green" /> Matched trends</span><span><i className="legend-blue" /> Break analysis</span></div>
                </div>
                <div className="floating-stat"><span className="stat-icon">↗</span><div><small>INSIGHT</small><strong>Ask in plain English</strong></div></div>
                <div className="visual-orbit orbit-one" /><div className="visual-orbit orbit-two" />
              </div>
            </div>

            <div className="overview-content">
              <div className="section-intro">
                <p className="eyebrow">THE PLATFORM</p>
                <h2>From operational data to clear answers</h2>
                <p>One workspace to ask questions, understand results, and revisit the analysis that matters.</p>
              </div>
              <div className="feature-grid">
                <article className="feature-card"><div className="feature-icon purple">⌕</div><h3>Ask naturally</h3><p>Ask questions about break volumes, aged breaks, amounts, teams, and reconciliation trends in everyday language.</p><span className="feature-index">01</span></article>
                <article className="feature-card"><div className="feature-icon green">▥</div><h3>Explore operations</h3><p>Turn a large reconciliation dataset into focused answers that help teams investigate operational exceptions.</p><span className="feature-index">02</span></article>
                <article className="feature-card"><div className="feature-icon amber">◷</div><h3>Return to past queries</h3><p>Use the Query History page to revisit earlier questions and review the answers saved by the backend.</p><span className="feature-index">03</span></article>
                <article className="feature-card"><div className="feature-icon blue">⌘</div><h3>Built for teams</h3><p>Choose a workspace role for the context of your work, with a layout designed for financial operations workflows.</p><span className="feature-index">04</span></article>
              </div>

              <div className="workflow-panel">
                <div><p className="eyebrow">HOW IT WORKS</p><h2>Three simple steps</h2><p>Move from a question to a useful operational answer.</p></div>
                <div className="workflow-steps">
                  <div className="workflow-step"><span>1</span><div><strong>Ask a question</strong><p>Write what you want to know.</p></div></div>
                  <div className="workflow-connector" />
                  <div className="workflow-step"><span>2</span><div><strong>Review the answer</strong><p>Read the response returned by the backend.</p></div></div>
                  <div className="workflow-connector" />
                  <div className="workflow-step"><span>3</span><div><strong>Revisit history</strong><p>Find previous queries in one place.</p></div></div>
                </div>
              </div>
              <footer className="page-footer"><Brand compact /><span>WealthFlow Query Console · Conversational financial analytics</span><button onClick={openConsole}>Get started ↗</button></footer>
            </div>
          </section>
        )}

        {page === "console" && (
          <section className="console-page">
            <header className="console-topbar">
              <div><p className="eyebrow">WORKSPACE / QUERY CONSOLE</p><h1>Query Console</h1><p>Ask a question. Get a clearer view of your reconciliation data.</p></div>
              <div className="role-chip"><span className="role-chip-dot" />{ROLE_OPTIONS.find((item) => item.value === role)?.label ?? "Analyst"}</div>
            </header>

            {messages.length === 0 ? (
              <div className="console-welcome">
                <div className="welcome-symbol"><Brand compact /></div>
                <p className="eyebrow">YOUR FINANCIAL DATA, IN PLAIN ENGLISH</p>
                <h2>Welcome to <span>WealthFlow</span></h2>
                <p className="welcome-description">What would you like to understand about your reconciliation operations today?</p>
                <div className="suggestion-heading"><span>TRY ASKING</span><span>5 EXAMPLES</span></div>
                <div className="suggestion-grid">
                  {SAMPLE_QUESTIONS.map((sample, index) => (
                    <button key={sample} className="suggestion-card" onClick={() => submitQuestion(sample)}>
                      <span className="suggestion-number">0{index + 1}</span><span>{sample}</span><span className="suggestion-arrow">↗</span>
                    </button>
                  ))}
                </div>
                <p className="welcome-note"><span>✦</span> Select an example or type your own question below.</p>
              </div>
            ) : (
              <div className="conversation-area">
                <div className="conversation-title"><span className="conversation-live" /> CONVERSATION <button onClick={() => { setMessages([]); setError(""); }}>New conversation +</button></div>
                {messages.map((message) => (
                  <article key={message.id} className={`message-row ${message.type}`}>
                    <div className="message-avatar">{message.type === "user" ? "Y" : message.type === "error" ? "!" : <Brand compact />}</div>
                    <div className="message-content">
                      <div className="message-author">{message.type === "user" ? "You" : message.type === "error" ? "Unable to answer" : "WealthFlow"}</div>
                      <div className="message-bubble">{message.text}</div>
                      {message.notes && <p className="message-notes">{String(message.notes)}</p>}
                      {message.sql && <details className="sql-details"><summary>View generated SQL</summary><pre>{message.sql}</pre></details>}
                    </div>
                  </article>
                ))}
                {loading && <div className="loading-row"><span className="loading-dots"><i /><i /><i /></span><span>Analyzing your question…</span></div>}
                {error && <p className="inline-error">{error}</p>}
                <div ref={conversationEndRef} />
              </div>
            )}

            <div className="composer-wrap">
              <form className="composer" onSubmit={(event) => { event.preventDefault(); submitQuestion(); }}>
                <div className="composer-icon">✧</div>
                <input ref={inputRef} value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="Ask about reconciliation breaks, amounts, teams…" aria-label="Your question" />
                <button type="submit" disabled={!question.trim() || loading}>{loading ? <span className="button-spinner" /> : <>Ask <span>↑</span></>}</button>
              </form>
              <p className="composer-caption"><span>▣</span> Answers are based on the data and capabilities available in your connected backend.</p>
            </div>
          </section>
        )}

        {page === "history" && (
          <section className="history-page">
            <PageHeader
              eyebrow="WORKSPACE / QUERY HISTORY"
              title="Query History"
              description="Review the questions submitted to WealthFlow and the answers returned by your backend."
              action={
                <div className="history-header-actions">
                  <button
                    className={`secondary-button recent-toggle ${recentOnly ? "selected" : ""}`}
                    onClick={() => setRecentOnly((current) => !current)}
                    aria-pressed={recentOnly}
                  >
                    ◷ {recentOnly ? "Show all queries" : "Recent queries"}
                  </button>
                  <button className="primary-button export-button" onClick={() => downloadHistory(filteredHistory)} disabled={!filteredHistory.length}>↓ Export CSV</button>
                </div>
              }
            />
            <div className="history-summary-row">
              <div className="history-summary-card"><span className="summary-icon">◷</span><div><small>SAVED QUERIES</small><strong>{history.length}</strong></div></div>
              <div className="history-summary-card"><span className="summary-icon green-icon">✓</span><div><small>HISTORY STATUS</small><strong>{historyLoading ? "Loading…" : historyError ? "Unavailable" : "Up to date"}</strong></div></div>
            </div>
            <div className="history-table-panel">
              <div className="history-table-toolbar">
                <div><h2>{recentOnly ? "Recent queries" : "All queries"}</h2><p>{recentOnly ? "Showing the five most recent matching queries." : "Your saved query activity in one place."}</p></div>
                <label className="history-search"><span>⌕</span><input value={searchHistory} onChange={(event) => setSearchHistory(event.target.value)} placeholder="Search history…" /></label>
              </div>
              {historyError && <div className="history-notice error-notice"><strong>Unable to load history</strong><p>{historyError}</p><button className="secondary-button" onClick={loadHistory}>Try again</button></div>}
              {historyLoading ? (
                <div className="history-empty"><span className="empty-icon">◌</span><h3>Loading your history</h3><p>Retrieving saved queries from the backend…</p></div>
              ) : !historyError && filteredHistory.length === 0 ? (
                <div className="history-empty"><span className="empty-icon">◷</span><h3>{history.length ? "No matching queries" : "No queries yet"}</h3><p>{history.length ? "Try a different search term." : "Your submitted questions will appear here after you run your first query."}</p><button className="secondary-button" onClick={openConsole}>Go to Query Console</button></div>
              ) : (
                <div className="history-list">
                  {filteredHistory.map((item, index) => (
                    <article className="history-item" key={item.id ?? item.query_id ?? `${historyQuestion(item)}-${index}`}>
                      <div className="history-item-icon">⌕</div>
                      <div className="history-item-main">
                        <div className="history-item-meta"><span className="history-role">{String(item.role ?? "Analyst").replaceAll("_", " ")}</span><span>·</span><time>{formatDate(item.ts ?? item.created_at ?? item.timestamp ?? item.date ?? item.createdAt)}</time></div>
                        <h3>{historyQuestion(item)}</h3>
                        {historyAnswer(item) && <p className="history-answer">{String(historyAnswer(item))}</p>}
                        {item.sql && <details className="sql-details"><summary>View SQL</summary><pre>{item.sql}</pre></details>}
                      </div>
                      <button className="reask-button" onClick={() => { setQuestion(historyQuestion(item)); setPage("console"); window.setTimeout(() => inputRef.current?.focus(), 50); }} title="Ask this question again">↗</button>
                    </article>
                  ))}
                </div>
              )}
              <div className="history-table-footer"><span>Showing {filteredHistory.length} of {history.length} queries</span><button onClick={loadHistory} disabled={historyLoading}>↻ Refresh history</button></div>
            </div>
          </section>
        )}
      </main>
    </div>
  );
}
