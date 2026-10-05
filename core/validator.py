REQUIRED = ["client_id", "amount", "date"]


def validate_transactions(df):
    """Fail early with a clear message; row-level cleaning happens in data_pipelining."""
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required column(s): {', '.join(missing)}")
    return df
