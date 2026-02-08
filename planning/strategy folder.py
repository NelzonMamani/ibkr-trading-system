from pathlib import Path

BASE_DIR = Path("03_STRATEGIES")

STRATEGIES = [
    "P1_ROSS_MOMENTUM",
    "P2_STATISTICAL_INTRADAY_MOMENTUM",
    "P3_MEAN_REVERSION",
    "P4_LONG_HORIZON_VALUE",
    "P5_OPENING_DRIVE",
    "P6_VWAP_RECLAIM",
    "P7_POWER_HOUR",
    "P8_VOLATILITY_EXPANSION",
]

SUBFOLDERS = [
    "GOVERNANCE",
    "CODEX_INSTRUCTIONS",
]

def main():
    BASE_DIR.mkdir(parents=True, exist_ok=True)

    for strategy in STRATEGIES:
        strategy_path = BASE_DIR / strategy
        strategy_path.mkdir(exist_ok=True)

        for sub in SUBFOLDERS:
            (strategy_path / sub).mkdir(exist_ok=True)

    print("04_STRATEGIES (P1–P8) folder structure created successfully.")

if __name__ == "__main__":
    main()
