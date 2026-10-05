import React, { useEffect, useRef, useState } from "react";
import { usd } from "./api.js";

export function useWidth() {
  const ref = useRef(null);
  const [w, setW] = useState(720);
  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(([e]) => setW(Math.max(280, e.contentRect.width)));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  return [ref, w];
}

const monthLabel = (ym) =>
  new Date(ym + "-01T00:00:00").toLocaleDateString("en-US", { month: "short", year: "2-digit" });

/* The payment rhythm: one tick per month of income, then the silence since the last payment. */
export function Rhythm({ data, onWhy }) {
  const { months, rows } = data;
  const first = monthLabel(months[0].slice(0, 7)), last = monthLabel(months[months.length - 1].slice(0, 7));
  return (
    <div className="rhythm" role="list">
      {rows.map((r, ri) => {
        const max = Math.max(...r.pulse, 1);
        const quiet = Math.min((r.recency / 30.4 / months.length) * 100, 100);
        return (
          <div className="rhythm-row" role="listitem" key={r.client_id}>
            <div className="rhythm-id">
              <b>{r.client_id}</b>
              <span>{r.stage.toLowerCase()}, {Math.round(r.risk)}% risk</span>
            </div>
            <div className="strip" role="img"
              aria-label={`${r.client_id}: last paid ${r.recency} days ago, usually every ${Math.round(r.avg_gap)} days`}>
              {r.pulse.map((v, ci) => (
                <i key={ci} className={v ? "tick" : "tick none"}
                  style={{ "--h": v ? Math.max(8, Math.sqrt(v / max) * 100) + "%" : "3px", "--d": ci * 16 + ri * 70 + "ms" }} />
              ))}
              <u className="quiet" style={{ width: quiet + "%" }}>
                {quiet > 22 && <em>{r.recency} days quiet</em>}
              </u>
            </div>
            <div className="rhythm-end">
              <b>{usd(r.at_risk, true)}</b>
              <button className="link" onClick={() => onWhy(`Why is ${r.client_id} at risk and what should I do?`)}>Why?</button>
            </div>
          </div>
        );
      })}
      <div className="rhythm-axis"><span>{first}</span><span>{last}</span></div>
    </div>
  );
}

const niceStep = (v) => { const raw = (v || 1) / 4, p = 10 ** Math.floor(Math.log10(raw)); return [1, 2, 2.5, 5, 10].map((m) => m * p).find((x) => x >= raw); };

