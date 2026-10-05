class BusinessRiskEngine:

    def calculate_risk_score(self, active, monthly, burnout, forecast):
        """0-100 blend of at-risk client share, revenue volatility, forecast direction and burnout."""
        client_risk = (active["RISK_%"] > 60).mean() * 100 if len(active) else 100
        rev = monthly["revenue"].tail(24)
        vol = min(rev.std() / (rev.mean() + 1e-9) * 100, 100)
        falling = len(forecast) >= 2 and forecast[-1] < forecast[0]
        score = 0.4 * burnout + 0.3 * client_risk + 0.2 * vol + 0.1 * (70 if falling else 20)
        return round(min(score, 100), 1)

    def risk_status(self, score):
        return ("Healthy" if score < 30 else "Moderate Risk" if score < 60
                else "High Risk" if score < 80 else "Critical")
