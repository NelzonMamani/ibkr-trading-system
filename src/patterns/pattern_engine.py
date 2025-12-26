"""
Pattern engine skeleton illustrating how detected patterns might be evaluated.

Phase 4: Deterministic, teaching-only pattern tagging based on scanner candidates.
No real pattern recognition, indicators, or scoring logic is present.
"""

from typing import List

from src.models.data_models import PatternResult, ScannerCandidate


class PatternEngine:
    """Minimal pattern engine placeholder with teaching-oriented logs."""

    def __init__(self) -> None:
        print("[BOOT] PatternEngine instantiated — phase 4 teaching placeholder (deterministic rules)")

    def evaluate_patterns(self, scanner_candidates: List[ScannerCandidate]) -> List[PatternResult]:
        """
        Apply deterministic teaching rules to scanner candidates.

        Each candidate yields zero or one PatternResult using simple thresholds to
        keep behavior transparent and repeatable.
        """

        print(f"[PATTERN] Received {len(scanner_candidates)} scanner candidates for teaching evaluation")
        pattern_results: List[PatternResult] = []

        for candidate in scanner_candidates:
            print(
                f"[PATTERN] Evaluating {candidate.symbol}: gap={candidate.gap_percent}% "
                f"float={candidate.float_millions}M rVol={candidate.rvol} — {candidate.rationale}"
            )

            pattern_assignment: PatternResult | None = None

            if candidate.gap_percent >= 8.0 and candidate.float_millions <= 50.0:
                rationale = (
                    "High gap paired with a relatively low float can fuel rapid moves; "
                    "tagging as a teaching-friendly gap-and-go scenario without claiming predictiveness."
                )
                print(
                    "[PATTERN] Assigned 'Gap and Go (Teaching)' because the gap is at least 8% "
                    "and float is under or equal to 50M shares for a supply-driven move illustration."
                )
                pattern_assignment = PatternResult(
                    symbol=candidate.symbol,
                    pattern_name="Gap and Go (Teaching)",
                    confidence=0.82,
                    rationale=rationale,
                )
            elif 4.0 <= candidate.gap_percent < 8.0 and candidate.float_millions >= 100.0:
                rationale = (
                    "Moderate gap with higher float suggests continuation fueled by participation rather "
                    "than scarcity; labeling for classroom discussion of liquid momentum names."
                )
                print(
                    "[PATTERN] Assigned 'Momentum Continuation (Teaching)' because the gap is between 4% and 8% "
                    "while float exceeds or equals 100M shares, highlighting liquidity-focused setups."
                )
                pattern_assignment = PatternResult(
                    symbol=candidate.symbol,
                    pattern_name="Momentum Continuation (Teaching)",
                    confidence=0.58,
                    rationale=rationale,
                )
            else:
                print(
                    "[PATTERN] No pattern assigned — candidate does not meet teaching thresholds; "
                    "this models disciplined selectivity rather than prediction."
                )

            if pattern_assignment:
                pattern_results.append(pattern_assignment)

        print(f"[PATTERN] Completed evaluation — generated {len(pattern_results)} teaching pattern result(s)")
        return pattern_results