/* Revenue (and optionally expenses) as bars, with the forecast as a range per month. */
export function CashChart({ trend, fc, label, height = 300 }) {
  const [ref, W] = useWidth();
  const H = height, pad = { l: 46, r: 8, t: 12, b: 26 };
  const n = trend.length + fc.months.length;
  const slot = (W - pad.l - pad.r) / n;
  const peak = Math.max(...trend.map((d) => d.revenue), ...fc.hi), step = niceStep(peak), top = Math.ceil(peak / step) * step;
  const y = (v) => pad.t + (1 - Math.max(v, 0) / top) * (H - pad.t - pad.b);
  const ticks = Array.from({ length: Math.round(top / step) + 1 }, (_, i) => i * step);
  const xl = (i) => pad.l + i * slot;
  return (
    <div ref={ref} className="chart">
      <svg width={W} height={H} role="img" aria-label={label}>
        <defs>
          <pattern id="hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <line x1="0" y1="0" x2="0" y2="6" stroke="var(--pink)" strokeWidth="2.2" />
          </pattern>
        </defs>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={pad.l} x2={W - pad.r} y1={y(t)} y2={y(t)} className="grid" />
            <text x={pad.l - 8} y={y(t) + 4} textAnchor="end" className="axis">{usd(t, true)}</text>
          </g>
        ))}
        {trend.map((d, i) => (
          <g key={d.date}>
            <rect x={xl(i) + slot * 0.14} width={slot * 0.72} y={y(d.revenue)} height={y(0) - y(d.revenue)} className="bar-rev">
              <title>{`${monthLabel(d.date)}: revenue ${usd(d.revenue)}${d.expenses != null ? `, expenses ${usd(d.expenses)}` : ""}`}</title>
            </rect>
            {d.expenses != null && (
              <rect x={xl(i) + slot * 0.3} width={slot * 0.4} y={y(d.expenses)} height={y(0) - y(d.expenses)} className="bar-exp" />
            )}
            {i % Math.ceil(n / 8) === 0 && <text x={xl(i) + slot / 2} y={H - 8} textAnchor="middle" className="axis">{monthLabel(d.date)}</text>}
          </g>
        ))}
        {fc.months.map((m, k) => {
          const i = trend.length + k;
          return (
            <g key={m}>
              <rect x={xl(i) + slot * 0.14} width={slot * 0.72} y={y(fc.hi[k])} height={Math.max(y(fc.lo[k]) - y(fc.hi[k]), 2)} fill="url(#hatch)" className="band">
                <title>{`${monthLabel(m)} forecast ${usd(fc.yhat[k])}, likely range ${usd(fc.lo[k])} to ${usd(fc.hi[k])}`}</title>
              </rect>
              <rect x={xl(i) + slot * 0.1} width={slot * 0.8} y={y(fc.yhat[k]) - 1.5} height="3" className="mid" />
              {k === 1 && <text x={xl(i) + slot / 2} y={H - 8} textAnchor="middle" className="axis">{monthLabel(m)}</text>}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

const BANDS = [["Healthy", 30], ["Moderate", 30], ["High", 20], ["Critical", 20]];
/* A printed-ruler gauge for a 0-100 score. */
export function Ruler({ value, name }) {
  return (
    <div className="ruler" role="img" aria-label={`${name}: ${value} out of 100`}>
      <div className="ruler-track">
        {BANDS.map(([b, w]) => <span key={b} style={{ flex: w }} className={"band-" + b.toLowerCase()} />)}
        <i className="ruler-mark" style={{ left: `${Math.min(value, 100)}%` }} />
      </div>
      <div className="ruler-labels">{BANDS.map(([b, w]) => <span key={b} style={{ flex: w }}>{b}</span>)}</div>
    </div>
  );
}

const STAGE_CLASS = { STABLE: "s-stable", GROWING: "s-growing", ACTIVE: "s-active", NEW: "s-new", DECLINING: "s-declining", CHURNED: "s-churned" };
export function StageBar({ dist }) {
  const entries = Object.entries(dist).sort((a, b) => b[1] - a[1]);
  return (
    <div>
      <div className="stagebar" role="img" aria-label={entries.map(([k, v]) => `${v} ${k.toLowerCase()}`).join(", ")}>
        {entries.map(([k, v]) => <span key={k} className={STAGE_CLASS[k]} style={{ flex: v }} title={`${k.toLowerCase()}: ${v}`} />)}
      </div>
      <ul className="stagekey">
        {entries.map(([k, v]) => <li key={k}><i className={STAGE_CLASS[k]} /> {k.toLowerCase()} <b>{v}</b></li>)}
      </ul>
    </div>
  );
}

export function RiskBar({ value }) {
  return <span className="riskbar" title={`${value}%`}><i style={{ width: `${Math.min(value, 100)}%` }} /><b>{Math.round(value)}%</b></span>;
}

/* Expected revenue lost per month, with the expected number of clients lost. */
export function LossBars({ data }) {
  const max = Math.max(...data.map((d) => d.revenue_loss), 1);
  return (
    <div className="lossbars">
      {data.map((d, i) => (
        <div key={d.month} className="loss">
          <div className="loss-bar"><i style={{ height: `${(d.revenue_loss / max) * 100}%` }} /></div>
          <b>{usd(d.revenue_loss, true)}</b>
          <span>{["Next month", "In two months", "In three months"][i]}: about {Math.round(d.expected_churn)} clients gone in total</span>
        </div>
      ))}
    </div>
  );
}
