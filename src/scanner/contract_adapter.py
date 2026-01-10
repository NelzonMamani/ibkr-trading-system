from __future__ import annotations

from typing import Any, Dict, List

from src.models.data_models import ScannerCandidate
from src.scanner.contracts import ScannerRow54


def _build_rationale(row: ScannerRow54) -> str:
    if row.debug_notes:
        return row.debug_notes
    return "Scanner candidate derived from canonical 54-field contract."


def _float_millions(float_raw: int | None) -> float | None:
    if float_raw is None:
        return None
    return round(float_raw / 1_000_000, 3)


def build_scanner_candidates(
    scanner_rows: List[ScannerRow54],
    row_validations: Dict[str, Dict[str, Any]] | None,
) -> List[ScannerCandidate]:
    validations = row_validations or {}
    candidates: List[ScannerCandidate] = []
    for idx, row in enumerate(scanner_rows, start=1):
        symbol_key = row.symbol or f"row_{idx}"
        validation = validations.get(symbol_key, {})
        data_quality_flags = list(validation.get("non_allowed_na_fields") or [])
        candidates.append(
            ScannerCandidate(
                symbol=row.symbol or "UNKNOWN",
                price=row.last_trade_price or row.session_open_price or row.previous_close_price,
                gap_percent=row.overnight_gap_percentage,
                rvol=row.relative_volume,
                float_millions=_float_millions(row.float_shares_raw),
                rationale=_build_rationale(row),
                session=row.market_session_label,
                vwap=row.vwap_price,
                bid=row.bid_price,
                ask=row.ask_price,
                spread=row.bid_ask_spread,
                volume=row.current_intraday_volume,
                data_quality_flags=data_quality_flags,
            )
        )
    return candidates
