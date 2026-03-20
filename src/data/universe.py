from __future__ import annotations


_UNIVERSES: dict[str, tuple[str, ...]] = {
    "topix_top_10": (
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
    ),
}


def list_universe_names() -> list[str]:
    return list(_UNIVERSES.keys())


def get_universe(name: str) -> list[str]:
    try:
        return list(_UNIVERSES[name])
    except KeyError as exc:
        raise KeyError(f"Unknown universe: {name}") from exc


def get_topix_top_10() -> list[str]:
    """Returns the named TOPIX top 10 universe."""
    return get_universe("topix_top_10")
