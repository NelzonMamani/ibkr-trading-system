from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, List, Optional


@dataclass(frozen=True)
class FastViewRow:
    symbol: str
    session: str
    last_price: Optional[float]
    pct_change: Optional[float]
    volume: Optional[int]
    dollar_volume: Optional[float]
    bid: Optional[float]
    ask: Optional[float]
    spread: Optional[float]
    spread_pct: Optional[float]
    rvol: Optional[float]
    float_shares: Optional[int]
    scanner_rank: int
    scanner_score: Optional[float]
    drop_reason: Optional[str]
    data_quality_flags: List[str]
    news_present: bool
    catalyst_type: Optional[str]
    dilution_flag: bool
    news_age_minutes: Optional[int]
    velocity_5m: Optional[int]
    velocity_10m: Optional[int]
    velocity_30m: Optional[int]
    attention_tier: Optional[str]
    gam_ea_eligible: Optional[bool]


@dataclass(frozen=True)
class DeepViewRow:
    symbol: str
    focus_rank: int
    links: List[str]
    catalyst_rationale: str
    focus_reason: str


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fmt_float(value: Optional[float], digits: int = 2) -> str:
    if value is None:
        return "N/A"
    return f"{value:.{digits}f}"


def _fmt_int(value: Optional[int]) -> str:
    if value is None:
        return "N/A"
    return str(value)


def format_fast_view_lines(rows: Iterable[FastViewRow]) -> List[str]:
    lines: List[str] = []
    for row in rows:
        flags = row.data_quality_flags or []
        flags_s = ",".join(flags) if flags else "none"
        lines.append(
            " ".join(
                [
                    f"rank={row.scanner_rank:02d}",
                    f"symbol={row.symbol}",
                    f"session={row.session}",
                    f"last={_fmt_float(row.last_price)}",
                    f"pct_change={_fmt_float(row.pct_change, 1)}",
                    f"volume={_fmt_int(row.volume)}",
                    f"dollar_vol={_fmt_float(row.dollar_volume)}",
                    f"bid={_fmt_float(row.bid)}",
                    f"ask={_fmt_float(row.ask)}",
                    f"spread={_fmt_float(row.spread, 4)}",
                    f"spread_pct={_fmt_float(row.spread_pct, 4)}",
                    f"rvol={_fmt_float(row.rvol, 2)}",
                    f"float={_fmt_int(row.float_shares)}",
                    f"score={_fmt_float(row.scanner_score, 2)}",
                    f"news_present={str(row.news_present).lower()}",
                    f"catalyst={row.catalyst_type or 'N/A'}",
                    f"dilution={str(row.dilution_flag).lower()}",
                    f"news_age_min={_fmt_int(row.news_age_minutes)}",
                    f"vel5={_fmt_int(row.velocity_5m)}",
                    f"vel10={_fmt_int(row.velocity_10m)}",
                    f"vel30={_fmt_int(row.velocity_30m)}",
                    f"attention={row.attention_tier or 'N/A'}",
                    f"gam_ea_eligible={str(row.gam_ea_eligible).lower()}",
                    f"flags={flags_s}",
                ]
            )
        )
    return lines


def print_fast_view(rows: Iterable[FastViewRow]) -> None:
    rows_list = list(rows)
    print("\n" + "=" * 90)
    print(f"[SCANNER][FAST_VIEW] Watchlist ({len(rows_list)}) — {_utc_now_iso()}")
    print("=" * 90)
    for line in format_fast_view_lines(rows_list):
        print(line)
    print("=" * 90)


def print_deep_view(rows: Iterable[DeepViewRow]) -> None:
    rows_list = list(rows)
    print("\n" + "=" * 90)
    print(f"[SCANNER][DEEP_VIEW] Focus ({len(rows_list)}) — {_utc_now_iso()}")
    print("=" * 90)
    for row in rows_list:
        print(f"[FOCUS {row.focus_rank:02d}] {row.symbol}")
        if row.links:
            print("  Links:")
            for link in row.links:
                print(f"   - {link}")
        else:
            print("  Links: N/A")
        print(f"  Catalyst: {row.catalyst_rationale}")
        print(f"  Focus reason: {row.focus_reason}")
        print("-" * 90)
