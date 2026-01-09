"""
Ross Momentum pattern engine with deterministic, explainable pattern evaluation.
"""

from dataclasses import dataclass
from typing import List, Tuple

from src.models.data_models import PatternResult, ScannerCandidate


@dataclass(frozen=True)
class PatternThresholds:
    min_gap_percent: float = 8.0
    min_relative_volume: float = 2.0
    max_float_millions: float = 50.0
    min_breakout_volume_ratio: float = 2.0
    min_breakout_hold_minutes: int = 2
    orb_window_minutes: int = 5
    min_momentum_move_pct: float = 5.0
    min_pullback_pct: float = 0.5
    max_pullback_pct: float = 3.0
    max_pullback_volume_ratio: float = 0.7
    min_vwap_hold_minutes: int = 2
    min_vwap_volume_ratio: float = 1.5
    max_hod_consolidation_pct: float = 2.0
    max_hod_extension_pct: float = 4.0
    min_hod_volume_ratio: float = 2.0
    min_liquid_rvol: float = 1.5


class PatternEngine:
    """Ross Momentum pattern engine with explicit rule checks and scoring."""

    def __init__(self, thresholds: PatternThresholds | None = None) -> None:
        self.thresholds = thresholds or PatternThresholds()
        print("[BOOT] PatternEngine instantiated — Ross Momentum pattern suite enabled")

    def evaluate_patterns(self, scanner_candidates: List[ScannerCandidate]) -> List[PatternResult]:
        """
        Apply deterministic Ross Momentum pattern logic to scanner candidates.

        Each candidate can emit zero or more PatternResult objects.
        """

        print(f"[PATTERN] Received {len(scanner_candidates)} scanner candidates for evaluation")
        pattern_results: List[PatternResult] = []

        for candidate in scanner_candidates:
            print(
                f"[PATTERN] Evaluating {candidate.symbol}: gap={candidate.gap_percent}% "
                f"float={candidate.float_millions}M rVol={candidate.rvol} — {candidate.rationale}"
            )
            if candidate.price is None:
                print(
                    "[PATTERN] Skipping candidate due to missing price "
                    f"symbol={candidate.symbol}"
                )
                continue
            if candidate.gap_percent is None or candidate.rvol is None or candidate.float_millions is None:
                print(
                    "[PATTERN] Skipping candidate due to missing teaching metrics "
                    f"symbol={candidate.symbol}"
                )
                continue
            if candidate.data_quality_flags:
                print(
                    "[PATTERN] Skipping candidate due to data quality flags "
                    f"symbol={candidate.symbol} flags={candidate.data_quality_flags}"
                )
                continue

            pattern_results.extend(self._evaluate_gap_and_go(candidate))
            pattern_results.extend(self._evaluate_orb_breakout(candidate))
            pattern_results.extend(self._evaluate_first_pullback(candidate))
            pattern_results.extend(self._evaluate_vwap_reclaim(candidate))
            pattern_results.extend(self._evaluate_hod_break(candidate))

        print(f"[PATTERN] Completed evaluation — generated {len(pattern_results)} pattern result(s)")
        return pattern_results

    def _evaluate_gap_and_go(self, candidate: ScannerCandidate) -> List[PatternResult]:
        thresholds = self.thresholds
        reasons = []
        criteria = []
        gap_ok = candidate.gap_percent >= thresholds.min_gap_percent
        rvol_ok = candidate.rvol >= thresholds.min_relative_volume
        float_ok = candidate.float_millions <= thresholds.max_float_millions
        broke_level, level_label = self._broke_premarket_or_early_high(candidate)
        volume_ok = self._volume_ratio_ok(candidate, thresholds.min_breakout_volume_ratio)

        if gap_ok:
            criteria.append(f"gap_percent={candidate.gap_percent:.2f}>= {thresholds.min_gap_percent}")
        if rvol_ok:
            criteria.append(f"rvol={candidate.rvol:.2f}>= {thresholds.min_relative_volume}")
        if float_ok:
            criteria.append(
                f"float_millions={candidate.float_millions:.2f}<= {thresholds.max_float_millions}"
            )
        if broke_level:
            criteria.append(level_label)
        if volume_ok:
            criteria.append(
                f"breakout_volume_ratio={candidate.breakout_volume_ratio:.2f}>= "
                f"{thresholds.min_breakout_volume_ratio}"
            )

        if not (gap_ok and rvol_ok and float_ok and broke_level and volume_ok):
            return []

        if not self._passes_breakout_filters(candidate, "GAP_AND_GO", reasons):
            return []

        confidence = self._score_confidence(candidate, thresholds.min_breakout_volume_ratio)
        rationale = self._format_rationale(
            criteria,
            confidence,
            "Gap and Go breakout with premarket/early high confirmation.",
        )
        return [
            self._build_pattern_result(candidate, "GAP_AND_GO", confidence, rationale)
        ]

    def _evaluate_orb_breakout(self, candidate: ScannerCandidate) -> List[PatternResult]:
        thresholds = self.thresholds
        reasons = []
        criteria = []
        session_ok = self._session_is_regular(candidate)
        orb_window_ok = (
            candidate.opening_range_minutes is not None
            and candidate.opening_range_minutes <= thresholds.orb_window_minutes
        )
        range_high = candidate.opening_range_high
        broke_range = range_high is not None and candidate.price > range_high
        hold_ok = self._hold_minutes_ok(candidate, thresholds.min_breakout_hold_minutes)
        volume_ok = self._volume_ratio_ok(candidate, thresholds.min_breakout_volume_ratio)

        if session_ok:
            criteria.append("session=REGULAR")
        if orb_window_ok:
            criteria.append(
                f"opening_range_minutes={candidate.opening_range_minutes}<= "
                f"{thresholds.orb_window_minutes}"
            )
        if broke_range:
            criteria.append(f"price={candidate.price:.2f} broke opening_range_high={range_high:.2f}")
        if hold_ok:
            criteria.append(
                f"breakout_hold_minutes={candidate.breakout_hold_minutes}>= "
                f"{thresholds.min_breakout_hold_minutes}"
            )
        if volume_ok:
            criteria.append(
                f"breakout_volume_ratio={candidate.breakout_volume_ratio:.2f}>= "
                f"{thresholds.min_breakout_volume_ratio}"
            )

        if not (session_ok and orb_window_ok and broke_range and hold_ok and volume_ok):
            return []

        if not self._passes_breakout_filters(candidate, "ORB_BREAKOUT", reasons):
            return []

        confidence = self._score_confidence(candidate, thresholds.min_breakout_volume_ratio)
        rationale = self._format_rationale(
            criteria,
            confidence,
            "Opening range break with hold and volume confirmation.",
        )
        return [
            self._build_pattern_result(candidate, "ORB_BREAKOUT", confidence, rationale)
        ]

    def _evaluate_first_pullback(self, candidate: ScannerCandidate) -> List[PatternResult]:
        thresholds = self.thresholds
        reasons = []
        criteria = []
        momentum_ok = (
            candidate.momentum_move_pct is not None
            and candidate.momentum_move_pct >= thresholds.min_momentum_move_pct
        )
        pullback_ok = (
            candidate.pullback_pct is not None
            and thresholds.min_pullback_pct <= candidate.pullback_pct <= thresholds.max_pullback_pct
        )
        pullback_volume_ok = (
            candidate.pullback_volume_ratio is not None
            and candidate.pullback_volume_ratio <= thresholds.max_pullback_volume_ratio
        )
        higher_low_ok = candidate.higher_low is True
        pullback_high = candidate.pullback_high
        broke_pullback_high = pullback_high is not None and candidate.price > pullback_high
        volume_ok = self._volume_ratio_ok(candidate, thresholds.min_breakout_volume_ratio)

        if momentum_ok:
            criteria.append(
                f"momentum_move_pct={candidate.momentum_move_pct:.2f}>= "
                f"{thresholds.min_momentum_move_pct}"
            )
        if pullback_ok:
            criteria.append(
                f"pullback_pct={candidate.pullback_pct:.2f} within "
                f"{thresholds.min_pullback_pct}-{thresholds.max_pullback_pct}"
            )
        if pullback_volume_ok:
            criteria.append(
                f"pullback_volume_ratio={candidate.pullback_volume_ratio:.2f}<= "
                f"{thresholds.max_pullback_volume_ratio}"
            )
        if higher_low_ok:
            criteria.append("higher_low=True")
        if broke_pullback_high:
            criteria.append(f"price={candidate.price:.2f} broke pullback_high={pullback_high:.2f}")
        if volume_ok:
            criteria.append(
                f"breakout_volume_ratio={candidate.breakout_volume_ratio:.2f}>= "
                f"{thresholds.min_breakout_volume_ratio}"
            )

        if not (
            momentum_ok
            and pullback_ok
            and pullback_volume_ok
            and higher_low_ok
            and broke_pullback_high
            and volume_ok
        ):
            return []

        if not self._passes_breakout_filters(candidate, "FIRST_PULLBACK", reasons):
            return []

        confidence = self._score_confidence(candidate, thresholds.min_breakout_volume_ratio)
        rationale = self._format_rationale(
            criteria,
            confidence,
            "First pullback continuation with higher low confirmation.",
        )
        return [
            self._build_pattern_result(candidate, "FIRST_PULLBACK", confidence, rationale)
        ]

    def _evaluate_vwap_reclaim(self, candidate: ScannerCandidate) -> List[PatternResult]:
        thresholds = self.thresholds
        criteria = []
        session_ok = self._session_is_regular(candidate)
        vwap_ok = candidate.vwap is not None and candidate.price > candidate.vwap
        hold_ok = (
            candidate.vwap_hold_minutes is not None
            and candidate.vwap_hold_minutes >= thresholds.min_vwap_hold_minutes
        )
        volume_ok = (
            candidate.breakout_volume_ratio is not None
            and candidate.breakout_volume_ratio >= thresholds.min_vwap_volume_ratio
        )
        liquid_ok = candidate.rvol >= thresholds.min_liquid_rvol

        if session_ok:
            criteria.append("session=REGULAR")
        if vwap_ok:
            criteria.append(f"price={candidate.price:.2f} reclaimed vwap={candidate.vwap:.2f}")
        if hold_ok:
            criteria.append(
                f"vwap_hold_minutes={candidate.vwap_hold_minutes}>= "
                f"{thresholds.min_vwap_hold_minutes}"
            )
        if volume_ok:
            criteria.append(
                f"vwap_volume_ratio={candidate.breakout_volume_ratio:.2f}>= "
                f"{thresholds.min_vwap_volume_ratio}"
            )
        if liquid_ok:
            criteria.append(f"rvol={candidate.rvol:.2f}>= {thresholds.min_liquid_rvol}")

        if not (session_ok and vwap_ok and hold_ok and volume_ok and liquid_ok):
            return []

        confidence = self._score_confidence(candidate, thresholds.min_vwap_volume_ratio)
        rationale = self._format_rationale(
            criteria,
            confidence,
            "VWAP reclaim with hold confirmation and liquid volume.",
        )
        return [
            self._build_pattern_result(candidate, "VWAP_RECLAIM", confidence, rationale)
        ]

    def _evaluate_hod_break(self, candidate: ScannerCandidate) -> List[PatternResult]:
        thresholds = self.thresholds
        reasons = []
        criteria = []
        hod = candidate.hod
        broke_hod = hod is not None and candidate.price > hod
        consolidation_ok = (
            candidate.consolidation_range_pct is not None
            and candidate.consolidation_range_pct <= thresholds.max_hod_consolidation_pct
        )
        extension_ok = (
            candidate.extension_pct is not None
            and candidate.extension_pct <= thresholds.max_hod_extension_pct
        )
        volume_ok = (
            candidate.breakout_volume_ratio is not None
            and candidate.breakout_volume_ratio >= thresholds.min_hod_volume_ratio
        )

        if broke_hod:
            criteria.append(f"price={candidate.price:.2f} broke hod={hod:.2f}")
        if consolidation_ok:
            criteria.append(
                f"consolidation_range_pct={candidate.consolidation_range_pct:.2f}<= "
                f"{thresholds.max_hod_consolidation_pct}"
            )
        if extension_ok:
            criteria.append(
                f"extension_pct={candidate.extension_pct:.2f}<= "
                f"{thresholds.max_hod_extension_pct}"
            )
        if volume_ok:
            criteria.append(
                f"breakout_volume_ratio={candidate.breakout_volume_ratio:.2f}>= "
                f"{thresholds.min_hod_volume_ratio}"
            )

        if not (broke_hod and consolidation_ok and extension_ok and volume_ok):
            return []

        if not self._passes_breakout_filters(candidate, "HOD_BREAK", reasons):
            return []

        confidence = self._score_confidence(candidate, thresholds.min_hod_volume_ratio)
        rationale = self._format_rationale(
            criteria,
            confidence,
            "High-of-day continuation with tight consolidation.",
        )
        return [
            self._build_pattern_result(candidate, "HOD_BREAK", confidence, rationale)
        ]

    def _broke_premarket_or_early_high(
        self, candidate: ScannerCandidate
    ) -> Tuple[bool, str]:
        if candidate.premarket_high is not None and candidate.price > candidate.premarket_high:
            return True, f"price={candidate.price:.2f} broke premarket_high={candidate.premarket_high:.2f}"
        if candidate.early_session_high is not None and candidate.price > candidate.early_session_high:
            return True, (
                f"price={candidate.price:.2f} broke early_session_high={candidate.early_session_high:.2f}"
            )
        return False, ""

    def _passes_breakout_filters(
        self,
        candidate: ScannerCandidate,
        pattern_name: str,
        reasons: List[str],
    ) -> bool:
        if candidate.breakout_reject:
            reasons.append("IMMEDIATE_REJECTION_AFTER_BREAKOUT")
        if candidate.breakout_volume_ratio is not None and candidate.breakout_volume_ratio < (
            self.thresholds.min_breakout_volume_ratio
        ):
            reasons.append("LOW_VOLUME_BREAK_ATTEMPT")
        if candidate.breakout_hold_minutes is not None and candidate.breakout_hold_minutes < (
            self.thresholds.min_breakout_hold_minutes
        ):
            reasons.append("FAILED_HOLD_ABOVE_KEY_LEVEL")
        if reasons:
            reason_text = ", ".join(reasons)
            print(
                f"[PATTERN] {pattern_name} invalidated for symbol={candidate.symbol} "
                f"INVALIDATION_REASON={reason_text}"
            )
            return False
        return True

    def _session_is_regular(self, candidate: ScannerCandidate) -> bool:
        return (candidate.session or "").upper() == "REGULAR"

    def _hold_minutes_ok(self, candidate: ScannerCandidate, min_hold: int) -> bool:
        return (
            candidate.breakout_hold_minutes is not None
            and candidate.breakout_hold_minutes >= min_hold
        )

    def _volume_ratio_ok(self, candidate: ScannerCandidate, min_ratio: float) -> bool:
        return (
            candidate.breakout_volume_ratio is not None
            and candidate.breakout_volume_ratio >= min_ratio
        )

    def _score_confidence(self, candidate: ScannerCandidate, min_volume_ratio: float) -> float:
        gap_score = min(max(candidate.gap_percent / 15.0, 0.0), 1.0)
        rvol_score = min(max(candidate.rvol / 4.0, 0.0), 1.0)
        breakout_ratio = candidate.breakout_volume_ratio or min_volume_ratio
        breakout_score = min(max(breakout_ratio / min_volume_ratio, 0.0), 1.0)
        volume_score = min(1.0, (rvol_score + breakout_score) / 2.0)

        if candidate.float_millions <= self.thresholds.max_float_millions:
            float_score = 1.0
        elif candidate.float_millions <= 100.0:
            float_score = 0.7
        else:
            float_score = 0.4

        session_score = 1.0 if self._session_is_regular(candidate) else 0.6
        confidence = (
            gap_score * 0.35
            + volume_score * 0.35
            + float_score * 0.2
            + session_score * 0.1
        )
        return max(0.0, min(confidence, 1.0))

    def _format_rationale(
        self, criteria: List[str], confidence: float, summary: str
    ) -> str:
        details = "; ".join(criteria)
        return f"{summary} | {details} | confidence={confidence:.2f}"

    def _build_pattern_result(
        self,
        candidate: ScannerCandidate,
        pattern_name: str,
        confidence: float,
        rationale: str,
    ) -> PatternResult:
        return PatternResult(
            symbol=candidate.symbol,
            pattern_name=pattern_name,
            confidence=confidence,
            rationale=rationale,
            gap_percent=candidate.gap_percent,
            rvol=candidate.rvol,
            float_millions=candidate.float_millions,
            data_quality_flags=candidate.data_quality_flags,
        )
