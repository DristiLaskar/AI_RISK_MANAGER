import React, { useEffect, useMemo, useRef, useState } from "react";
import { api, usd } from "./api.js";
import { CashChart, LossBars, RiskBar, Rhythm, Ruler, StageBar } from "./charts.jsx";

export function useLoad(fn, dep) {
  const [s, set] = useState({ loading: true });
  useEffect(() => {
    let live = true;
    set({ loading: true });
    fn().then((data) => live && set({ data })).catch((error) => live && set({ error: error.message }));
    return () => { live = false; };
  }, [dep]);
  return s;
}

const plural = (n, a, b) => (n === 1 ? a : b);
const Status = ({ s }) => (s.loading ? <p className="muted pad">Crunching your numbers…</p> : <p role="alert" className="error pad">{s.error}</p>);

/* ------------------------------------------------------------ empty state / landing */
function Landing({ go, onDemo, busy }) {
  const sample = useMemo(() => {
    const rows = [["Brightwell", 0, 0.3], ["Nordlicht", 0, 0.12], ["Ostrava Labs", 0, 0.62], ["Kappa & Sons", 0, 0.05]];
    return rows.map(([n, , quiet], r) => ({
      n, quiet,
      pulse: Array.from({ length: 24 }, (_, c) => (c > 24 * (1 - quiet) ? 0 : 30 + ((c * 37 + r * 53) % 70))),
    }));
  }, []);
  return (
    <section className="landing">
      <h1>Know which clients will go quiet before your invoices do.</h1>
      <p className="lede">
        Upload your payments and see who is drifting away, how much money rides on them, and what next quarter
        looks like.
      </p>
      <div className="actions">
        <button className="btn primary" onClick={onDemo} disabled={busy}>{busy ? "Loading…" : "Try sample data"}</button>
        <button className="btn" onClick={() => go("data")}>Use your own data</button>
      </div>
      {busy && <p className="muted" role="status">Learning from five years of payments. This takes a few seconds.</p>}
      <div className="rhythm demo" aria-hidden="true">
        {sample.map((r, ri) => (
          <div className="rhythm-row" key={r.n}>
            <div className="rhythm-id"><b>{r.n}</b></div>
            <div className="strip">
              {r.pulse.map((v, ci) => <i key={ci} className={v ? "tick" : "tick none"} style={{ "--h": v ? v + "%" : "3px", "--d": ci * 16 + ri * 70 + "ms" }} />)}
              <u className="quiet" style={{ width: r.quiet * 100 + "%" }} />
            </div>
            <div className="rhythm-end" />
          </div>
        ))}
        <p className="caption">Example. Each tick is a month with a payment; the hatched stretch is silence.</p>
      </div>
    </section>
  );
}

/* ------------------------------------------------------------ overview */
export function Overview({ version, go, onDemo, busy, ask }) {
  const s = useLoad(api.dashboard, version);
  if (s.loading || s.error) return <Status s={s} />;
  const d = s.data;
  if (d.no_data) return <Landing go={go} onDemo={onDemo} busy={busy} />;
  const { summary: sm, model, quality } = d;
  const n = sm.high_risk_clients;
  return (
    <>
      <header className="hero">
        <h1>
          {n > 0 ? (
            <>
              <b>{n}</b> {plural(n, "client is", "clients are")} going quiet. About <b className="hot">{usd(sm.revenue_at_risk, true)}</b> of
              the next twelve months is at stake.
            </>
          ) : "Every active client is paying on rhythm."}
        </h1>
        <p className="muted">
          As of {d.as_of}. {sm.active_clients} active clients, {sm.lost_last_year} lost in the last year.
        </p>
      </header>

      <section aria-labelledby="rh">
        <h2 id="rh">Payment rhythm</h2>
        <p className="muted tight">Clients with the most revenue at stake. Ticks are months with income; hatching is the silence since their last payment.</p>
        {d.rhythm.rows.length ? <Rhythm data={d.rhythm} onWhy={ask} /> : <p className="muted">No active clients to show.</p>}
      </section>

      <section className="split" aria-labelledby="cf">
        <div>
          <h2 id="cf">Money in and out</h2>
          <CashChart trend={d.financial_trend.slice(-24)} fc={d.forecast.net} label="Monthly revenue and expenses with a three month net cash flow forecast" />
          <ul className="legend">
            <li><i className="k-rev" /> Revenue</li><li><i className="k-exp" /> Expenses</li>
            <li><i className="k-fc" /> Net cash flow forecast, likely range</li>
          </ul>
        </div>
        <div className="gauges">
          <div>
            <h2>Business risk</h2>
            <p className="big">{d.risk_status} <span>{d.risk_score}/100</span></p>
            <Ruler value={d.risk_score} name="Business risk" />
          </div>
          <div>
            <h2>Burnout</h2>
            <p className="big">{d.burnout}%</p>
            <Ruler value={d.burnout} name="Burnout" />
          </div>
          <div>
            <h2>Dependence</h2>
            <p>Your biggest client is <b>{d.dependency_risk.top_client}%</b> of recent revenue; your top five are <b>{d.dependency_risk.top_5_clients}%</b>.</p>
          </div>
        </div>
      </section>

      <section aria-labelledby="lc">
        <h2 id="lc">Where your clients are</h2>
        <StageBar dist={d.lifecycle_distribution} />
      </section>

      {d.alerts.length > 0 && (
        <section aria-labelledby="al">
          <h2 id="al">Worth acting on</h2>
          <ul className="alerts">{d.alerts.map((a) => <li key={a}>{a}</li>)}</ul>
        </section>
      )}

      <section className="notes" aria-labelledby="bn">
        <h2 id="bn">Behind the numbers</h2>
        {model.mode === "ml" ? (
          <p>
            Risk is the chance a client pays nothing in the next {model.horizon_days} days. The model learns from your own history and was
            tested on a later period it had not seen: AUC <b>{model.auc ?? "n/a"}</b>, against <b>{model.baseline_auc ?? "n/a"}</b> for
            simply flagging overdue clients (0.5 is a coin flip). What it leans on most: {Object.keys(model.drivers).slice(0, 3).join(", ").replace(/_/g, " ")}.
          </p>
        ) : (
          <p>{model.reason} Until then, risk comes from simple rules: how overdue a client is and how irregular their payments are.</p>
        )}
        <p className="muted">
          Cleaning removed {quality.duplicates_removed} duplicate rows and {quality.unreadable_rows} unreadable rows;
          {" "}{quality.income_without_client} income rows had no client name and count towards revenue but not towards client scores.
        </p>
      </section>
    </>
  );
}

