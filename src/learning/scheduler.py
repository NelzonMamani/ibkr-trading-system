from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

from src.learning.models import LearningDataset
from src.learning.reporting import (
    build_daily_report,
    build_summary_text,
    build_trade_reviews,
    filter_trades_for_date,
    trade_from_row,
)
from src.learning.storage import LearningStorage, compute_hash
from src.utils.time_utils import to_ny_time


class LearningScheduler:
    def __init__(self, strategy_name: str = "ROSS_MOMENTUM") -> None:
        self.strategy_name = strategy_name

    def on_startup(self) -> None:
        now = datetime.now(timezone.utc)
        asof_date = _last_completed_trading_day(now)
        if not asof_date:
            return
        self._ensure_daily_report(asof_date)

    def on_shutdown(self) -> None:
        today = to_ny_time(datetime.now(timezone.utc)).date().isoformat()
        self._ensure_daily_report(today)

    def _ensure_daily_report(self, asof_date: str) -> None:
        storage = LearningStorage()
        reports = storage.list_reports(strategy_name=self.strategy_name, limit=1)
        if reports and reports[0].get("asof_date_ny") == asof_date:
            storage.close()
            return
        trades_raw = storage.fetch_trade_outcomes(strategy_name=self.strategy_name)
        trades = [trade_from_row(row) for row in trades_raw]
        trades = filter_trades_for_date(trades, asof_date)
        if not trades:
            storage.close()
            return
        dataset = LearningDataset(trades=trades)
        reviews = build_trade_reviews(trades)
        watchlists = storage.fetch_watchlists(strategy_name=self.strategy_name)
        report = build_daily_report(
            asof_date=asof_date,
            strategy_name=self.strategy_name,
            dataset=dataset,
            watchlists=watchlists,
            trade_reviews=reviews,
        )
        storage.insert_learning_report(
            run_id=compute_hash({"strategy": self.strategy_name, "date": asof_date}),
            report_type="DAILY",
            asof_date_ny=asof_date,
            strategy_name=self.strategy_name,
            payload=report,
            summary_text=build_summary_text(report),
        )
        storage.close()


def _last_completed_trading_day(now_utc: datetime) -> str | None:
    ny_time = to_ny_time(now_utc)
    if ny_time.weekday() >= 5:
        ny_time = ny_time - timedelta(days=ny_time.weekday() - 4)
    if ny_time.time() >= time(16, 0) and ny_time.weekday() < 5:
        return ny_time.date().isoformat()
    day = ny_time.date() - timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day.isoformat()
