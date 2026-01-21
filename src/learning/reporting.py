from __future__ import annotations

from datetime import datetime
from typing import Any

from src.learning.models import LearningDataset, LearningTrade
from src.utils.time_utils import to_ny_time


def _trade_pnl_pct(trade: LearningTrade) -> float | None:
    if trade.entry_price in {None, 0} or trade.exit_price is None:
        return None
    return round(((trade.exit_price - trade.entry_price) / trade.entry_price) * 100.0, 2)


def _win_loss_counts(trades: list[LearningTrade]) -> dict[str, int]:
    wins = sum(1 for trade in trades if (trade.pnl or 0.0) > 0)
    losses = sum(1 for trade in trades if (trade.pnl or 0.0) < 0)
    flats = sum(1 for trade in trades if (trade.pnl or 0.0) == 0)
    return {"wins": wins, "losses": losses, "flats": flats}


def build_daily_report(
    *,
    asof_date: str,
    strategy_name: str,
    dataset: LearningDataset,
    watchlists: list[dict[str, Any]],
    trade_reviews: list[dict[str, Any]],
    report_type: str = "DAILY",
) -> dict[str, Any]:
    trades = dataset.trades
    counts = _win_loss_counts(trades)
    total = len(trades)
    win_rate = round((counts["wins"] / total) * 100.0, 2) if total else 0.0
    gross_pnl = round(sum((trade.pnl or 0.0) for trade in trades), 2)
    avg_pnl = round(gross_pnl / total, 2) if total else 0.0
    report = {
        "asof_date_ny": asof_date,
        "strategy_name": strategy_name,
        "report_type": report_type,
        "executive_summary": {
            "trades_opened": total,
            "trades_closed": total,
            "wins": counts["wins"],
            "losses": counts["losses"],
            "flats": counts["flats"],
            "win_rate": win_rate,
            "gross_pnl": gross_pnl,
            "net_pnl": gross_pnl,
            "average_pnl": avg_pnl,
        },
        "rule_adherence": {
            "stop_loss_violations": 0,
            "near_violations": 0,
            "daily_max_loss_breaches": 0,
            "circuit_breaker_triggers": 0,
            "execution_blocks": 0,
        },
        "setup_performance": {
            "by_pattern": {},
            "by_session_phase": {},
        },
        "missed_trades": {
            "top_reasons": [],
        },
        "watchlist_quality": {
            "watchlists_generated": len(watchlists),
            "focus_trade_count": 0,
        },
        "trade_reviews": trade_reviews,
        "action_items": {
            "improve": [],
            "keep": [],
        },
    }
    return report


def build_summary_text(report: dict[str, Any]) -> str:
    summary = report.get("executive_summary", {})
    return (
        "Trades={trades} WinRate={win_rate}% GrossPnL={pnl}".format(
            trades=summary.get("trades_closed", 0),
            win_rate=summary.get("win_rate", 0.0),
            pnl=summary.get("gross_pnl", 0.0),
        )
    )


def build_trade_reviews(trades: list[LearningTrade]) -> list[dict[str, Any]]:
    reviews: list[dict[str, Any]] = []
    for trade in trades:
        pnl = trade.pnl or 0.0
        grade = "A" if pnl > 0 else "C" if pnl == 0 else "D"
        reviews.append(
            {
                "symbol": trade.symbol,
                "grade": grade,
                "what_went_well": ["Positive follow-through"] if pnl > 0 else [],
                "what_went_wrong": ["Trade did not follow through"] if pnl < 0 else [],
                "rule_checks": {"followed_plan": "PASS" if pnl >= 0 else "FAIL"},
                "next_time": ["Reduce risk on weak follow-through"] if pnl < 0 else [],
                "evidence": [],
            }
        )
    return reviews


def trade_from_row(row: dict[str, Any]) -> LearningTrade:
    entry_price = row.get("entry_price")
    exit_price = row.get("exit_price")
    pnl = row.get("net_realised_pnl", row.get("gross_realised_pnl"))
    if pnl is None and entry_price is not None and exit_price is not None:
        pnl = round(float(exit_price) - float(entry_price), 2)
    return LearningTrade(
        strategy_name=row.get("strategy_name") or "UNKNOWN",
        symbol=row.get("symbol") or "UNKNOWN",
        entry_time=_parse_time(row.get("opened_at")),
        exit_time=_parse_time(row.get("closed_at")),
        entry_price=_safe_float(entry_price),
        exit_price=_safe_float(exit_price),
        pnl=_safe_float(pnl),
        pnl_pct=_trade_pnl_pct(
            LearningTrade(
                strategy_name=row.get("strategy_name") or "UNKNOWN",
                symbol=row.get("symbol") or "UNKNOWN",
                entry_time=None,
                exit_time=None,
                entry_price=_safe_float(entry_price),
                exit_price=_safe_float(exit_price),
                pnl=_safe_float(pnl),
                pnl_pct=None,
            )
        ),
        tags=[],
        gate_context={},
    )


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def filter_trades_for_date(trades: list[LearningTrade], asof_date: str) -> list[LearningTrade]:
    filtered: list[LearningTrade] = []
    for trade in trades:
        exit_time = trade.exit_time or trade.entry_time
        if exit_time is None:
            continue
        ny_date = to_ny_time(exit_time).date().isoformat()
        if ny_date == asof_date:
            filtered.append(trade)
    return filtered


def filter_trades_for_range(
    trades: list[LearningTrade],
    start_date: str,
    end_date: str,
) -> list[LearningTrade]:
    filtered: list[LearningTrade] = []
    for trade in trades:
        exit_time = trade.exit_time or trade.entry_time
        if exit_time is None:
            continue
        ny_date = to_ny_time(exit_time).date().isoformat()
        if start_date <= ny_date <= end_date:
            filtered.append(trade)
    return filtered
