"""Churn model with a real, forward-looking target.

A client "churns" at a cutoff date if they make no payment in the following HORIZON days.
Features are computed ONLY from data up to the cutoff, with the same function for training
and for scoring today, so there is no label leakage and no train/serve skew. The model is
trained on rolling biweekly snapshots of the user's own history and evaluated on a later,
purged time window.
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import brier_score_loss, roc_auc_score

HORIZON = 90
FEATURES = ["recency", "overdue_ratio", "avg_gap", "volatility", "payment_count",
            "revenue_trend", "revenue_share_%", "avg_payment_delay", "tenure"]
DAY = np.timedelta64(1, "D")
_cs = lambda x: np.concatenate([[0.0], np.cumsum(x)])


def snapshot_features(inc, inv, cuts):
    """One row per (client, cutoff) for clients that had paid at least once by the cutoff."""
    cuts = np.asarray(cuts, dtype="datetime64[ns]")
    daily = inc.groupby("date")["amount"].sum().sort_index()
    tot_dates, tot_cs = daily.index.values, _cs(daily.values)
    inv_by = {c: g.sort_values("paid_date") for c, g in inv.groupby("client_id")}
    out = []
    for cid, g in inc.groupby("client_id"):
        d, a = g["date"].values, g["amount"].values
        n = len(d)
        k = np.searchsorted(d, cuts, side="right")          # payments made by each cutoff
        ok = k > 0
        if not ok.any():
            continue
        k, cu = k[ok], cuts[ok]
        recency = (cu - d[k - 1]) / DAY

        gaps = np.diff(d) / DAY                              # prefix stats over first k payments
        gs, gq, ng = _cs(gaps), _cs(gaps ** 2), k - 1
        mean = np.where(ng > 0, gs[ng] / np.maximum(ng, 1), 30.0)
        var = np.where(ng > 1, gq[ng] / np.maximum(ng, 1) - (gs[ng] / np.maximum(ng, 1)) ** 2, 0)

        acs = _cs(a)                                         # last-3 vs previous-6 payment amounts
        j, i0 = np.maximum(k - 3, 0), np.maximum(k - 9, 0)
        last3 = (acs[k] - acs[j]) / np.minimum(k, 3)
        prev = np.where(j > i0, (acs[j] - acs[i0]) / np.maximum(j - i0, 1), np.nan)
        trend = np.clip(np.where(np.isnan(prev) | (prev == 0), 0, last3 / np.where(prev == 0, 1, prev) - 1), -1, 1)

        tenure = (cu - d[0]) / DAY
        last = d[k - 1]                                      # typical monthly revenue while they were paying
        i180 = np.searchsorted(d, last - 180 * DAY, side="right")
        run_rate = (acs[k] - acs[i180]) / np.clip((last - d[0]) / DAY / 30.4, 1, 6)

        delay = np.zeros(len(cu))
        if cid in inv_by:
            iv = inv_by[cid]
            kk = np.searchsorted(iv["paid_date"].values, cu, side="right")
            dcs = _cs(iv["delay"].values)
            delay = np.where(kk > 0, dcs[kk] / np.maximum(kk, 1), 0)

        nxt = d[np.minimum(k, n - 1)]                        # first payment after the cutoff
        churned = ((k >= n) | ((nxt - cu) / DAY > HORIZON)).astype(int)

        out.append(pd.DataFrame({
            "client_id": cid, "cutoff": cu, "recency": recency, "overdue_ratio": recency / (mean + 1),
            "avg_gap": mean, "volatility": np.sqrt(np.maximum(var, 0)) / (mean + 1),
            "payment_count": k, "revenue_trend": trend, "tenure": tenure, "run_rate": run_rate,
            "revenue_share_%": acs[k] / np.maximum(tot_cs[np.searchsorted(tot_dates, cu, side="right")], 1e-9) * 100,
            "avg_payment_delay": delay, "total_revenue": acs[k], "churned": churned,
        }))
    return pd.concat(out, ignore_index=True)


def _model():
    return RandomForestClassifier(n_estimators=150, min_samples_leaf=10, max_samples=0.5, n_jobs=-1, random_state=42)


def score_clients(inc, inv):
    """Return (client table as of the last transaction date, model report)."""
    end = inc["date"].max()
    now = snapshot_features(inc, inv, [end]).drop(columns="cutoff")
    cuts = pd.date_range(inc["date"].min() + pd.Timedelta(days=120), end - pd.Timedelta(days=HORIZON), freq="14D")
    snaps = snapshot_features(inc, inv, cuts) if len(cuts) else pd.DataFrame()
    report = {"mode": "rules", "horizon_days": HORIZON, "as_of": str(end.date()), "snapshots": len(snaps)}

    pos = int(snaps["churned"].sum()) if len(snaps) else 0
    if len(snaps) < 200 or pos < 20 or len(snaps) - pos < 20:
        report["reason"] = "Not enough history to learn from yet (needs ~8+ months and some lapsed clients)."
        now["ml_prob"] = np.nan
        return now, report

    split = snaps["cutoff"].quantile(0.75, interpolation="nearest")
    train = snaps[snaps["cutoff"] <= split - pd.Timedelta(days=HORIZON)]      # purge: labels look 90d ahead
    test = snaps[(snaps["cutoff"] > split) & (snaps["recency"] <= 180)]       # clients still in play
    if train["churned"].nunique() == 2 and test["churned"].nunique() == 2:
        p = _model().fit(train[FEATURES], train["churned"]).predict_proba(test[FEATURES])[:, 1]
        report.update(
            auc=round(roc_auc_score(test["churned"], p), 3),
            baseline_auc=round(roc_auc_score(test["churned"], test["overdue_ratio"]), 3),
            brier=round(brier_score_loss(test["churned"], p), 3),
            base_rate=round(float(test["churned"].mean()), 3),
            train_rows=len(train), test_rows=len(test), test_from=str(split.date()))

    model = _model().fit(snaps[FEATURES], snaps["churned"])
    now["ml_prob"] = model.predict_proba(now[FEATURES])[:, 1] * 100
    imp = pd.Series(model.feature_importances_, index=FEATURES).sort_values(ascending=False)
    report.update(mode="ml", drivers={k: round(float(v), 3) for k, v in imp.head(5).items()})
    return now, report
