def get_topix_top_10() -> list[str]:
    """Returns a hardcoded list of the top 10 TOPIX components by market cap (approximate).
    Suffix '.T' is required for Yahoo Finance Japanese stocks."""
    return [
        "7203.T",  # Toyota
        "6758.T",  # Sony
        "8306.T",  # Mitsubishi UFJ
        "6861.T",  # Keyence
        "9984.T",  # SoftBank Group
        "9432.T",  # NTT
        "8035.T",  # Tokyo Electron
        "8316.T",  # SMFG
        "6098.T",  # Recruit
        "7974.T",  # Nintendo
    ]
