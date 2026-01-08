from __future__ import annotations

import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

from scanner.core.entry_builder import build_entry  # noqa: E402
from scanner.core.filters import passes_catalyst_eligibility, passes_ross_5_pillars  # noqa: E402
from scanner.core.printer import print_master, print_watchlist  # noqa: E402
from scanner.engines.float_engine import load_float_cache, save_float_cache  # noqa: E402
from scanner.ib.ib_connect import fetch_top_gainers, ib_connect  # noqa: E402
from scanner.news.news_engine import NewsEngine  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    ib = ib_connect()
    float_cache = load_float_cache()
    news_engine = NewsEngine()

    contracts = fetch_top_gainers(ib, n=50)
    entries = []

    for contract in contracts:
        try:
            entry = build_entry(ib, contract, news_engine, float_cache)
            entries.append(entry)
        except Exception as exc:
            logger.warning("Failed to build entry for %s: %s", contract.symbol, exc)

    gap_sorted = sorted(
        entries,
        key=lambda item: item.get("overnight_gap_percentage") or 0,
        reverse=True,
    )
    for idx, entry in enumerate(gap_sorted, start=1):
        entry["sort_rank_by_gap_desc"] = idx

    print_master(entries)

    filtered = [
        entry
        for entry in entries
        if passes_ross_5_pillars(entry) and passes_catalyst_eligibility(entry)
    ]

    filtered = sorted(
        filtered,
        key=lambda item: item.get("current_percentage_change_from_prior_close") or 0,
        reverse=True,
    )[:15]

    print_watchlist(filtered)
    save_float_cache(float_cache)

    try:
        ib.disconnect()
    except Exception:
        pass


if __name__ == "__main__":
    main()
