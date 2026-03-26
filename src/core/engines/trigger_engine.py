from __future__ import annotations

from typing import Any

from src.domain.market_snapshot import MarketSnapshot


class TriggerEngine:
    """Derive explicit, executable trigger readiness from a DecisionEngine artifact."""

    _MAX_SPREAD_RATIO = 0.03
    _MAX_PRICE_DISTANCE_RATIO = 0.05
    _BLOCKING_TOKENS = ("NON_ENTRY", "SESSION_INCOMPATIBLE")
    _SESSION_ALLOWLIST_BY_PATTERN: dict[str, set[str]] = {
        "P_ORB": {"REGULAR"},
        "P_OPENING_DRIVE": {"REGULAR"},
        "P_FAILED_ORB_FAKEOUT": {"REGULAR"},
    }

    def compute_trigger(
        self,
        symbol: str,
        decision: dict,
        market_snapshot: MarketSnapshot,
        session_context: str,
    ) -> dict:
        blocking_factors: list[str] = []
        normalized_symbol = str(symbol or "").upper()
        decision_payload = decision or {}
        decision_state = str(decision_payload.get("decision_state") or "").upper()

        if decision_state != "CANDIDATE_SELECTED":
            blocking_factors.append("decision_not_candidate_selected")

        trigger_level = self._safe_float(decision_payload.get("trigger_level"))
        invalidation_level = self._safe_float(decision_payload.get("invalidation_level"))
        entry_bias = str(decision_payload.get("entry_bias") or "LONG").upper()

        if trigger_level is None:
            blocking_factors.append("missing_trigger_level")
        if invalidation_level is None:
            blocking_factors.append("missing_invalidation_level")

        bid = self._safe_float(getattr(market_snapshot, "bid", None)) if market_snapshot else None
        ask = self._safe_float(getattr(market_snapshot, "ask", None)) if market_snapshot else None
        last = self._safe_float(getattr(market_snapshot, "last", None)) if market_snapshot else None
        if bid is None or ask is None:
            blocking_factors.append("missing_bid_ask")
        elif ask < bid:
            blocking_factors.append("crossed_market_snapshot")
        elif bid > 0:
            spread_ratio = (ask - bid) / bid
            if spread_ratio > self._MAX_SPREAD_RATIO:
                blocking_factors.append(f"spread_too_wide({spread_ratio:.4f})")

        if trigger_level is not None:
            anchor_price = last if last is not None else ask if entry_bias != "SHORT" else bid
            if anchor_price is None:
                blocking_factors.append("missing_anchor_price")
            elif trigger_level > 0:
                distance_ratio = abs(anchor_price - trigger_level) / trigger_level
                if distance_ratio > self._MAX_PRICE_DISTANCE_RATIO:
                    blocking_factors.append(f"price_too_far_from_trigger({distance_ratio:.4f})")

        if self._decision_contains_blocking_signal(decision_payload):
            blocking_factors.append("decision_explicitly_blocked")
        if not self._session_is_valid(
            session_context=session_context,
            pattern_id=str(decision_payload.get("selected_pattern_id") or ""),
        ):
            blocking_factors.append("invalid_session_for_pattern")

        entry_price = None
        if trigger_level is not None and bid is not None and ask is not None:
            if entry_bias == "SHORT":
                entry_price = min(trigger_level, bid)
            else:
                entry_price = max(trigger_level, ask)

        trigger_id = f"{normalized_symbol}:{decision_payload.get('selected_pattern_id') or 'UNKNOWN'}:TRIGGER"
        trigger_state = "TRIGGER_BLOCKED" if blocking_factors else "TRIGGER_READY"
        reason = "trigger_ready" if trigger_state == "TRIGGER_READY" else blocking_factors[0]
        output = {
            "symbol": normalized_symbol or str(symbol),
            "trigger_state": trigger_state,
            "trigger_id": trigger_id,
            "entry_price": entry_price,
            "stop_loss_price": invalidation_level,
            "invalidation_level": invalidation_level,
            "quantity_hint": 1,
            "reason": reason,
            "blocking_factors": blocking_factors,
        }
        print(
            "[TRIGGER_ENGINE] "
            f"symbol={normalized_symbol} state={trigger_state} reason={reason} "
            f"entry={entry_price} stop={invalidation_level} blockers={blocking_factors}"
        )
        return output

    def _session_is_valid(self, *, session_context: str | None, pattern_id: str) -> bool:
        normalized_pattern = str(pattern_id or "").upper()
        allowed_sessions = self._SESSION_ALLOWLIST_BY_PATTERN.get(normalized_pattern)
        if not allowed_sessions:
            return True
        normalized_session = str(session_context or "").upper()
        if normalized_session in {"RTH", "RTH_OPEN", "RTH_MID", "RTH_LATE", "REG"}:
            normalized_session = "REGULAR"
        return normalized_session in allowed_sessions

    def _decision_contains_blocking_signal(self, decision: dict[str, Any]) -> bool:
        fields: list[Any] = [
            decision.get("decision_reason"),
            *(decision.get("supporting_factors") or []),
        ]
        for item in fields:
            text = str(item or "").upper()
            if any(token in text for token in self._BLOCKING_TOKENS):
                return True
        for candidate in decision.get("rejected_candidates") or []:
            reason = str((candidate or {}).get("reason") or "").upper()
            if "NON_ENTRY" in reason:
                return True
        return False

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        try:
            return None if value is None else float(value)
        except (TypeError, ValueError):
            return None
