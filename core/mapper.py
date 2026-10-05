import pandas as pd
import re
from rapidfuzz import process


COLUMN_SYNONYMS = {

    "client_id": [
        "client",
        "client_id",
        "customer",
        "customer_id",
        "account",
        "company",
        "client name",
        "customer name",
        "buyer"
    ],

    "date": [
        "date",
        "transaction_date",
        "payment_date",
        "invoice_date",
        "order_date",
        "purchase_date"
    ],

    "amount": [
        "amount",
        "revenue",
        "sales",
        "transaction_amount",
        "payment",
        "income",
        "value",
        "price"
    ],

    "invoice_amount": [
        "invoice",
        "invoice_amount",
        "invoice_value",
        "bill",
        "billing",
        "total_invoice"
    ],

    "payment_delay": [
        "delay",
        "payment_delay",
        "late_days",
        "days_late",
        "days_overdue"
    ],

    "type": [
        "type",
        "transaction type",
        "direction",
        "kind"
    ],

    "industry": [
        "industry",
        "sector",
        "business_type"
    ]

}


def normalize_column(col):

    col = col.lower()

    col = re.sub(r"[_\-]", " ", col)

    col = re.sub(r"\s+", " ", col).strip()

    return col


def auto_map_columns(df):

    df = df.copy()

    new_columns = {}

    for col in df.columns:

        clean_col = normalize_column(col)

        best_match = None
        best_score = 0
        best_target = None

        for target, synonyms in COLUMN_SYNONYMS.items():

            match = process.extractOne(
                clean_col,
                synonyms
            )

            if match and match[1] > best_score:

                best_match = match[0]
                best_score = match[1]
                best_target = target

        if best_score >= 70 and best_target not in new_columns.values():
            new_columns[col] = best_target

    df = df.rename(columns=new_columns)

    return df