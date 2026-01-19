from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional, Sequence

from src.config.config_resolver import get_config
from src.core.event_collector import EventCollector
from src.models.data_models import ScannerCandidate
from src.regime.baselines import BaselineStore
from src.regime.classifier import RegimeClassifier
from src.regime.contracts import (
    RegimePolicyDecision,
    RegimeSnapshot,
)
from src.regime.observers import observe_features
from src.regime.policy import RegimePolicy


class RegimeLayer:
    def __init__(
        self,
        *,
        event_collector: Optional[EventCollector] = None,
        baseline_store: Optional[BaselineStore] = None,
    ) -> None:
        self.event_collector = event_collector
        self.enabled = bool(get_config("ADAPTIVE_REGIME_LAYER_ENABLED"))
        self.log_level = str(get_config("ADAPTIVE_REGIME_LOG_LEVEL") or "INFO").upper()
        self.feature_set = str(get_config("ADAPTIVE_REGIME_FEATURE_SET") or "BASIC").upper()
        baseline_window = int(get_config("ADAPTIVE_REGIME_BASELINE_WINDOW"))
        ewma_alpha = float(get_config("ADAPTIVE_REGIME_EWMA_ALPHA"))
        self.baseline_store = baseline_store or BaselineStore(
            window=baseline_window,
            alpha=ewma_alpha,
        )
        self.classifier = RegimeClassifier()
        self.policy = RegimePolicy()

    def evaluate(
        self,
        *,
        candidates: Sequence[ScannerCandidate],
        session: str,
    ) -> tuple[RegimeSnapshot | None, RegimePolicyDecision | None]:
        if not self.enabled:
            return None, None

        timestamp_utc = datetime.now(timezone.utc).isoformat()
        features, data_quality_flags = observe_features(
            candidates=candidates,
            session=session,
            feature_set=self.feature_set,
        )
        baseline_snapshot = self.baseline_store.snapshot()
        snapshot = self.classifier.classify(
            features=features,
            baseline_stats=baseline_snapshot,
            data_quality_flags=data_quality_flags,
            timestamp_utc=timestamp_utc,
        )
        self.baseline_store.update(features)

        self._log_snapshot(snapshot)
        self._emit_snapshot(snapshot)

        policy_decision = self.policy.decide(snapshot, timestamp_utc=timestamp_utc)
        self._emit_policy(policy_decision)
        return snapshot, policy_decision

    def _log_snapshot(self, snapshot: RegimeSnapshot) -> None:
        if self.log_level not in {"INFO", "DEBUG"}:
            return
        features = snapshot.features.to_payload()
        summary = (
            f"[REGIME] label={snapshot.label.value} confidence={snapshot.confidence:.2f} "
            f"session={snapshot.session} universe={features['universe_count']} "
            f"spread_bps={features['median_spread_bps']} rvol={features['median_rvol']} "
            f"gap={features['median_gap_pct']} liquidity_thin={features['liquidity_thin_flag']}"
        )
        print(summary)
        if self.log_level == "DEBUG":
            print(f"[REGIME][DEBUG] features={features}")
            print(
                f"[REGIME][DEBUG] flags={[flag.value for flag in snapshot.data_quality_flags]}"
            )

    def _emit_snapshot(self, snapshot: RegimeSnapshot) -> None:
        if not self.event_collector:
            return
        self.event_collector.emit(
            event_type="REGIME_SNAPSHOT",
            source="RegimeLayer",
            payload=snapshot.to_payload(),
        )

    def _emit_policy(self, decision: RegimePolicyDecision) -> None:
        if not self.event_collector:
            return
        if not bool(get_config("ADAPTIVE_REGIME_POLICY_ENABLED")):
            return
        self.event_collector.emit(
            event_type="REGIME_POLICY_DECISION",
            source="RegimeLayer",
            payload=decision.to_payload(),
        )
