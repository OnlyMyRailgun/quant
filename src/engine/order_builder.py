import pandas as pd


def build_orders(
    period_scores: dict[pd.Timestamp, pd.DataFrame],
    top_n: int,
    commission_rate: float,
    slippage_pct: float,
) -> pd.DataFrame:
    """Convert per-date scorer outputs into target-percentage orders for vectorbt.

    Parameters
    ----------
    period_scores : dict[pd.Timestamp, pd.DataFrame]
        Mapping of rebalance date to scored DataFrame with columns:
        symbol, total_score, rank, is_top_n, price.
    top_n : int
        Number of top-ranked stocks to hold.
    commission_rate : float
        Commission rate as a decimal (e.g. 0.001 = 10bp).
    slippage_pct : float
        Slippage as a decimal applied to execution price
        (execution_price = price * (1 - slippage_pct)).

    Returns
    -------
    pd.DataFrame
        Orders DataFrame with columns: [symbol, date, size, price, fees].
    """
    rows = []
    for date in sorted(period_scores):
        df = period_scores[date]
        if df.empty:
            continue

        top_df = df[df["is_top_n"] == True]
        if top_df.empty:
            continue

        n = min(top_n, len(top_df))
        target_weight = 0.95 / n

        for _, row in top_df.head(n).iterrows():
            price = row["price"] * (1 - slippage_pct)
            fees = abs(target_weight) * price * commission_rate
            rows.append({
                "symbol": row["symbol"],
                "date": date,
                "size": target_weight,
                "price": price,
                "fees": fees,
            })

    if not rows:
        return pd.DataFrame(columns=["symbol", "date", "size", "price", "fees"])

    return pd.DataFrame(rows, columns=["symbol", "date", "size", "price", "fees"])
