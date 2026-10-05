import numpy as np
import pandas as pd


class AdaptiveIntelligenceEngine:
    """Lifecycle stage + hybrid (ML + rules) churn risk for one client row."""

    def predict_lifecycle(self, r):
        if r["payment_count"] <= 2:
            return "NEW"
        if r["recency"] > max(90, 3 * r["avg_gap"]):
            return "CHURNED"
        if r["revenue_trend"] < -0.15:
            return "DECLINING"
        if r["revenue_trend"] > 0.15:
            return "GROWING"
        calm = r["ml_prob"] < 15 if pd.notna(r["ml_prob"]) else r["volatility"] < 0.35
        return "STABLE" if calm else "ACTIVE"

    def rule_risk(self, r):
        return (50 if r["overdue_ratio"] > 1.5 else 0) + (30 if r["volatility"] > 0.5 else 0)

    def calculate_hybrid_risk(self, r):
        """90-day churn risk in %. Clients with little history lean on rules; falls back to rules if no ML."""
        rule = self.rule_risk(r)
        if pd.isna(r["ml_prob"]):
            return float(rule)
        w = min(r["payment_count"] / 15, 0.8)
        return round(r["ml_prob"] * w + rule * (1 - w), 1)


class BusinessHealthEngine:
    """Burnout = how fragile the client base is (at-risk share, irregularity, dependence on one client)."""

    def calculate_burnout_risk(self, active):
        if len(active) == 0:
            return 100.0
        high = (active["RISK_%"] > 60).mean()
        vol = min(active["volatility"].mean(), 1)
        top = active["run_rate"].max() / (active["run_rate"].sum() + 1e-9)
        return round(min(0.4 * high + 0.3 * vol + 0.3 * top, 1) * 100, 1)


class HeuristicPricingOptimizer:
    def suggest_adjustment(self, r):
        if r["STAGE"] == "CHURNED":
            return "Win-back outreach"
        if r["RISK_%"] > 60:
            return "Retention Discount (-10%)"
        return {"DECLINING": "Reduce Rate 10%", "GROWING": "Premium Rate (+15%)",
                "STABLE": "Standard Increase (+5%)"}.get(r["STAGE"], "Maintain Rate")


class CLVEngine:
    """Expected revenue over the next 12 months = monthly run-rate x expected months the client stays.

    p is the 90-day churn probability, so monthly survival is (1-p)^(1/3).
    """

    @staticmethod
    def survival(p, months):
        s = (1 - np.clip(np.asarray(p) / 100, 0.001, 0.999)) ** (1 / 3)
        return s ** months

    def estimate_predictive_clv(self, r):
        return round(r["run_rate"] * sum(self.survival(r["RISK_%"], m) for m in range(1, 13)), 2)