/* ------------------------------------------------------------ clients */
const FILTERS = [["all", "Everyone"], ["risk", "At risk"], ["active", "Active"], ["lost", "Lost"]];
const COLS = [["client_id", "Client"], ["STAGE", "Stage"], ["RISK_%", "Risk"], ["PREDICTIVE_CLV", "Next 12 months"],
  ["AT_RISK", "At stake"], ["recency", "Last paid"], ["PRICE_STRATEGY", "Suggested action"]];

export function Clients({ version, go }) {
  const s = useLoad(api.clients, version);
  const [f, setF] = useState("all"), [q, setQ] = useState(""), [sort, setSort] = useState(["AT_RISK", -1]);
  if (s.loading || s.error) return <Status s={s} />;
  if (s.data.no_data) return <Empty go={go} />;
  const keep = (c) => f === "all" || (f === "risk" && c.STAGE !== "CHURNED" && c["RISK_%"] > 60) ||
    (f === "active" && c.STAGE !== "CHURNED") || (f === "lost" && c.STAGE === "CHURNED");
  const rows = s.data.clients.filter((c) => keep(c) && c.client_id.toLowerCase().includes(q.toLowerCase()))
    .sort((a, b) => (a[sort[0]] > b[sort[0]] ? 1 : -1) * sort[1]);
  return (
    <>
      <header className="hero small">
        <h1>{s.data.clients.length} clients</h1>
        <div className="toolbar">
          <div className="seg" role="group" aria-label="Filter clients">
            {FILTERS.map(([k, l]) => <button key={k} aria-pressed={f === k} onClick={() => setF(k)}>{l}</button>)}
          </div>
          <input type="search" placeholder="Find a client" aria-label="Find a client" value={q} onChange={(e) => setQ(e.target.value)} />
          <a className="btn" href={api.csvUrl}>Download CSV</a>
        </div>
      </header>
      <div className="table-wrap">
        <table>
          <thead><tr>{COLS.map(([k, l]) => (
            <th key={k} aria-sort={sort[0] === k ? (sort[1] > 0 ? "ascending" : "descending") : "none"}>
              <button onClick={() => setSort([k, sort[0] === k ? -sort[1] : -1])}>{l}{sort[0] === k ? (sort[1] > 0 ? " ▴" : " ▾") : ""}</button>
            </th>))}</tr></thead>
          <tbody>
            {rows.map((c) => (
              <tr key={c.client_id} className={c.STAGE === "CHURNED" ? "lost" : ""}>
                <td><b>{c.client_id}</b></td><td>{c.STAGE.toLowerCase()}</td>
                <td><RiskBar value={c["RISK_%"]} /></td>
                <td>{usd(c.PREDICTIVE_CLV)}</td><td>{usd(c.AT_RISK)}</td>
                <td>{c.recency} days ago</td><td>{c.PRICE_STRATEGY}</td>
              </tr>))}
          </tbody>
        </table>
        {!rows.length && <p className="muted pad">No clients match.</p>}
      </div>
    </>
  );
}

