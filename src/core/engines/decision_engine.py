from __future__ import annotations

from typing import Any


class DecisionEngine:
    """Deterministic candidate arbitration for setup/pattern decisions."""

    _COMPATIBILITY_MATRIX: dict[str, set[str]] = {
        "ORB": {"P_ORB", "P_OPENING_DRIVE", "P_FAILED_ORB_FAKEOUT"},
        "OPENING_DRIVE": {"P_OPENING_DRIVE", "P_ORB"},
        "PREMARKET_HIGH_BREAK": {"P_PREMKT_BREAK", "P_HOD_BREAK"},
        "HOD_BREAK": {"P_HOD_BREAK", "P_PREMKT_BREAK", "P_RANGE_BREAKOUT"},
        "EMA_PULLBACK": {"P_EMA_PULLBACK", "P_FIRST_PULLBACK", "P_MICRO_PULLBACK", "P_SECOND_PULLBACK"},
        "VWAP_RECLAIM": {"P_VWAP_PULLBACK", "P_MOMENTUM_RECLAIM", "P_FIRST_PULLBACK", "P_MICRO_PULLBACK"},
        "RANGE_BREAK": {"P_RANGE_BREAKOUT", "P_ASCENDING_TRIANGLE_BREAKOUT", "P_PENNANT_BREAK"},
    }

    _NON_ENTRY_MARKERS: tuple[str, ...] = ("AVOID", "CAUTION", "EXIT", "STOP", "RISK_OFF")

    _SCORE_DETECTED = 2.0
    _SCORE_SETUP_COMPATIBLE = 2.5
    _SCORE_STRUCTURE_COMPATIBLE = 1.0
    _SCORE_ACTIONABLE = 1.0
    _SCORE_HAS_INVALIDATION = 0.5
    _PENALTY_MISSING_ACTIONABILITY = 1.75
    _PENALTY_SESSION_INCOMPATIBLE = 1.5
    _PENALTY_NON_ENTRY = 4.0

    def compute_decision(
        self,
        *,
        symbol: str,
        levels: dict,
        structure: dict,
        setups: list[dict],
        pattern_results: list[Any],
        session_context: str | None = None,
        pattern_traces: list[Any] | None = None,
        inactive_pattern_ids: set[str] | None = None,
    ) -> dict:
        normalized_setup_families = {
            str(item.get("setup_family") or "").upper() for item in (setups or []) if isinstance(item, dict)
        }
        trace_by_pattern_id = {
            str(getattr(trace, "pattern_id", "") or "").upper(): trace for trace in (pattern_traces or [])
        }
        normalized_candidates = [
            self._normalize_candidate(item, trace_by_pattern_id=trace_by_pattern_id)
            for item in (pattern_results or [])
        ]

        scored_candidates: list[dict] = []
        rejected_candidates: list[dict] = []

        for candidate in normalized_candidates:
            if not candidate["detected"]:
                rejected_candidates.append(self._reject(candidate, "not_detected"))
                continue
            if candidate["pattern_id"] in set(inactive_pattern_ids or set()):
                rejected_candidates.append(self._reject(candidate, "inactive_pattern"))
                continue
            if candidate["non_entry"]:
                rejected_candidates.append(self._reject(candidate, "non_entry_signal"))
                continue

            score, reasons = self._score_candidate(
                candidate=candidate,
                setup_families=normalized_setup_families,
                structure=structure,
                session_context=session_context,
            )
            candidate["score"] = round(score, 4)
            candidate["score_reasons"] = reasons
            scored_candidates.append(candidate)

        print(
            "[DECISION_ENGINE][CANDIDATES] "
            f"symbol={symbol} total={len(normalized_candidates)} "
            f"detected={sum(1 for item in normalized_candidates if item['detected'])} "
            f"scored={len(scored_candidates)} "
            f"ids={[item['pattern_id'] for item in normalized_candidates]}"
        )

        if not normalized_candidates or not any(item["detected"] for item in normalized_candidates):
            return self._no_candidate(symbol=symbol, rejected_candidates=rejected_candidates, reason="no_detected_actionable_candidate")

        if not scored_candidates:
            return {
                "symbol": symbol,
                "selected_setup_family": None,
                "selected_pattern_id": None,
                "selected_pattern_name": None,
                "decision_state": "CANDIDATE_REJECTED_INSUFFICIENT_QUALITY",
                "confidence": 0.0,
                "entry_bias": "NONE",
                "trigger_level": None,
                "invalidation_level": None,
                "supporting_factors": [],
                "rejected_candidates": rejected_candidates,
                "decision_reason": "all_detected_candidates_rejected",
            }

        direction_buckets: dict[str, list[dict]] = {}
        for candidate in scored_candidates:
            direction_buckets.setdefault(candidate["direction"], []).append(candidate)

        if len(direction_buckets) > 1:
            print(
                "[DECISION_ENGINE][TRUE_CONFLICT] "
                f"symbol={symbol} reason=rejected_true_conflict_opposing_direction "
                f"directions={sorted(direction_buckets.keys())}"
            )
            for candidate in scored_candidates:
                rejected_candidates.append(
                    self._reject(
                        candidate,
                        "rejected_true_conflict_opposing_direction",
                        score=candidate["score"],
                    )
                )
            return {
                "symbol": symbol,
                "selected_setup_family": None,
                "selected_pattern_id": None,
                "selected_pattern_name": None,
                "decision_state": "CANDIDATE_REJECTED_CONFLICT",
                "confidence": 0.0,
                "entry_bias": "NONE",
                "trigger_level": None,
                "invalidation_level": None,
                "supporting_factors": [],
                "rejected_candidates": rejected_candidates,
                "decision_reason": "rejected_true_conflict_opposing_direction",
            }

        compatibility_partitions = {"compatible": [], "incompatible": []}
        for candidate in scored_candidates:
            if self._is_execution_compatible(candidate, session_context=session_context):
                compatibility_partitions["compatible"].append(candidate)
            else:
                compatibility_partitions["incompatible"].append(candidate)
        print(
            "[DECISION_ENGINE][COMPATIBILITY] "
            f"symbol={symbol} compatible={[item['pattern_id'] for item in compatibility_partitions['compatible']]} "
            f"incompatible={[item['pattern_id'] for item in compatibility_partitions['incompatible']]}"
        )

        compatible_pool = compatibility_partitions["compatible"] or scored_candidates
        ranked = sorted(compatible_pool, key=self._ranking_key, reverse=True)
        selected = ranked[0]
        print(
            "[DECISION_ENGINE][RANKING] "
            f"symbol={symbol} order={[(item['pattern_id'], self._ranking_key(item)) for item in ranked]}"
        )

        for loser in ranked[1:]:
            rejected_candidates.append(
                self._reject(
                    loser,
                    "dropped_lower_priority_compatible_candidate",
                    score=loser["score"],
                )
            )
            print(
                "[DECISION_ENGINE][DROP] "
                f"symbol={symbol} pattern_id={loser['pattern_id']} "
                "reason=dropped_lower_priority_compatible_candidate"
            )
        for incompatible in compatibility_partitions["incompatible"]:
            rejected_candidates.append(
                self._reject(
                    incompatible,
                    "rejected_true_conflict_incompatible_execution_semantics",
                    score=incompatible["score"],
                )
            )
            print(
                "[DECISION_ENGINE][DROP] "
                f"symbol={symbol} pattern_id={incompatible['pattern_id']} "
                "reason=rejected_true_conflict_incompatible_execution_semantics"
            )

        output = {
            "symbol": symbol,
            "selected_setup_family": selected["setup_family"],
            "selected_pattern_id": selected["pattern_id"],
            "selected_pattern_name": selected["pattern_name"],
            "decision_state": "CANDIDATE_SELECTED",
            "confidence": selected["confidence"],
            "entry_bias": selected["direction"],
            "trigger_level": selected["trigger_level"],
            "invalidation_level": selected["invalidation_level"],
            "supporting_factors": selected["score_reasons"],
            "rejected_candidates": rejected_candidates,
            "decision_reason": "selected_best_compatible_candidate",
        }
        print(
            "[DECISION_ENGINE][SELECTED] "
            f"symbol={symbol} state=CANDIDATE_SELECTED selected_pattern={selected['pattern_id']} "
            "reason=selected_best_compatible_candidate"
        )
        return output

    def _score_candidate(
        self,
        *,
        candidate: dict,
        setup_families: set[str],
        structure: dict,
        session_context: str | None,
    ) -> tuple[float, list[str]]:
        score = 0.0
        reasons: list[str] = []

        score += self._SCORE_DETECTED
        reasons.append("detected")

        score += max(0.0, min(1.0, candidate["confidence"]))
        reasons.append("confidence")

        pattern_id = candidate["pattern_id"]
        if self._is_setup_compatible(pattern_id=pattern_id, setup_families=setup_families):
            score += self._SCORE_SETUP_COMPATIBLE
            reasons.append("setup_compatible")

        if self._is_structure_compatible(direction=candidate["direction"], structure=structure):
            score += self._SCORE_STRUCTURE_COMPATIBLE
            reasons.append("structure_compatible")

        if candidate["trigger_level"] is not None:
            score += self._SCORE_ACTIONABLE
            reasons.append("trigger_actionable")
        else:
            score -= self._PENALTY_MISSING_ACTIONABILITY
            reasons.append("missing_trigger_level_penalty")

        if candidate["invalidation_level"] is not None:
            score += self._SCORE_HAS_INVALIDATION
            reasons.append("invalidation_present")

        if candidate["session_valid"] is False:
            score -= self._PENALTY_SESSION_INCOMPATIBLE
            reasons.append("session_incompatible_penalty")

        return score, reasons

    def _normalize_candidate(self, item: Any, *, trace_by_pattern_id: dict[str, Any]) -> dict:
        pattern_id = self._to_text(self._get_first(item, "pattern_id", "setup_id", "id"))
        pattern_name = self._to_text(self._get_first(item, "pattern_name", "name")) or pattern_id
        trace = trace_by_pattern_id.get(pattern_id)

        confidence = self._safe_float(self._get_first(item, "confidence"))
        if confidence is None and trace is not None:
            confidence = self._safe_float(getattr(trace, "confidence", None))

        setup_family = self._to_text(self._get_first(item, "setup_family_id", "setup_family"))
        if not setup_family:
            setup_family = self._infer_setup_family(pattern_id)

        rejection_reason = self._to_text(self._get_first(item, "rejection_reason"))
        if not rejection_reason and trace is not None:
            rejection_reason = self._to_text(getattr(trace, "rejection_reason", None))

        detected = bool(self._get_first(item, "detected", default=False))
        if trace is not None:
            detected = bool(getattr(trace, "detected", detected))

        direction = self._to_text(self._get_first(item, "direction", default="LONG")) or "LONG"

        risk_flags = self._normalize_list(self._get_first(item, "risk_flags", default=[]))
        tags = self._normalize_list(self._get_first(item, "tags", default=[]))
        non_entry_flag = bool(self._get_first(item, "non_entry_signal", default=False))

        candidate = {
            "pattern_id": pattern_id,
            "pattern_name": pattern_name,
            "detected": detected,
            "confidence": max(0.0, min(1.0, confidence if confidence is not None else 0.0)),
            "direction": direction,
            "trigger_type": self._to_text(self._get_first(item, "trigger_type")),
            "trigger_level": self._safe_float(self._get_first(item, "trigger_level")),
            "invalidation_level": self._safe_float(self._get_first(item, "invalidation_level", "stop_level")),
            "rejection_reason": rejection_reason,
            "session_valid": self._get_first(item, "session_valid", default=True),
            "setup_family": setup_family,
            "non_entry": non_entry_flag or self._is_non_entry(tags=tags, risk_flags=risk_flags, reason=rejection_reason),
            "is_fallback": pattern_id.startswith("FALLBACK_"),
        }
        return candidate

    def _ranking_key(self, candidate: dict) -> tuple:
        return (
            1 if self._is_execution_compatible(candidate, session_context=None) else 0,
            1 if "setup_compatible" in candidate.get("score_reasons", []) else 0,
            1 if candidate["trigger_level"] is not None else 0,
            1 if candidate["invalidation_level"] is not None else 0,
            0 if candidate.get("is_fallback") else 1,
            candidate["score"],
            candidate["confidence"],
            candidate["pattern_id"],
        )

    @staticmethod
    def _is_execution_compatible(candidate: dict, *, session_context: str | None) -> bool:
        _ = session_context
        return candidate.get("session_valid", True) is not False

    @staticmethod
    def _get_first(item: Any, *keys: str, default: Any = None) -> Any:
        for key in keys:
            if isinstance(item, dict) and key in item:
                return item.get(key)
            if hasattr(item, key):
                return getattr(item, key)
        return default

    @staticmethod
    def _to_text(value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip().upper()

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        try:
            return None if value is None else float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _normalize_list(value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item).upper() for item in value]
        return []

    def _is_setup_compatible(self, *, pattern_id: str, setup_families: set[str]) -> bool:
        if not pattern_id or not setup_families:
            return False
        for family in setup_families:
            if pattern_id in self._COMPATIBILITY_MATRIX.get(family, set()):
                return True
        return False

    @staticmethod
    def _is_structure_compatible(*, direction: str, structure: dict) -> bool:
        trend = str((structure or {}).get("trend") or "").upper()
        if direction == "SHORT":
            return trend in {"DOWN", "SIDEWAYS"}
        return trend in {"UP", "SIDEWAYS"}

    def _is_non_entry(self, *, tags: list[str], risk_flags: list[str], reason: str) -> bool:
        haystack = " ".join([*tags, *risk_flags, reason]).upper()
        return any(marker in haystack for marker in self._NON_ENTRY_MARKERS)

    @staticmethod
    def _reject(candidate: dict, reason: str, *, score: float | None = None) -> dict:
        payload = {
            "pattern_id": candidate.get("pattern_id"),
            "pattern_name": candidate.get("pattern_name"),
            "reason": reason,
        }
        if score is not None:
            payload["score"] = round(float(score), 4)
        return payload

    @staticmethod
    def _infer_setup_family(pattern_id: str) -> str:
        mapping = {
            "P_ORB": "ORB",
            "P_PREMKT_BREAK": "PREMARKET_HIGH_BREAK",
            "P_OPENING_DRIVE": "OPENING_DRIVE",
            "P_HOD_BREAK": "HOD_BREAK",
            "P_FIRST_PULLBACK": "FIRST_PULLBACK",
            "P_MICRO_PULLBACK": "MICRO_PULLBACK",
            "P_BULL_FLAG": "BULL_FLAG",
            "P_CUP_HANDLE": "CUP_HANDLE",
            "P_MOMENTUM_RECLAIM": "MOMENTUM_RECLAIM",
            "P_RANGE_BREAKOUT": "RANGE_BREAK",
            "P_ASCENDING_TRIANGLE_BREAKOUT": "ASCENDING_TRIANGLE",
            "P_PENNANT_BREAK": "PENNANT",
            "P_EMA_PULLBACK": "EMA_PULLBACK",
            "P_VWAP_PULLBACK": "VWAP_PULLBACK",
            "P_THREE_BAR_PULLBACK": "THREE_BAR_PULLBACK",
            "P_SECOND_PULLBACK": "SECOND_PULLBACK",
        }
        return mapping.get(str(pattern_id or "").upper(), "UNKNOWN")

    @staticmethod
    def _no_candidate(*, symbol: str, rejected_candidates: list[dict], reason: str) -> dict:
        return {
            "symbol": symbol,
            "selected_setup_family": None,
            "selected_pattern_id": None,
            "selected_pattern_name": None,
            "decision_state": "NO_CANDIDATE",
            "confidence": 0.0,
            "entry_bias": "NONE",
            "trigger_level": None,
            "invalidation_level": None,
            "supporting_factors": [],
            "rejected_candidates": rejected_candidates,
            "decision_reason": reason,
        }
