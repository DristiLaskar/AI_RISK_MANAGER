"""Backtest the churn model on a dataset:  python train_model.py [transactions.csv] [invoices.csv]

There is no saved model file any more: the model is fitted on each dataset's own history
(see core/churn.py), so this script just prints how well that works on the data you give it.
"""
import sys

import pandas as pd

from core.analysis import run

args = sys.argv[1:]
tx = pd.read_csv(args[0] if args else "data/transactions.csv")
inv = pd.read_csv(args[1]) if len(args) > 1 else (pd.read_csv("data/invoices.csv") if not args else None)
for k, v in run(tx, inv)["model"].items():
    print(f"{k:>14}: {v}")
