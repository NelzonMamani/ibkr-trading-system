"""CLI tool to audit float provider caching and sources."""

from __future__ import annotations

import argparse

from src.market_data.float_provider import FloatProvider
from src.utils.time_utils import to_ny_time, utc_now


def main() -> int:
    parser = argparse.ArgumentParser(description="Float audit tool")
    parser.add_argument("--symbols", required=True, help="Comma-separated symbols list")
    args = parser.parse_args()

    symbols = [symbol.strip().upper() for symbol in args.symbols.split(",") if symbol.strip()]
    session_date = to_ny_time(utc_now()).date().isoformat()
    provider = FloatProvider()
    print(f"[FLOAT_AUDIT] session_date={session_date} symbols={symbols}")
    for symbol in symbols:
        record = provider.get_float(symbol, session_date=session_date)
        print(
            "[FLOAT_AUDIT] "
            f"symbol={record.symbol} raw={record.raw} formatted={record.formatted} "
            f"source={record.source} fetched_at={record.fetched_at} cache_hit={record.cache_hit}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
