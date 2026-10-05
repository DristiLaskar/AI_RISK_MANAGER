import pandas as pd
import numpy as np
import random
import os
from datetime import datetime, timedelta

# -----------------------------
# SETTINGS
# -----------------------------
np.random.seed(99)
random.seed(99)   # reproducible: the stdlib RNG was previously unseeded

NUM_CLIENTS = 100
MONTHS = 60
START_DATE = datetime(2020, 1, 1)

output_dir = "data"

if not os.path.exists(output_dir):
    os.makedirs(output_dir)

# -----------------------------
# GENERATE CLIENTS
# -----------------------------
client_ids = [f"C{i:03d}" for i in range(1, NUM_CLIENTS + 1)]

clients_data = []

for cid in client_ids:

    clients_data.append({
        "client_id": cid,
        "industry": random.choice(["Tech", "Marketing", "Retail", "Finance", "Art"]),
        "contract_type": random.choice(["Retainer", "Project", "Hourly"]),
        "base_value": random.randint(500, 12000)
    })

df_clients = pd.DataFrame(clients_data)

# Permanent churn: ~35% of non-loyal clients leave for good somewhere in months 18-56.
# (The old generator zeroed a single month, so nobody ever really churned.)
churn_month = {
    cid: random.randint(18, 56)
    for cid in client_ids
    if int(cid[1:]) > 10 and random.random() < 0.35
}

# -----------------------------
# GENERATE TRANSACTIONS
# -----------------------------
transactions = []

for month in range(MONTHS):

    month_start = START_DATE + pd.DateOffset(months=month)

    # -----------------------------
    # EXPENSES
    # -----------------------------

    # Fixed monthly rent
    transactions.append({
        "date": month_start,
        "client_id": "SELF",
        "amount": 1200,
        "type": "expense",
        "category": "Rent"
    })

    # Operational expense
    transactions.append({
        "date": month_start + timedelta(days=random.randint(1,15)),
        "client_id": "SELF",
        "amount": random.randint(1000,5000),
        "type": "expense",
        "category": "Operations"
    })

    # Contractor payment
    if random.random() > 0.75:

        transactions.append({
            "date": month_start + timedelta(days=random.randint(1,20)),
            "client_id": "SELF",
            "amount": random.randint(3000,8000),
            "type": "expense",
            "category": "Contractor"
        })

    # Rare financial shocks
    if random.random() > 0.9:

        transactions.append({
            "date": month_start + timedelta(days=random.randint(1,25)),
            "client_id": "SELF",
            "amount": random.randint(2000,15000),
            "type": "expense",
            "category": random.choice(["Taxes", "Hardware", "Emergency", None])
        })

    # -----------------------------
    # INCOME
    # -----------------------------
    for _, client in df_clients.iterrows():

        cid = client["client_id"]

        # Loyal stable clients
        if int(cid[1:]) <= 10:
            prob_pay = 0.95
            volatility = 0.05

        # Medium ghost clients
        elif int(cid[1:]) <= 50:
            prob_pay = 0.60
            volatility = 0.40

        # Risky clients
        else:
            prob_pay = 0.30
            volatility = 0.80

        # Churn: a fading phase (smaller, rarer payments) 4 months before leaving, then silence
        fade = 1.0
        if cid in churn_month:
            if month >= churn_month[cid]:
                prob_pay = 0
            elif month >= churn_month[cid] - 4:
                prob_pay *= 0.7
                fade = 0.6

        if random.random() < prob_pay:

            pay_date = month_start + timedelta(days=random.randint(1,45))

            amount = client["base_value"] * fade * random.uniform(1-volatility,1+volatility)

            # Fragmented payments
            if random.random() > 0.8:

                part1 = round(amount * 0.4, 2)
                part2 = round(amount * 0.6, 2)

                transactions.append({
                    "date": pay_date,
                    "client_id": cid,
                    "amount": part1,
                    "type": "income",
                    "category": "Partial"
                })

                transactions.append({
                    "date": pay_date + timedelta(days=4),
                    "client_id": cid,
                    "amount": part2,
                    "type": "income",
                    "category": "Partial"
                })

            else:

                transactions.append({
                    "date": pay_date,
                    "client_id": cid,
                    "amount": round(amount,2),
                    "type": "income",
                    "category": "Service"
                })

            # Duplicate entries (human error)
            if random.random() > 0.98:

                transactions.append({
                    "date": pay_date,
                    "client_id": cid,
                    "amount": round(amount,2),
                    "type": "income",
                    "category": "Service"
                })

# -----------------------------
# CREATE DATAFRAME
# -----------------------------
df_tx = pd.DataFrame(transactions)

# -----------------------------
# FINAL DATA CORRUPTION
# -----------------------------

# Missing client IDs
df_tx.loc[df_tx.sample(frac=0.05).index, "client_id"] = np.nan

# Random bad categories
df_tx.loc[df_tx.sample(frac=0.1).index, "category"] = "UNKNOWN_ERROR"

# -----------------------------
# GENERATE INVOICES
# -----------------------------
invoices = []

invoice_id = 1

income_df = df_tx[df_tx["type"] == "income"].copy().dropna(subset=["client_id"])

for _, tx in income_df.iterrows():

    due_date = tx["date"] - timedelta(days=random.randint(7,45))
    paid_date = tx["date"]

    invoices.append({
        "invoice_id": f"INV{invoice_id:05d}",
        "client_id": tx["client_id"],
        "due_date": due_date,
        "paid_date": paid_date,
        "amount": tx["amount"]
    })

    invoice_id += 1

df_invoices = pd.DataFrame(invoices)

# -----------------------------
# SAVE FILES
# -----------------------------
df_tx.to_csv(os.path.join(output_dir,"transactions.csv"),index=False)
df_clients.to_csv(os.path.join(output_dir,"clients.csv"),index=False)
df_invoices.to_csv(os.path.join(output_dir,"invoices.csv"),index=False)

print(f"🔥 CHAOS DATA GENERATED: {len(df_tx)} transactions for {NUM_CLIENTS} clients over {MONTHS} months")