/* ------------------------------------------------------------ outlook */
export function Outlook({ version, go }) {
  const s = useLoad(api.forecast, version);
  if (s.loading || s.error) return <Status s={s} />;
  const d = s.data;
  if (d.no_data) return <Empty go={go} />;
  const { summary: sm } = d;
  return (
    <>
      <header className="hero">
        <h1>
          Next quarter: about <b>{usd(sm.next_quarter_revenue, true)}</b> coming in, with <b className="hot">{usd(sm.revenue_at_risk_3m, true)}</b> likely
          to walk away.
        </h1>
        <p className="muted">
          {usd(sm.next_month_revenue, true)} expected next month.
          {sm.error_pct != null && <> In a backtest over recent months the forecast was off by about {sm.error_pct}%.</>}
        </p>
      </header>
      <section aria-labelledby="rf">
        <h2 id="rf">Revenue forecast</h2>
        <CashChart trend={d.history.map((h) => ({ date: h.month, revenue: h.revenue }))} fc={d.revenue_forecast} label="Monthly revenue with a three month forecast" height={280} />
        <ul className="legend"><li><i className="k-rev" /> Revenue</li><li><i className="k-fc" /> Forecast, likely range</li></ul>
      </section>
      <section aria-labelledby="ch">
        <h2 id="ch">Revenue we expect to lose</h2>
        <p className="muted tight">Each month adds up every client's chance of leaving, weighted by what they pay you.</p>
        <LossBars data={d.churn_forecast} />
      </section>
      <section aria-labelledby="hr">
        <h2 id="hr">Clients most likely to leave</h2>
        {d.high_risk_clients.length ? (
          <div className="table-wrap"><table>
            <thead><tr><th>Client</th><th>Risk</th><th>Monthly run-rate</th><th>At stake over 12 months</th></tr></thead>
            <tbody>{d.high_risk_clients.map((c) => (
              <tr key={c.client_id}><td><b>{c.client_id}</b></td><td><RiskBar value={c["RISK_%"]} /></td><td>{usd(c.run_rate)}</td><td>{usd(c.AT_RISK)}</td></tr>))}</tbody>
          </table></div>
        ) : <p className="muted">No active client is above 60% risk.</p>}
      </section>
    </>
  );
}

const Empty = ({ go }) => (
  <section className="landing"><h1>Nothing to show yet.</h1>
    <p className="lede">Add some payments and this page fills itself in.</p>
    <div className="actions"><button className="btn primary" onClick={() => go("data")}>Add data</button></div></section>
);

/* ------------------------------------------------------------ data in */
function parseRows(text) {
  const rows = [], bad = [];
  text.split("\n").map((l) => l.trim()).filter(Boolean).forEach((line, i) => {
    const [date, client_id, amount, type] = line.split(/[,\t]/).map((x) => x.trim());
    if (!date || isNaN(Date.parse(date)) || !client_id || isNaN(parseFloat(amount))) bad.push(i + 1);
    else rows.push({ date, client_id, amount: parseFloat(amount), ...(type ? { type } : {}) });
  });
  return { rows, bad };
}

export function DataIn({ onLoaded, onDemo, busy }) {
  const [files, setFiles] = useState([]), [text, setText] = useState(""), [err, setErr] = useState(""), [work, setWork] = useState("");
  const fileRef = useRef();
  const run = async (name, fn) => {
    setErr(""); setWork(name);
    try { await fn(); onLoaded(); } catch (e) { setErr(e.message); } finally { setWork(""); }
  };
  const parsed = parseRows(text);
  return (
    <>
      <header className="hero small"><h1>Bring in your payments</h1>
        <p className="muted">Pick whichever is quickest. Everything is analysed again each time you load something new.</p></header>
      {err && <p role="alert" className="error">{err}</p>}
      <section className="intake">
        <div>
          <h2>Sample data</h2>
          <p>Five years of made-up freelance income: 100 clients, some of whom leave for good.</p>
          <button className="btn primary" disabled={busy || work} onClick={() => run("demo", onDemo)}>{work === "demo" ? "Loading…" : "Load sample data"}</button>
        </div>
        <div>
          <h2>Upload files</h2>
          <p>A spreadsheet with a client, a date and an amount for each payment. Add a type column (income or expense) to track costs, and an invoices file with due and paid dates to include payment delays.</p>
          <input ref={fileRef} type="file" multiple accept=".csv,.xlsx" hidden onChange={(e) => setFiles([...e.target.files])} />
          <button className="btn" onClick={() => fileRef.current.click()}>{files.length ? `${files.length} selected: ${files.map((f) => f.name).join(", ")}` : "Choose .csv or .xlsx files"}</button>
          {files.length > 0 && <button className="btn primary" disabled={work} onClick={() => run("up", () => api.upload(files))}>{work === "up" ? "Analysing…" : "Analyse files"}</button>}
        </div>
        <div>
          <h2>Type or paste payments</h2>
          <p>One per line: date, client, amount. Optionally add expense at the end of a line for costs.</p>
          <textarea rows="6" value={text} onChange={(e) => setText(e.target.value)} placeholder={"2025-01-15, Acme, 4200\n2025-02-14, Acme, 4350\n2025-02-20, Hosting, 80, expense"} />
          {parsed.bad.length > 0 && <p className="error">Check line {parsed.bad.slice(0, 5).join(", ")}: each needs a date, a client and a number.</p>}
          <button className="btn primary" disabled={work || !parsed.rows.length || parsed.bad.length > 0} onClick={() => run("man", () => api.manual(parsed.rows))}>
            {work === "man" ? "Analysing…" : `Analyse ${parsed.rows.length} ${plural(parsed.rows.length, "payment", "payments")}`}
          </button>
        </div>
      </section>
    </>
  );
}

