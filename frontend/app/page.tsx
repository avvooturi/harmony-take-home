"use client";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { request } from "@/lib/api";

type Employee = {
  id: string;
  name: string;
  role: string;
  department: string;
  permissions: string[];
};
type Attention = {
  id: string;
  run_id: string;
  priority: string;
  title: string;
  evidence: string[];
  recommendation: string;
  status: string;
};
type Approval = {
  id: string;
  run_id: string;
  tool_name: string;
  arguments: Record<string, unknown>;
  reason: string;
  evidence: string[];
  status: string;
};
type Audit = {
  id: string;
  event_type: string;
  details: Record<string, unknown>;
  created_at: string;
};
type ContextItem = {
  source: string;
  title: string;
  detail: string;
  status?: string;
  occurred_at?: string;
  decisions?: string[];
};
type MemoryItem = {
  id: string;
  type: string;
  content: string;
  source: string;
  importance: number;
  expires_at: string | null;
};
type RecommendedAction = {
  title: string;
  detail: string;
  action: string;
  permission: string;
  available: boolean;
};
type WorkContext = {
  employee: Employee & {
    relationships: { name: string; relationship: string }[];
  };
  current_work: ContextItem[];
  recent_context: ContextItem[];
  long_term_memory: MemoryItem[];
  recommended_actions: RecommendedAction[];
};
type ChatResponse = {
  message: string;
  reasoning_mode: "local_ai" | "deterministic_fallback";
  provider: string;
  model: string;
  proposed_action: {
    type: string;
    status: string;
    next_step: string;
    approval_id?: string;
  } | null;
  fallback_error: string | null;
};
const tabs = [
  "Work Context",
  "Attention",
  "Approvals",
  "Agent",
  "Audit",
] as const;
type Tab = (typeof tabs)[number];

