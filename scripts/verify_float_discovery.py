from __future__ import annotations

from pathlib import Path
import sys

if __package__ in {None, ""}:
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

from src.data.fundamentals.float_provider import FloatProvider


def _fmt(value: int | None) -> str:
    if value is None:
        return "UNKNOWN"
    if value >= 1_000_000_000:
        return f"{value/1_000_000_000:.1f}B"
    if value >= 1_000_000:
        return f"{value/1_000_000:.1f}M"
    if value >= 1_000:
        return f"{value/1_000:.1f}K"
    return str(value)


def main() -> None:
    symbols = [
        "PRSO", "EDSA", "ANTX", "AAPL", "MSFT", "NVDA", "AMD", "TSLA", "META", "AMZN",
        "PLTR", "SOFI", "RIVN", "LCID", "GME", "MARA", "RIOT", "PENN", "NIO", "F",
    ]
    provider = FloatProvider()

    print("FLOAT DISCOVERY TEST")
    print("--------------------")
    print()
    print("Symbol  Float     Source")

    success = 0
    missing = 0
    for symbol in symbols:
        value, source = provider.get_float(symbol)
        if value is None or source == "UNKNOWN":
            missing += 1
            source_out = "NONE"
        else:
            success += 1
            source_out = source
        print(f"{symbol:<6}  {_fmt(value):<8}  {source_out}")

    print()
    print("Summary:")
    print()
    print(f"tested={len(symbols)}")
    print(f"success={success}")
    print(f"missing={missing}")


if __name__ == "__main__":
    main()
