import pandas as pd

from src.research.factor_analysis import run_factor_analysis


def test_run_factor_analysis_resolves_book_values_by_rebalance_date():
    dates = pd.bdate_range("2024-01-01", "2024-07-03")
    data = {
        "AAA.T": pd.DataFrame({"Close": [100.0] * len(dates)}, index=dates),
        "BBB.T": pd.DataFrame({"Close": [100.0] * len(dates)}, index=dates),
    }

    def book_values_as_of(as_of_date):
        if as_of_date < pd.Timestamp("2024-07-01"):
            return {"AAA.T": 100.0, "BBB.T": 50.0}
        return {"AAA.T": 50.0, "BBB.T": 100.0}

    result = run_factor_analysis(
        data_dfs=data,
        start=pd.Timestamp("2024-06-03"),
        end=pd.Timestamp("2024-07-03"),
        weight_mom=0.0,
        weight_vol=0.0,
        weight_rev=0.0,
        weight_val=1.0,
        book_values=book_values_as_of,
        top_n=1,
    )

    july_scores = result["period_scores"][pd.Timestamp("2024-07-01")]
    assert july_scores.iloc[0]["symbol"] == "BBB.T"