/* ------------------------------------------------------------ account */
export function Account({ onAuthed }) {
  const [mode, setMode] = useState("login"), [f, setF] = useState({ name: "", email: "", password: "" }), [err, setErr] = useState("");
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const submit = async (e) => {
    e.preventDefault(); setErr("");
    try {
      const d = await api.auth(mode, mode === "signup" ? f : { email: f.email, password: f.password });
      localStorage.setItem("arm_user", JSON.stringify({ name: d.name, token: d.token }));
      onAuthed(d.name);
    } catch (x) { setErr(x.message); }
  };
  return (
    <section className="account">
      <h1>{mode === "login" ? "Welcome back" : "Create your account"}</h1>
      <form onSubmit={submit}>
        {mode === "signup" && <label>Name<input required value={f.name} onChange={set("name")} autoComplete="name" /></label>}
        <label>Email<input required type="email" value={f.email} onChange={set("email")} autoComplete="email" /></label>
        <label>Password<input required type="password" minLength={6} value={f.password} onChange={set("password")} autoComplete={mode === "login" ? "current-password" : "new-password"} /></label>
        {err && <p role="alert" className="error">{err}</p>}
        <button className="btn primary">{mode === "login" ? "Sign in" : "Create account"}</button>
      </form>
      <p className="muted">{mode === "login" ? "New here?" : "Already have an account?"}{" "}
        <button className="link" onClick={() => { setMode(mode === "login" ? "signup" : "login"); setErr(""); }}>{mode === "login" ? "Create an account" : "Sign in"}</button></p>
    </section>
  );
}

/* ------------------------------------------------------------ ask (RAG) */
const IDEAS = ["Who should I contact first?", "What happens to my cash flow next quarter?", "How reliable is the churn model?", "Am I too dependent on one client?"];

export function Ask({ open, seed, onClose }) {
  const [q, setQ] = useState(""), [a, setA] = useState(null), [busy, setBusy] = useState(false), [err, setErr] = useState("");
  const input = useRef();
  const submit = async (text) => {
    if (!text.trim()) return;
    setQ(text); setBusy(true); setErr(""); setA(null);
    try { setA(await api.ask(text)); } catch (e) { setErr(e.message); } finally { setBusy(false); }
  };
  useEffect(() => { if (open) { input.current?.focus(); if (seed.q) submit(seed.q); } }, [open, seed.n]);
  useEffect(() => {
    const k = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, []);
  if (!open) return null;
  return (
    <div className="scrim" onClick={onClose}>
      <div className="sheet" role="dialog" aria-modal="true" aria-label="Ask about your numbers" onClick={(e) => e.stopPropagation()}>
        <form onSubmit={(e) => { e.preventDefault(); submit(q); }}>
          <input ref={input} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ask about a client, your cash flow or the model" aria-label="Your question" />
          <button className="btn primary" disabled={busy}>{busy ? "Thinking…" : "Ask"}</button>
        </form>
        {!a && !busy && !err && <ul className="ideas">{IDEAS.map((i) => <li key={i}><button className="link" onClick={() => submit(i)}>{i}</button></li>)}</ul>}
        {err && <p role="alert" className="error">{err}</p>}
        {a && (
          <div className="answer">
            <p className="text">{a.answer}</p>
            {a.note && <p className="muted">{a.note}</p>}
            <p className="muted">{a.mode === "llm" ? "Written by the language model from" : "Matching facts from"} your data:</p>
            <ul className="chips">{a.sources.map((s) => <li key={s.id}><details><summary>{s.id}</summary><p>{s.text}</p></details></li>)}</ul>
          </div>
        )}
      </div>
    </div>
  );
}