export default function Home() {
  const [employee, setEmployee] = useState("emp-pm"),
    [employees, setEmployees] = useState<Employee[]>([]),
    [tab, setTab] = useState<Tab>("Work Context");
  const [attention, setAttention] = useState<Attention[]>([]),
    [approvals, setApprovals] = useState<Approval[]>([]),
    [audit, setAudit] = useState<Audit[]>([]),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const [workContext, setWorkContext] = useState<WorkContext | null>(null);
  const [notice, setNotice] = useState("");
  const [messages, setMessages] = useState<string[]>([
    "Ask me about purchasing risk. I can recommend actions, but I cannot execute them without the application approval gate.",
  ]);
  const [chatMode, setChatMode] = useState({
    mode: "checking",
    model: "",
    fallbackDetail: "",
  });
  const [chatAction, setChatAction] = useState<ChatResponse["proposed_action"]>(null);
  const load = useCallback(async () => {
    setError("");
    try {
      const [es, wc, at, ap, au] = await Promise.all([
        request<Employee[]>("/employees", employee),
        request<WorkContext>("/work-context", employee),
        request<Attention[]>("/attention", employee),
        request<Approval[]>("/approvals", employee),
        request<Audit[]>("/audit", employee),
      ]);
      setEmployees(es);
      setWorkContext(wc);
      setAttention(at);
      setApprovals(ap);
      setAudit(au);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [employee]);
  useEffect(() => {
    load();
  }, [load]);
  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(""), 6500);
    return () => window.clearTimeout(timer);
  }, [notice]);
  async function analyze(destination: "Attention" | "Approvals") {
    setBusy(true);
    setNotice("");
    setError("");
    try {
      await request("/proactive/run", employee, { method: "POST" });
      await load();
      setNotice(
        destination === "Approvals"
          ? "Action prepared. Review the exact change and evidence before approving."
          : "Proactive analysis completed.",
      );
      setTab(destination);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function decide(id: string, decision: string) {
    setBusy(true);
    setNotice("");
    try {
      const result = await request<{ status: string }>(
        `/approvals/${id}/decision`,
        employee,
        { method: "POST", body: JSON.stringify({ decision }) },
      );
      await load();
      setNotice(
        `Decision recorded: ${result.status}. You can now dismiss the task from your Attention feed.`,
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function dismissAttention(id: string) {
    setBusy(true);
    setNotice("");
    try {
      await request(`/attention/${id}/dismiss`, employee, { method: "POST" });
      await load();
      setNotice(
        "Task removed from your Attention feed. Its approval and audit history remain available.",
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function resetDemo() {
    if (!window.confirm("Reset all demo data and restore the original seeded scenario?")) {
      return;
    }
    setBusy(true);
    setNotice("");
    setError("");
    try {
      await request("/demo/reset", employee, { method: "POST" });
      setMessages([
        "Ask me about purchasing risk. I can recommend actions, but I cannot execute them without the application approval gate.",
      ]);
      setChatMode({ mode: "checking", model: "", fallbackDetail: "" });
      setChatAction(null);
      setTab("Work Context");
      await load();
      setNotice("Demo reset complete. The original Part X scenario is ready to run again.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function chat(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget),
      message = String(f.get("message"));
    if (!message) return;
    setBusy(true);
    setError("");
    setMessages((x) => [...x, `You: ${message}`]);
    e.currentTarget.reset();
    try {
      const r = await request<ChatResponse>("/agent/chat", employee, {
        method: "POST",
        body: JSON.stringify({ message }),
      });
      setChatMode({
        mode: r.reasoning_mode,
        model: r.model,
        fallbackDetail: r.fallback_error
          ? "Local model unavailable — using deterministic fallback"
          : "",
      });
      setChatAction(r.proposed_action);
      setMessages((x) => [
        ...x,
        `Agent: ${r.message}`,
        ...(r.proposed_action
          ? [`Proposed action: ${r.proposed_action.type}. ${r.proposed_action.next_step}.`]
          : []),
      ]);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const who = employees.find((e) => e.id === employee);
  return (
    <div className="shell">
      <aside className="side">
        <div className="brand">
          Harmony <span>Agent</span>
        </div>
        <nav className="nav">
          {tabs.map((t) => (
            <button
              key={t}
              className={tab === t ? "active" : ""}
              onClick={() => setTab(t)}
            >
              {t}
            </button>
          ))}
        </nav>
      </aside>
      <main className="main">
        <div className="top">
          <div>
            <h1>{tab}</h1>
            <div className="muted">
              {who?.role} · {who?.department}
            </div>
          </div>
          <div className="header-actions">
            {who?.permissions.includes("demo.reset") && (
              <button className="secondary reset-demo" disabled={busy} onClick={resetDemo}>
                {busy ? "Working…" : "Reset Demo"}
              </button>
            )}
            <select
              className="switcher"
              value={employee}
              onChange={(e) => setEmployee(e.target.value)}
            >
              {employees.map((e) => (
                <option value={e.id} key={e.id}>
                  {e.name} — {e.role}
                </option>
              ))}
            </select>
          </div>
        </div>
        {error && (
          <div className="card error notification-banner" role="alert">
            <div><b>Access or request error:</b> {error}</div>
            <button className="notification-close" aria-label="Dismiss error" onClick={() => setError("")}>
              ×
            </button>
          </div>
        )}
        {notice && (
          <div className="card success notification-banner" role="status">
            <b>{notice}</b>
            <button className="notification-close" aria-label="Dismiss notification" onClick={() => setNotice("")}>
              ×
            </button>
          </div>
        )}
        {tab === "Work Context" && workContext && (
          <>
            <div className="card context-hero">
              <div>
                <div className="eyebrow">PERSONALIZED WORK CONTEXT</div>
                <h2>{workContext.employee.name}</h2>
                <p className="muted">
                  {workContext.employee.role} ·{" "}
                  {workContext.employee.department}
                </p>
              </div>
              <div>
                {workContext.employee.relationships.map((r, i) => (
                  <span className="pill" key={i}>
                    {r.relationship}: {r.name}
                  </span>
                ))}
              </div>
            </div>
            <div className="context-grid">
              <section className="card">
                <h2>Current Work</h2>
                <p className="muted">
                  Retrieved now from authorized source systems.
                </p>
                {workContext.current_work.map((x, i) => (
                  <div className="context-item" key={i}>
                    <div className="row">
                      <b>{x.title}</b>
                      {x.status && (
                        <span className="pill pending">{x.status}</span>
                      )}
                    </div>
                    <small>{x.source}</small>
                    <p>{x.detail}</p>
                  </div>
                ))}
              </section>
              <section className="card">
                <h2>Recent Context</h2>
                <p className="muted">
                  Relevant history; not copied into agent memory.
                </p>
                {workContext.recent_context.map((x, i) => (
                  <div className="context-item" key={i}>
                    <b>{x.title}</b>
                    <small>
                      {x.source}
                      {x.occurred_at
                        ? ` · ${new Date(x.occurred_at).toLocaleString()}`
                        : ""}
                    </small>
                    <p>{x.detail}</p>
                    {x.decisions?.map((d) => (
                      <div className="decision" key={d}>
                        Decision: {d}
                      </div>
                    ))}
                  </div>
                ))}
              </section>
              <section className="card">
                <h2>Long-Term Memory</h2>
                <p className="muted">Selective durable facts only.</p>
                {workContext.long_term_memory.map((m) => (
                  <div className="context-item" key={m.id}>
                    <div className="row">
                      <span className="pill">{m.type}</span>
                      <small>importance {m.importance}</small>
                    </div>
                    <p>{m.content}</p>
                    <small>Source: {m.source}</small>
                  </div>
                ))}
              </section>
              <section className="card recommendations">
                <h2>Recommended Actions</h2>
                <p className="muted">
                  Personalized using role, permissions, current work, recent
                  history, and memory.
                </p>
                {workContext.recommended_actions.map((a, i) => (
                  <div className="context-item" key={i}>
                    <div className="row">
                      <b>{a.title}</b>
                      <span className={`pill ${a.available ? "" : "pending"}`}>
                        {a.available ? "AVAILABLE" : "NOT AUTHORIZED"}
                      </span>
                    </div>
                    <p>{a.detail}</p>
                    {a.action === "RUN_PROACTIVE_ANALYSIS" && a.available && (
                      <button
                        disabled={busy}
                        onClick={() => analyze("Approvals")}
                      >
                        {busy ? "Preparing…" : "Prepare action"}
                      </button>
                    )}
                  </div>
                ))}
              </section>
            </div>
          </>
        )}
        {tab === "Attention" && (
          <>
            <div className="row" style={{ marginBottom: 16 }}>
              <button disabled={busy} onClick={() => analyze("Attention")}>
                {busy ? "Analyzing…" : "Run proactive analysis"}
              </button>
              <span className="muted">
                Deterministic detection first; agent reasoning only after a risk
                is found.
              </span>
            </div>
            {attention.length === 0 ? (
              <div className="card muted">
                No attention items for this employee.
              </div>
            ) : (
              attention.map((a) => (
                <div className="card" key={a.id}>
                  <div className="row">
                    <span className="eyebrow">{a.priority} PRIORITY</span>
                    <span
                      className={`pill ${a.status === "OPEN" ? "pending" : ""}`}
                    >
                      {a.status}
                    </span>
                  </div>
                  <h2>{a.title}</h2>
                  <div className="evidence">
                    <b>Evidence</b>
                    <ul>
                      {a.evidence.map((x) => (
                        <li key={x}>{x}</li>
                      ))}
                    </ul>
                  </div>
                  <p>
                    <b>Recommended action:</b> {a.recommendation}
                  </p>
                  {a.status === "OPEN" ? (
                    <button onClick={() => setTab("Approvals")}>
                      Review approval
                    </button>
                  ) : (
                    <div className="decision-closure">
                      <p>
                        <b>Decision complete:</b> this task is retained until
                        you dismiss it.
                      </p>
                      <button
                        disabled={busy}
                        className="secondary"
                        onClick={() => dismissAttention(a.id)}
                      >
                        Dismiss from Attention
                      </button>
                    </div>
                  )}
                </div>
              ))
            )}
          </>
        )}
        {tab === "Approvals" && (
          <>
            {approvals.length === 0 ? (
              <div className="card muted">
                No approval requests for this employee.
              </div>
            ) : (
              approvals.map((a) => {
                const linked = attention.find(
                  (item) => item.run_id === a.run_id,
                );
                return (
                  <div className="card" key={a.id}>
                    <div className="row">
                      <span
                        className={`pill ${a.status === "PENDING" ? "pending" : ""}`}
                      >
                        {a.status}
                      </span>
                      <b>{a.tool_name}</b>
                    </div>
                    <p>{a.reason}</p>
                    <div className="grid">
                      <div>
                        <h3>Exact change</h3>
                        <pre>{JSON.stringify(a.arguments, null, 2)}</pre>
                      </div>
                      <div>
                        <h3>Evidence</h3>
                        <ul>
                          {a.evidence.map((x) => (
                            <li key={x}>{x}</li>
                          ))}
                        </ul>
                      </div>
                    </div>
                    {a.status === "PENDING" ? (
                      <div className="row">
                        <button
                          disabled={busy}
                          onClick={() => decide(a.id, "APPROVE")}
                        >
                          Approve
                        </button>
                        <button
                          disabled={busy}
                          className="danger"
                          onClick={() => decide(a.id, "REJECT")}
                        >
                          Reject
                        </button>
                      </div>
                    ) : (
                      <div className="decision-closure">
                        <p>
                          <b>Decision already made:</b> {a.status}. The approval
                          remains here as history.
                        </p>
                        {linked ? (
                          <button
                            disabled={busy}
                            className="secondary"
                            onClick={() => dismissAttention(linked.id)}
                          >
                            Dismiss task from Attention
                          </button>
                        ) : (
                          <span className="muted">
                            This task has been removed from Attention.
                          </span>
                        )}
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </>
        )}
        {tab === "Agent" && (
          <div className="card">
            <div className="row chat-mode">
              <span
                className={`pill ${chatMode.mode === "deterministic_fallback" ? "pending" : ""}`}
              >
                {chatMode.mode === "local_ai"
                  ? "Local AI"
                  : chatMode.mode === "deterministic_fallback"
                    ? "Deterministic fallback"
                    : "Mode shown after first response"}
              </span>
              {chatMode.model && <small className="muted">{chatMode.model}</small>}
            </div>
            {chatMode.fallbackDetail && (
              <div className="mode-detail muted">{chatMode.fallbackDetail}</div>
            )}
            <div className="chat">
              {messages.map((m, i) => (
                <div className="message" key={i}>
                  {m}
                </div>
              ))}
            </div>
            {chatAction?.type === "review_pending_approval" && (
              <button className="secondary chat-action" onClick={() => setTab("Approvals")}>
                Review approval
              </button>
            )}
            {chatAction?.type === "prepare_approval" && (
              <button className="secondary chat-action" onClick={() => analyze("Approvals")}>
                Prepare action
              </button>
            )}
            <form className="input" onSubmit={chat}>
              <input name="message" placeholder="Ask about your work context…" />
              <button disabled={busy}>{busy ? "Reasoning…" : "Send"}</button>
            </form>
          </div>
        )}
        {tab === "Audit" && (
          <div className="card audit">
            <table>
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Event</th>
                  <th>Details</th>
                </tr>
              </thead>
              <tbody>
                {audit.map((a) => (
                  <tr key={a.id}>
                    <td>{new Date(a.created_at).toLocaleString()}</td>
                    <td>{a.event_type}</td>
                    <td>
                      <pre>{JSON.stringify(a.details, null, 2)}</pre>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {audit.length === 0 && (
              <p className="muted">No visible audit events.</p>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
