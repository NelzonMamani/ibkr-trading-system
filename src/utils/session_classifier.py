"""Session classification utilities for market-aware baselines."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.config.config_resolver import get_config
from src.config.system_config import get_current_market_session
from src.strategies.ross_momentum.strategy_policy import RossTradingMode
from src.utils.time_utils import to_ny_time, to_uk_time


@dataclass(frozen=True)
class SessionClassification:
    now_utc: datetime
    now_ny: datetime
    now_uk: datetime
    session_state: str
    ross_trading_mode: RossTradingMode


class SessionClassifier:
    def classify(self, now_utc: datetime) -> SessionClassification:
        now_ny = to_ny_time(now_utc)
        now_uk = to_uk_time(now_utc)
        ny_date = now_ny.date()

        holidays = set(get_config("MARKET_HOLIDAYS"))
        if now_ny.weekday() >= 5:
            state = "WEEKEND"
        elif ny_date in holidays:
            state = "HOLIDAY"
        else:
            session = get_current_market_session(now_utc)
            if session == "PRE":
                state = "PRE"
            elif session == "REGULAR":
                state = "RTH"
            elif session == "AFTER":
                state = "AH"
            else:
                state = "CLOSED"

        if state in {"PRE", "RTH"}:
            ross_mode = RossTradingMode.OPENING_DRIVE
        elif state == "AH":
            ross_mode = RossTradingMode.LATE_DAY
        else:
            ross_mode = RossTradingMode.MIDDAY

        return SessionClassification(
            now_utc=now_utc,
            now_ny=now_ny,
            now_uk=now_uk,
            session_state=state,
            ross_trading_mode=ross_mode,
        )
