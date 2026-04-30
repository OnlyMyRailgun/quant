"""TOPIX universe loader from J-Quants API.

Provides:
  - get_topix_universe() — fetch + cache constituent lists
  - get_industry_map() — 33-sector JPX industry classification
  - get_stock_master() — ticker → name, sector, scale lookup
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

CACHE_DIR = Path(".data_cache")
UNIVERSE_CACHE = CACHE_DIR / "jquants_universe.json"
INDUSTRY_CACHE = CACHE_DIR / "jquants_industries.json"


def _get_client():
    from jquantsapi import ClientV2
    return ClientV2()


def get_topix_universe(size: str = "large100", force_refresh: bool = False) -> list[str]:
    """Get TOPIX constituent ticker codes.

    Args:
        size: Universe size —
            "core30" → TOPIX Core 30 (~30 stocks)
            "large70" → TOPIX Large 70 (~70 stocks)
            "large100" → Core30 + Large70 (~100 stocks)
            "mid400" → TOPIX Mid 400 (~400 stocks)
            "topix500" → Core30 + Large70 + Mid400 (~500 stocks)
        force_refresh: Re-fetch from J-Quants API.

    Returns:
        List of ticker codes with .T suffix (e.g., "7203.T").
    """
    scale_map = {
        "core30": ["TOPIX Core30"],
        "large70": ["TOPIX Large70"],
        "large100": ["TOPIX Core30", "TOPIX Large70"],
        "mid400": ["TOPIX Mid400"],
        "topix500": ["TOPIX Core30", "TOPIX Large70", "TOPIX Mid400"],
    }
    if size not in scale_map:
        raise ValueError(f"Unknown size '{size}'. Choose from: {list(scale_map.keys())}")

    if not force_refresh and UNIVERSE_CACHE.exists():
        with open(UNIVERSE_CACHE) as f:
            cached = json.load(f)
        if size in cached:
            return cached[size]

    cli = _get_client()
    df = cli.get_list()
    scales = scale_map[size]
    filtered = df[df["ScaleCat"].isin(scales)]
    codes = [f"{code}.T" for code in filtered["Code"].tolist()]

    # Update cache
    cached = {}
    if UNIVERSE_CACHE.exists():
        with open(UNIVERSE_CACHE) as f:
            cached = json.load(f)
    cached[size] = codes
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(UNIVERSE_CACHE, "w") as f:
        json.dump(cached, f, indent=2)

    return codes


def get_industry_map(force_refresh: bool = False) -> dict[str, str]:
    """Get 33-sector industry classification for all listed stocks.

    Returns:
        {ticker_code: sector_name_en} e.g., {"7203.T": "Transportation Equipment"}
    """
    if not force_refresh and INDUSTRY_CACHE.exists():
        with open(INDUSTRY_CACHE) as f:
            return json.load(f)

    cli = _get_client()
    df = cli.get_list()
    ind_map = {}
    for _, row in df.iterrows():
        code = f"{row['Code']}.T"
        sector = row.get("S33NmEn", "Other")
        ind_map[code] = sector

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(INDUSTRY_CACHE, "w") as f:
        json.dump(ind_map, f, indent=2)

    return ind_map


def get_stock_master(force_refresh: bool = False) -> pd.DataFrame:
    """Get full stock master with codes, names, sectors, market segments.

    Returns:
        DataFrame with columns: Code, CoNameEn, S33NmEn, MktNmEn, ScaleCat
    """
    cli = _get_client()
    df = cli.get_list()
    df["Ticker"] = df["Code"].apply(lambda c: f"{c}.T")
    return df[["Ticker", "CoNameEn", "S33NmEn", "MktNmEn", "ScaleCat"]]
