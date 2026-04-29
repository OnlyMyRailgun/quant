#!/usr/bin/env python3
"""Compare backtrader vs vectorbt engine output on a small universe."""
from __future__ import annotations
import sys
import pandas as pd
from src.data.bulk_loader import fetch_universe
from src.optimize import evaluate_weight_tuple

SYMBOLS = ["7203.T", "8306.T", "9432.T"]
START, END = "2023-01-01", "2024-01-01"
WEIGHTS = (1.0, 0.0, 0.0)

print("Fetching data...")
data = fetch_universe(SYMBOLS, START, END)

print("Running backtrader...")
bt = evaluate_weight_tuple(data, START, END, WEIGHTS, engine="backtrader")

print("Running vectorbt...")
vbt_result = evaluate_weight_tuple(data, START, END, WEIGHTS, engine="vectorbt")

print(f"\n{'Metric':<20} {'Backtrader':>12} {'Vectorbt':>12} {'Diff':>10}")
print("-" * 56)
for key in ["return_pct", "sharpe", "drawdown"]:
    b, v = bt[key], vbt_result[key]
    diff = abs(b - v)
    print(f"{key:<20} {b:>12.4f} {v:>12.4f} {diff:>10.4f}")

return_diff = abs(bt["return_pct"] - vbt_result["return_pct"])
sharpe_diff = abs(bt["sharpe"] - vbt_result["sharpe"])

ok = return_diff < 1.0 and sharpe_diff < 0.05
print(f"\nReturn < 1% diff:  {'PASS' if return_diff < 1.0 else 'FAIL'} ({return_diff:.4f})")
print(f"Sharpe < 0.05 diff: {'PASS' if sharpe_diff < 0.05 else 'FAIL'} ({sharpe_diff:.4f})")
print(f"OVERALL:            {'PASS' if ok else 'FAIL'}")
sys.exit(0 if ok else 1)
