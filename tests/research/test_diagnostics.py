import pandas as pd

from src.research.walk_forward import (
    aggregate_portfolio_diagnostics,
    build_portfolio_diagnostics,
)


def test_build_portfolio_diagnostics_calculates_hit_rate_and_contributors():
    symbol_returns = pd.DataFrame(
        [
            {"symbol": "AAA.T", "return_pct": 3.2},
            {"symbol": "BBB.T", "return_pct": -1.4},
            {"symbol": "CCC.T", "return_pct": 0.0},
            {"symbol": "DDD.T", "return_pct": 2.1},
        ]
    )

    diagnostics = build_portfolio_diagnostics(symbol_returns, contributor_count=2)

    assert diagnostics["hit_rate"] == 0.5
    assert diagnostics["top_contributors"] == [
        {"symbol": "AAA.T", "return_pct": 3.2},
        {"symbol": "DDD.T", "return_pct": 2.1},
    ]
    assert diagnostics["bottom_contributors"] == [
        {"symbol": "BBB.T", "return_pct": -1.4},
        {"symbol": "CCC.T", "return_pct": 0.0},
    ]


def test_build_portfolio_diagnostics_handles_empty_symbol_returns():
    diagnostics = build_portfolio_diagnostics(pd.DataFrame(columns=["symbol", "return_pct"]))

    assert diagnostics == {
        "hit_rate": None,
        "top_contributors": [],
        "bottom_contributors": [],
    }


def test_aggregate_portfolio_diagnostics_combines_window_payloads_deterministically():
    diagnostics = aggregate_portfolio_diagnostics(
        [
            {
                "hit_rate": 0.5,
                "top_contributors": [
                    {"symbol": "AAA.T", "return_pct": 2.0},
                    {"symbol": "BBB.T", "return_pct": 1.0},
                ],
                "bottom_contributors": [
                    {"symbol": "CCC.T", "return_pct": -1.5},
                ],
            },
            {
                "hit_rate": 1.0,
                "top_contributors": [
                    {"symbol": "AAA.T", "return_pct": 1.5},
                    {"symbol": "DDD.T", "return_pct": 1.2},
                ],
                "bottom_contributors": [
                    {"symbol": "CCC.T", "return_pct": -0.5},
                    {"symbol": "EEE.T", "return_pct": -0.1},
                ],
            },
        ],
        contributor_count=2,
    )

    assert diagnostics == {
        "avg_hit_rate": 0.75,
        "top_contributors": [
            {"symbol": "AAA.T", "return_pct": 3.5},
            {"symbol": "DDD.T", "return_pct": 1.2},
        ],
        "bottom_contributors": [
            {"symbol": "CCC.T", "return_pct": -2.0},
            {"symbol": "EEE.T", "return_pct": -0.1},
        ],
    }


def test_aggregate_portfolio_diagnostics_ignores_missing_hit_rates():
    diagnostics = aggregate_portfolio_diagnostics(
        [
            {"hit_rate": None, "top_contributors": [], "bottom_contributors": []},
            {"hit_rate": 0.25, "top_contributors": [], "bottom_contributors": []},
        ]
    )

    assert diagnostics == {
        "avg_hit_rate": 0.25,
        "top_contributors": [],
        "bottom_contributors": [],
    }
