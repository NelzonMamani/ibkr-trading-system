from __future__ import annotations

from typing import Any, Dict, List

from src.models.data_models import ScannerCandidate
from src.scanner.contracts import ScannerRow54


def build_scanner_candidates(
    rows: List[ScannerRow54],
    row_validations: Dict[str, Any],
) -> List[ScannerCandidate]:
    candidates: List[ScannerCandidate] = []
    for row in rows:
        validation = row_validations.get(row.symbol or "", {})
        missing_fields = validation.get("missing_fields") or []
        non_allowed = validation.get("non_allowed_na_fields") or []
        flags: List[str] = []
        if non_allowed:
            flags.append("MISSING_REQUIRED_FIELDS")
        if row.volume_data_quality_flag:
            flags.append(str(row.volume_data_quality_flag))
        if row.price_data_type_label == "ERROR":
            flags.append("PRICE_DATA_ERROR")
        if row.price_truth_source_label == "ERROR":
            flags.append("PRICE_TRUTH_ERROR")

        float_millions = (
            round(row.float_shares_raw / 1_000_000.0, 2)
            if row.float_shares_raw is not None
            else None
        )
        rationale_parts = ["scanner_contract_row"]
        if non_allowed:
            rationale_parts.append(f"missing_required={len(non_allowed)}")
        if missing_fields:
            rationale_parts.append(f"missing_fields={len(missing_fields)}")
        rationale = " | ".join(rationale_parts)

        candidates.append(
            ScannerCandidate(
                symbol=row.symbol or "UNKNOWN",
                price=row.last_trade_price,
                gap_percent=row.overnight_gap_percentage,
                rvol=row.relative_volume,
                float_millions=float_millions,
                rationale=rationale,
                session=row.market_session_label,
                bid=row.bid_price,
                ask=row.ask_price,
                spread=row.bid_ask_spread,
                volume=row.current_intraday_volume,
                vwap=row.vwap_price,
                data_quality_flags=flags,
            )
        )
    return candidates
