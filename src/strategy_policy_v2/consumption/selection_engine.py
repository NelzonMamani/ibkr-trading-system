from __future__ import annotations

from src.scanner.session_pct_change import normalize_session_label
from src.strategy_policy_v2.policy_v2 import StrategyPolicyV2
from src.strategy_policy_v2.consumption.models import Candidate, DroppedCandidate, SelectionResult


_REQUIRED_FIELDS = (
    "symbol",
    "session_label",
    "last_price",
    "pct_change",
    "volume",
    "rvol",
    "dollar_volume",
    "float_millions",
)


class SelectionEngineV2:
    def evaluate(self, policy: StrategyPolicyV2, candidates: list[Candidate]) -> SelectionResult:
        allowlist = {
            normalize_session_label(session).upper()
            for session in getattr(policy.selection_plan, "session_allowlist", ())
        }

        eligible: list[Candidate] = []
        dropped: list[DroppedCandidate] = []
        for candidate in candidates:
            reasons: list[str] = []
            for field in _REQUIRED_FIELDS:
                if candidate.get(field) is None:
                    reasons.append(f"DATA_MISSING:{field}")

            if reasons:
                dropped.append(DroppedCandidate(candidate=candidate, reasons=sorted(set(reasons))))
                continue

            session = normalize_session_label(str(candidate.get("session_label") or "")).upper()
            if allowlist and session not in allowlist:
                reasons.append("SESSION_NOT_ALLOWED")

            price = float(candidate.get("last_price") or 0.0)
            price_model = policy.stock_selection_law.price_model
            if price < float(price_model.min_price) or price > float(price_model.max_price):
                reasons.append("PRICE_OUT_OF_RANGE")

            gap_pct = float(candidate.get("pct_change") or 0.0)
            if gap_pct < float(policy.stock_selection_law.gap_model.hard_gap_threshold):
                reasons.append("GAP_TOO_SMALL")

            volume = int(candidate.get("volume") or 0)
            if volume < int(policy.stock_selection_law.volume_model.min_total_volume):
                reasons.append("VOLUME_TOO_LOW")

            pre_volume = int(candidate.get("premarket_volume") or 0)
            if pre_volume < int(policy.stock_selection_law.volume_model.min_premarket_volume):
                reasons.append("PREMARKET_VOLUME_TOO_LOW")

            rvol = float(candidate.get("rvol") or 0.0)
            if rvol < float(policy.stock_selection_law.relative_volume_model.rvol_minimum):
                reasons.append("RVOL_TOO_LOW")

            float_m = float(candidate.get("float_millions") or 0.0)
            if float_m > float(policy.stock_selection_law.float_model.float_max_millions):
                reasons.append("FLOAT_TOO_HIGH")

            if float(candidate.get("dollar_volume") or 0.0) < float(policy.stock_selection_law.volume_model.dollar_volume_min):
                reasons.append("DOLLAR_VOLUME_TOO_LOW")

            catalyst = candidate.get("news_catalyst")
            if policy.stock_selection_law.catalyst_model.require_catalyst and not catalyst:
                reasons.append("NO_CATALYST")

            spread_pct = float(candidate.get("spread_pct") or 0.0)
            spread_limit = float(policy.liquidity_sanity_model.spread_max_pct or 0.0)
            if spread_limit > 0 and spread_pct > spread_limit:
                reasons.append("SPREAD_TOO_WIDE")

            if bool(candidate.get("halted")) and "allow" not in policy.liquidity_sanity_model.halt_policy.lower():
                reasons.append("HALTED_DISALLOWED")

            if reasons:
                dropped.append(DroppedCandidate(candidate=candidate, reasons=sorted(set(reasons))))
            else:
                eligible.append(candidate)

        metrics = {
            "total": len(candidates),
            "eligible": len(eligible),
            "dropped": len(dropped),
            "drop_reason_counts": {
                reason: sum(1 for row in dropped if reason in row.reasons)
                for reason in sorted({r for row in dropped for r in row.reasons})
            },
        }
        return SelectionResult(eligible=eligible, dropped=dropped, metrics=metrics)
