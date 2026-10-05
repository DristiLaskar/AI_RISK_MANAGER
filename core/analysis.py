"""Upload loading, the full analysis run, and the JSON payloads the UI consumes."""
import os
import threading

import numpy as np
import pandas as pd

from core.business_risk import BusinessRiskEngine
from core.churn import score_clients
from core.data_pipelining import UNASSIGNED, clean_invoices, clean_transactions, monthly_summary
from core.forecast import forecast, trim_partial
from core.ingestion import load_user_file
from core.mapper import auto_map_columns, normalize_column
from core.models import (AdaptiveIntelligenceEngine, BusinessHealthEngine, CLVEngine,
                         HeuristicPricingOptimizer)
from core.rag import RagIndex
from core.validator import validate_transactions

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPLOAD_DIR = os.path.join(BASE, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
HIGH = 60  # risk % above which an active client counts as "at risk"


# ------------------------------------------------------------------ loading
def load_uploads(folder=UPLOAD_DIR):
    """Split uploaded files into transactions and (optional) invoices."""
    tx, inv, skipped = [], [], []
    for f in sorted(os.listdir(folder)):
        try:
            df = load_user_file(os.path.join(folder, f))
            norm = df.rename(columns=lambda c: normalize_column(str(c)).replace(" ", "_"))
            if {"client_id", "due_date", "paid_date"} <= set(norm.columns):
                inv.append(norm)
            else:
                tx.append(validate_transactions(auto_map_columns(df)))
        except Exception as e:
            skipped.append(f"{f}: {e}")
    if not tx:
        raise ValueError("No usable transaction file. " + " ".join(skipped) if skipped else
                         "No usable transaction file.")
    return pd.concat(tx, ignore_index=True), (pd.concat(inv, ignore_index=True) if inv else None), skipped


# ------------------------------------------------------------------ analysis
def run(tx_raw, inv_raw=None):
    tx, quality = clean_transactions(tx_raw)
    inv = clean_invoices(inv_raw)
    monthly = monthly_summary(tx)
    last = tx["date"].max()
    inc = tx[(tx["type"] == "income") & (tx["client_id"] != UNASSIGNED)]
    if inc.empty:
        raise ValueError("No income transactions with a client name were found.")

    cl, model = score_clients(inc, inv)
    intel, clv, price = AdaptiveIntelligenceEngine(), CLVEngine(), HeuristicPricingOptimizer()
    cl["STAGE"] = cl.apply(intel.predict_lifecycle, axis=1)
    cl["RISK_%"] = cl.apply(intel.calculate_hybrid_risk, axis=1)
    cl["PREDICTIVE_CLV"] = cl.apply(clv.estimate_predictive_clv, axis=1)
    cl["AT_RISK"] = (cl["run_rate"] * 12 - cl["PREDICTIVE_CLV"]).clip(lower=0).round(2)
    cl["PRICE_STRATEGY"] = cl.apply(price.suggest_adjustment, axis=1)
    lost = cl["STAGE"] == "CHURNED"
    cl.loc[lost, ["PREDICTIVE_CLV", "AT_RISK"]] = 0            # nothing left to protect on a lost client
    active = cl[~lost]
    recent = cl[~lost | (cl["recency"] <= 365)].copy()         # active + lost in the last year
    recent.loc[recent["STAGE"] == "CHURNED", "run_rate"] = 0   # lost clients count as risk, not as revenue

    fm = trim_partial(monthly, last)
    fc = {"net": forecast(fm["net_cash_flow"]), "revenue": forecast(fm["revenue"])}
    burnout = BusinessHealthEngine().calculate_burnout_risk(recent)
    engine = BusinessRiskEngine()
    score = engine.calculate_risk_score(recent, monthly, burnout, fc["net"]["yhat"])

    res = dict(clients=cl, active=active, monthly=monthly, inc=inc, fc=fc, model=model, quality=quality,
               as_of=str(last.date()), burnout=burnout, risk_score=score, risk_status=engine.risk_status(score))
    res["dependency"] = _dependency(active)
    watch = active[active["RISK_%"] > 30].sort_values("AT_RISK", ascending=False)
    res["watch"] = watch if len(watch) >= 5 else active.sort_values("AT_RISK", ascending=False)
    res["lost_recently"] = int(((cl["STAGE"] == "CHURNED") & (cl["recency"] <= 365)).sum())
    res["rag"] = RagIndex(res)
    return res


def _dependency(active):
    share = (active["run_rate"] / (active["run_rate"].sum() + 1e-9) * 100).sort_values(ascending=False)
    return {"top_client": round(float(share.iloc[0]), 1) if len(share) else 0,
            "top_5_clients": round(float(share.head(5).sum()), 1)}


_lock, _cache = threading.Lock(), {"sig": None, "res": None}


def get_analysis():
    """Cached analysis of whatever is in uploads/ (recomputed only when the files change)."""
    files = sorted(os.listdir(UPLOAD_DIR))
    if not files:
        return None
    sig = [(f, os.path.getmtime(os.path.join(UPLOAD_DIR, f)), os.path.getsize(os.path.join(UPLOAD_DIR, f)))
           for f in files]
    with _lock:
        if _cache["sig"] != sig:
            tx, inv, _ = load_uploads()
            _cache.update(res=run(tx, inv), sig=sig)
        return _cache["res"]


# ------------------------------------------------------------------ payloads
def _records(df):
    return df.replace([np.inf, -np.inf], 0).fillna(0).round(2).to_dict("records")


def churn_outlook(active, months=3):
    """Expected churners and monthly revenue lost, from each client's 90-day churn probability."""
    p, rr = active["RISK_%"].values, active["run_rate"].values
    out = []
    for m in range(1, months + 1):
        surv = CLVEngine.survival(p, m)
        out.append({"month": f"M{m}", "expected_churn": round(float((1 - surv).sum()), 1),
                    "revenue_loss": round(float((rr * (1 - surv)).sum()), 2)})
    return out


def _rhythm(res, n=12):
    last = pd.Timestamp(res["as_of"])
    months = pd.period_range(end=last, periods=24, freq="M")
    top = res["watch"].head(n)
    inc = res["inc"][res["inc"]["client_id"].isin(top["client_id"])]
    pv = (inc.assign(m=inc["date"].dt.to_period("M")).pivot_table(
        index="client_id", columns="m", values="amount", aggfunc="sum", fill_value=0)
        .reindex(columns=months, fill_value=0))
    rows = []
    for _, r in top.iterrows():
        rows.append({"client_id": r["client_id"], "risk": float(r["RISK_%"]), "stage": r["STAGE"],
                     "recency": int(r["recency"]), "avg_gap": round(float(r["avg_gap"]), 1),
                     "run_rate": round(float(r["run_rate"]), 2), "at_risk": float(r["AT_RISK"]),
                     "pulse": [round(float(v), 2) for v in pv.loc[r["client_id"]].values]})
    return {"months": [str(m) for m in months], "rows": rows}


def dashboard_payload(res):
    cl, act, m = res["clients"], res["active"], res["monthly"]
    at = act[act["RISK_%"] > HIGH]
    b = res["burnout"]
    alerts = []
    if len(res["watch"]):
        t = res["watch"].iloc[0]
        alerts.append(f"{t['client_id']} is the biggest exposure: {t['RISK_%']:.0f}% chance of going quiet, "
                      f"${t['AT_RISK']:,.0f} of the next 12 months at stake.")
    if res["dependency"]["top_client"] > 30:
        alerts.append(f"One client is {res['dependency']['top_client']:.0f}% of recent revenue.")
    if b > 60:
        alerts.append("Burnout risk is high: too many shaky clients for the workload.")
    return {
        "as_of": res["as_of"],
        "summary": {"total_clients": len(cl), "active_clients": len(act), "lost_clients": len(cl) - len(act), "lost_last_year": res["lost_recently"],
                    "high_risk_clients": len(at), "revenue_at_risk": round(float(at["AT_RISK"].sum()), 2)},
        "burnout": b, "risk_score": res["risk_score"], "risk_status": res["risk_status"],
        "dependency_risk": res["dependency"],
        "forecast": res["fc"],
        "financial_trend": [{"date": d.strftime("%Y-%m"), "revenue": round(r.revenue, 2),
                             "expenses": round(r.expenses, 2), "net": round(r.net_cash_flow, 2)}
                            for d, r in m.tail(36).iterrows()],
        "lifecycle_distribution": cl["STAGE"].value_counts().to_dict(),
        "rhythm": _rhythm(res), "alerts": alerts, "model": res["model"], "quality": res["quality"],
    }


def clients_payload(res):
    cols = ["client_id", "STAGE", "RISK_%", "PREDICTIVE_CLV", "AT_RISK", "run_rate", "recency", "avg_gap",
            "PRICE_STRATEGY"]
    return {"clients": _records(res["clients"][cols].sort_values("AT_RISK", ascending=False))}


def forecast_payload(res):
    act, rev = res["active"], res["fc"]["revenue"]
    at = act[act["RISK_%"] > HIGH].sort_values("AT_RISK", ascending=False)
    outlook = churn_outlook(act)
    hist = res["monthly"]["revenue"].tail(12)
    return {
        "summary": {"next_month_revenue": rev["yhat"][0], "next_quarter_revenue": round(sum(rev["yhat"]), 2),
                    "error_pct": rev["error_pct"],
                    "revenue_at_risk_3m": round(sum(o["revenue_loss"] for o in outlook), 2)},
        "history": [{"month": d.strftime("%Y-%m"), "revenue": round(v, 2)} for d, v in hist.items()],
        "revenue_forecast": rev,
        "high_risk_clients": _records(at[["client_id", "RISK_%", "run_rate", "AT_RISK"]].head(15)),
        "churn_forecast": outlook,
    }
