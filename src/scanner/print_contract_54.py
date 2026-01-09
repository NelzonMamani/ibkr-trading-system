from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Iterable, List

from .contracts import ALLOWED_NA, CANONICAL_FIELDS, ScannerRow54, validate_row


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _format_value(value) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, (list, dict)):
        return json.dumps(value, sort_keys=True, ensure_ascii=False)
    return str(value)


def print_master(rows: Iterable[ScannerRow54]) -> None:
    rows_list = list(rows)
    print("\n" + "=" * 90)
    print("MASTER SCANNER PRINTER —", _utc_now_iso())
    print("=" * 90)
    for idx, row in enumerate(rows_list, start=1):
        missing_fields, non_allowed_na_fields, _, integrity = validate_row(row)
        print(f"[ROW {idx:02d}] {row.symbol or 'UNKNOWN'} | integrity={integrity:.2f}%")
        if missing_fields:
            print(f"[WARN] Missing canonical fields: {missing_fields}")
        if non_allowed_na_fields:
            print(f"[WARN] Non-allowed N/A fields: {non_allowed_na_fields}")
        for field_idx, field_name in enumerate(CANONICAL_FIELDS, start=1):
            value = getattr(row, field_name, None)
            if value is None and ALLOWED_NA.get(field_name, True):
                value = "N/A"
            print(f"  {field_idx:02d}. {field_name}: {_format_value(value)}")
        print("-" * 90)


def print_watchlist_compact(rows: Iterable[ScannerRow54]) -> None:
    rows_list = list(rows)
    print("\n" + "=" * 90)
    print(f"[SCANNER] FILTERED WATCHLIST ({len(rows_list)}) — {_utc_now_iso()}")
    print("=" * 90)
    for row in rows_list:
        fire = row.momentum_fire_indicator or ""
        pct = row.current_percentage_change_from_prior_close
        gap = row.overnight_gap_percentage
        flt = row.float_shares_formatted
        rvol = row.relative_volume
        news_total = row.news_total_headlines
        score = row.composite_momentum_score
        pct_s = "N/A" if pct is None else f"{pct:.1f}"
        gap_s = "N/A" if gap is None else f"{gap:.1f}"
        rvol_s = "N/A" if rvol is None else f"{rvol:.2f}"
        flt_s = flt if flt is not None else "N/A"
        news_s = "N/A" if news_total is None else str(news_total)
        score_s = "N/A" if score is None else f"{score:.1f}"
        print(
            f"{fire} {row.symbol or 'UNKNOWN'} pct_change={pct_s} gap={gap_s} "
            f"rvol={rvol_s} float={flt_s} news={news_s} score={score_s}"
        )
    print("=" * 90)


def format_watchlist_lines(rows: Iterable[ScannerRow54]) -> List[str]:
    lines = []
    for row in rows:
        fire = row.momentum_fire_indicator or ""
        pct = row.current_percentage_change_from_prior_close
        gap = row.overnight_gap_percentage
        flt = row.float_shares_formatted
        rvol = row.relative_volume
        news_total = row.news_total_headlines
        score = row.composite_momentum_score
        pct_s = "N/A" if pct is None else f"{pct:.1f}"
        gap_s = "N/A" if gap is None else f"{gap:.1f}"
        rvol_s = "N/A" if rvol is None else f"{rvol:.2f}"
        flt_s = flt if flt is not None else "N/A"
        news_s = "N/A" if news_total is None else str(news_total)
        score_s = "N/A" if score is None else f"{score:.1f}"
        lines.append(
            f"{fire} {row.symbol or 'UNKNOWN'} pct_change={pct_s} gap={gap_s} "
            f"rvol={rvol_s} float={flt_s} news={news_s} score={score_s}"
        )
    return lines
