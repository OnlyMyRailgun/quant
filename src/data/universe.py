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
    "japan_large_30": (
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
        "4063.T",  # Shin-Etsu Chemical
        "6501.T",  # Hitachi
        "7741.T",  # HOYA
        "4519.T",  # Chugai Pharmaceutical
        "4502.T",  # Takeda Pharmaceutical
        "8411.T",  # Mizuho Financial Group
        "6954.T",  # Fanuc
        "6981.T",  # Murata Manufacturing
        "9433.T",  # KDDI
        "6367.T",  # Daikin
        "4543.T",  # Terumo
        "8058.T",  # Mitsubishi Corp
        "8766.T",  # Tokio Marine
        "6273.T",  # SMC
        "7267.T",  # Honda
        "6902.T",  # Denso
        "2413.T",  # M3
        "7733.T",  # Olympus
        "8031.T",  # Mitsui
        "6702.T",  # Fujitsu
    ),
    "japan_broad_50": (
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
        "4063.T",  # Shin-Etsu Chemical
        "6501.T",  # Hitachi
        "7741.T",  # HOYA
        "4519.T",  # Chugai Pharmaceutical
        "4502.T",  # Takeda Pharmaceutical
        "8411.T",  # Mizuho Financial Group
        "6954.T",  # Fanuc
        "6981.T",  # Murata Manufacturing
        "9433.T",  # KDDI
        "6367.T",  # Daikin
        "4543.T",  # Terumo
        "8058.T",  # Mitsubishi Corp
        "8766.T",  # Tokio Marine
        "6273.T",  # SMC
        "7267.T",  # Honda
        "6902.T",  # Denso
        "2413.T",  # M3
        "7733.T",  # Olympus
        "8031.T",  # Mitsui
        "6702.T",  # Fujitsu
        "7731.T",  # Nikon
        "8001.T",  # Itochu
        "8015.T",  # Toyota Tsusho
        "8053.T",  # Sumitomo Corp
        "8591.T",  # ORIX
        "9101.T",  # Nippon Yusen
        "9104.T",  # Mitsui O.S.K. Lines
        "9107.T",  # Kawasaki Kisen
        "9020.T",  # JR East
        "9021.T",  # JR West
        "9022.T",  # JR Central
        "8801.T",  # Mitsui Fudosan
        "8308.T",  # Resona Holdings
        "8750.T",  # Dai-ichi Life
        "3382.T",  # Seven & i Holdings
        "2502.T",  # Asahi Group
        "5108.T",  # Bridgestone
        "4901.T",  # Fujifilm Holdings
        "2802.T",  # Ajinomoto
        "2269.T",  # Meiji Holdings
    ),
}


def list_universe_names() -> list[str]:
    return list(_UNIVERSES.keys())


def format_unknown_universe_message(name: str) -> str:
    available = ", ".join(list_universe_names())
    return f"Invalid universe name: {name}. Available universes: {available}"


def get_universe(name: str) -> list[str]:
    try:
        return list(_UNIVERSES[name])
    except KeyError as exc:
        raise KeyError(f"Unknown universe: {name}") from exc


def get_topix_top_10() -> list[str]:
    """Returns the named TOPIX top 10 universe."""
    return get_universe("topix_top_10")
