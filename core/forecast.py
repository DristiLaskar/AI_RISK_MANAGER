import numpy as np
import pandas as pd


def _fit_predict(y, h):
    """Least-squares linear trend, plus a month-of-year effect once there are 2 full years."""
    n = len(y)
    t = np.arange(n + h)
    cols = [np.ones(n + h), t]
    if n >= 24:
        cols += [(t % 12 == k).astype(float) for k in range(1, 12)]
    X = np.column_stack(cols)
    beta, *_ = np.linalg.lstsq(X[:n], y, rcond=None)
    fit = X @ beta
    sigma = np.sqrt(((y - fit[:n]) ** 2).sum() / max(n - X.shape[1], 1))
    return fit[n:], sigma


def trim_partial(monthly, last_date):
    """Drop the final month when the data stops well before it ends (it would bias the trend)."""
    if len(monthly) > 1 and (last_date + pd.offsets.MonthEnd(0) - last_date).days > 3:
        return monthly.iloc[:-1]
    return monthly


def forecast(series, h=3):
    """h-month forecast with an 80% band and a rolling one-step backtest error."""
    y = series.astype(float).values[-36:]
    if len(y) < 4:                                   # too short to fit a trend: flat, wide band
        yhat, sigma = np.full(h, y.mean()), max(y.std(), abs(y.mean()) * 0.3)
    else:
        yhat, sigma = _fit_predict(y, h)
    band = 1.28 * sigma * np.sqrt(1 + np.arange(1, h + 1) / len(y))

    errs, acts = [], []
    for i in range(max(len(y) - 6, 6), len(y)):
        errs.append(abs(_fit_predict(y[:i], 1)[0][0] - y[i]))
        acts.append(abs(y[i]))
    err = sum(errs) / (sum(acts) + 1e-9) * 100 if errs else None

    months = pd.date_range(series.index[-1] + pd.offsets.MonthBegin(1), periods=h, freq="MS")
    r = lambda a: [round(float(v), 2) for v in a]
    return {
        "months": [d.strftime("%Y-%m") for d in months],
        "yhat": r(yhat), "lo": r(yhat - band), "hi": r(yhat + band),
        "error_pct": None if err is None else round(float(err), 1),
    }
