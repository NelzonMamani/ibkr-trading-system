# create_catalogue_strategies.py
from pathlib import Path

BASE = Path("TRADING_OS_MASTER_CATALOGUE") / "03_STRATEGIES"

STRATEGIES = [
    "P1_ROSS_MOMENTUM",
    "P2_STATISTICAL_INTRADAY_MOMENTUM",
    "P3_MEAN_REVERSION",
    "P4_LONG_HORIZON_VALUE",
    "P5_OPENING_DRIVE",
    "P6_VWAP_RECLAIM",
    "P7_POWER_HOUR",
    "P8_VOLATILITY_EXPANSION",
    "P9_RANGE_BOUND_FADE",
    "P10_SUPPORT_RESISTANCE_CHANNEL",
    "P11_EVENT_EARNINGS_REACTION",
    "P12_EVENT_NEWS_SHOCK_CONTINUATION",
    "P13_VOLATILITY_CONTRACTION_BREAKOUT",
    "P14_VOLATILITY_CARRY_RISK_PREMIUM",
    "P15_PAIRS_DIVERGENCE_REVERSION",
    "P16_CROSS_SECTIONAL_RELATIVE_STRENGTH_ROTATION",
    "P17_TIME_BASED_SEASONALITY",
    "P18_TREND_FOLLOWING_CLASSIC",
    "P19_LONG_HORIZON_QUALITY_COMPOUNDER",
    "P20_REGIME_ADAPTIVE_META_ALLOCATOR",
]

SUBFOLDERS = ["GOVERNANCE", "CODEX_INSTRUCTIONS"]

def main() -> None:
    BASE.mkdir(parents=True, exist_ok=True)

    # Optional top-level readme placeholders (non-destructive)
    for top in ["00_READ_FIRST.md", "STRATEGY_CERTIFICATION_RULES.md"]:
        p = BASE / top
        if not p.exists():
            p.write_text(f"# {top}\n\n", encoding="utf-8")

    for name in STRATEGIES:
        sp = BASE / name
        sp.mkdir(exist_ok=True)
        for sub in SUBFOLDERS:
            (sp / sub).mkdir(exist_ok=True)

    print(f"Created/verified catalogue strategy folders under: {BASE}")

if __name__ == "__main__":
    main()
