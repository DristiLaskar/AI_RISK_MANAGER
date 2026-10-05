import numpy as np
import pandas as pd

UNASSIGNED = "UNASSIGNED"
_EXPENSE_WORDS = ("exp", "debit", "cost", "out", "purchase", "bill")


def clean_transactions(df):
    """Normalise a raw transaction frame. Returns (clean_df, quality_report)."""
    rep = {"rows_in": len(df)}
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
    n = len(df)
    df = df.dropna(subset=["date", "amount"])
    rep["unreadable_rows"] = n - len(df)

    # income vs expense: explicit labels win, otherwise the sign decides
    if "type" in df.columns:
        t = df["type"].astype(str).str.lower()
        df["type"] = np.where(t.str.contains("|".join(_EXPENSE_WORDS)), "expense", "income")
    else:
        df["type"] = np.where(df["amount"] < 0, "expense", "income")
    df["amount"] = df["amount"].abs()

    df["client_id"] = df["client_id"].astype("string").str.strip().replace("", pd.NA)
    n = len(df)
    df = df.drop_duplicates(subset=["date", "client_id", "amount", "type"])
    rep["duplicates_removed"] = n - len(df)

    # income without a client still counts towards revenue, it just can't be scored per client
    miss = df["client_id"].isna()
    df.loc[miss, "client_id"] = UNASSIGNED
    rep["income_without_client"] = int((miss & (df["type"] == "income")).sum())
    return df.sort_values("date").reset_index(drop=True), rep


def clean_invoices(inv):
    """Invoices -> client_id, paid_date, delay (days paid after due)."""
    if inv is None or inv.empty:
        return pd.DataFrame(columns=["client_id", "paid_date", "delay"])
    inv = inv.copy()
    inv["paid_date"] = pd.to_datetime(inv["paid_date"], errors="coerce")
    inv["due_date"] = pd.to_datetime(inv["due_date"], errors="coerce")
    inv = inv.dropna(subset=["paid_date", "due_date", "client_id"])
    inv["client_id"] = inv["client_id"].astype(str).str.strip()
    inv["delay"] = (inv["paid_date"] - inv["due_date"]).dt.days
    return inv[["client_id", "paid_date", "delay"]]


def monthly_summary(tx):
    m = tx.assign(month=tx["date"].dt.to_period("M").dt.to_timestamp())
    m = m.pivot_table(index="month", columns="type", values="amount", aggfunc="sum", fill_value=0)
    m = m.reindex(columns=["income", "expense"], fill_value=0)
    m.columns = ["revenue", "expenses"]
    m = m.astype(float)
    m = m.reindex(pd.date_range(m.index.min(), m.index.max(), freq="MS"), fill_value=0)
    m.index.name = "date"
    m["net_cash_flow"] = m["revenue"] - m["expenses"]
    return m
