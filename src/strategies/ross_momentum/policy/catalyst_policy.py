"""Ross catalyst policy status semantics."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from src.strategies.ross_momentum.strategy_policy import StockSelectionSpec

from .runtime_safety import normalize_run_mode, validation_override_allowed


class CatalystStatus(str, Enum):
    CONFIRMED = "CONFIRMED"
    ABSENT = "ABSENT"
    UNKNOWN = "UNKNOWN"
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
    DISABLED_FOR_VALIDATION = "DISABLED_FOR_VALIDATION"


@dataclass(frozen=True)
class CatalystDecision:
    status: CatalystStatus
    satisfied: bool
    reason: str


@dataclass(frozen=True)
class CatalystPolicy:
    require_catalyst: bool
    statuses: tuple[CatalystStatus, ...] = tuple(CatalystStatus)

    @classmethod
    def from_stock_selection(cls, stock_selection: StockSelectionSpec) -> "CatalystPolicy":
        return cls(require_catalyst=bool(stock_selection.require_catalyst))


def assess_catalyst(
    *,
    mode: Any,
    news_enabled: bool,
    news_available: bool,
    confirmed: bool | None,
    validation_bypass_requested: bool = False,
) -> CatalystDecision:
    if confirmed is True:
        return CatalystDecision(CatalystStatus.CONFIRMED, True, "confirmed")
    if confirmed is False and news_available:
        return CatalystDecision(CatalystStatus.ABSENT, False, "absent")
    if validation_override_allowed(mode, validation_bypass_requested):
        return CatalystDecision(
            CatalystStatus.DISABLED_FOR_VALIDATION,
            True,
            "explicit_validation_bypass",
        )
    if not news_enabled:
        return CatalystDecision(CatalystStatus.DATA_UNAVAILABLE, False, "news_disabled")
    if not news_available:
        return CatalystDecision(CatalystStatus.DATA_UNAVAILABLE, False, "news_unavailable")
    return CatalystDecision(CatalystStatus.UNKNOWN, False, "news_unknown")


def log_catalyst_unavailable(symbol: Any, reason: str = "news_unavailable") -> None:
    print(
        "[ROSS][CATALYST][UNKNOWN] "
        f"symbol={str(symbol or 'UNKNOWN').upper()} reason={reason}"
    )


def log_catalyst_validation_bypass(mode: Any, reason: str) -> None:
    print(
        "[ROSS][CATALYST][VALIDATION_BYPASS] "
        f"mode={normalize_run_mode(mode)} reason={reason}"
    )


def log_catalyst_live_not_satisfied(symbol: Any, reason: str) -> None:
    print(
        "[ROSS][CATALYST][LIVE_NOT_SATISFIED] "
        f"symbol={str(symbol or 'UNKNOWN').upper()} reason={reason}"
    )
