from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.models.data_models import ScannerCandidate
from src.scanner.contracts import ScannerRow54


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _parse_float_millions(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    text = value.strip().upper()
    try:
        if text.endswith("B"):
            return float(text[:-1]) * 1_000.0
        if text.endswith("M"):
            return float(text[:-1])
        if text.endswith("K"):
            return float(text[:-1]) / 1_000.0
        return float(text) / 1_000_000.0
    except Exception:
        return None


def _float_shares_to_millions(row: ScannerRow54) -> Optional[float]:
    if row.float_shares_raw is not None:
        return _safe_float(row.float_shares_raw) / 1_000_000.0
    return _parse_float_millions(row.float_shares_formatted)


def build_scanner_candidates(
    scanner_rows: List[ScannerRow54],
    row_validations: Dict[str, Any],
) -> List[ScannerCandidate]:
    candidates: List[ScannerCandidate] = []
    for idx, row in enumerate(scanner_rows, start=1):
        row_key = row.symbol or f"row_{idx}"
        validation = row_validations.get(row_key, {}) if row_validations else {}
        missing_fields = validation.get("missing_fields") or []
        non_allowed = validation.get("non_allowed_na_fields") or []
        data_quality_flags: List[str] = []
        if row.volume_data_quality_flag:
            data_quality_flags.append(str(row.volume_data_quality_flag))
        if non_allowed:
            data_quality_flags.append("ROW_VALIDATION_NON_ALLOWED_NA_FIELDS")
        if missing_fields:
            data_quality_flags.append("ROW_VALIDATION_MISSING_FIELDS")

        rationale = "ScannerRow54 candidate derived from scanner artifact."
        if missing_fields or non_allowed:
            rationale = (
                f"{rationale} missing_fields={len(missing_fields)} "
                f"non_allowed_na_fields={len(non_allowed)}"
            )

        price = (
            row.last_trade_price
            if row.last_trade_price is not None
            else row.mid_price
            if row.mid_price is not None
            else row.session_open_price
            if row.session_open_price is not None
            else row.previous_close_price
        )

        candidates.append(
            ScannerCandidate(
                symbol=row.symbol or "UNKNOWN",
                price=_safe_float(price),
                gap_percent=_safe_float(row.overnight_gap_percentage),
                rvol=_safe_float(row.relative_volume),
                float_millions=_safe_float(_float_shares_to_millions(row)),
                rationale=rationale,
                session=row.market_session_label,
                vwap=_safe_float(row.vwap_price),
                hod=_safe_float(row.day_high_price),
                bid=_safe_float(row.bid_price),
                ask=_safe_float(row.ask_price),
                spread=_safe_float(row.bid_ask_spread),
                volume=_safe_float(row.current_intraday_volume),
                data_quality_flags=data_quality_flags,
            )
        )
    return candidates
