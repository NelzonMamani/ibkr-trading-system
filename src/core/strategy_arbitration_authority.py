from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
import hashlib
from typing import Any, Iterable, Sequence


class StrategyArbitrationStatus(str, Enum):
    APPROVED = "APPROVED"
    SELECTED = "SELECTED"
    REJECTED = "REJECTED"
    DEFERRED = "DEFERRED"
    BLOCKED = "BLOCKED"
    DUPLICATE_SYMBOL = "DUPLICATE_SYMBOL"
    OPPOSING_INTENT = "OPPOSING_INTENT"
    STALE_INTENT = "STALE_INTENT"
    STRATEGY_DISABLED = "STRATEGY_DISABLED"
    RECOVERY_NOT_COMPLETE = "RECOVERY_NOT_COMPLETE"
    READ_ONLY_BLOCKED = "READ_ONLY_BLOCKED"
    NO_ACTION = "NO_ACTION"


@dataclass(frozen=True)
class StrategyIntentCandidate:
    intent_id: str
    strategy_id: str
    symbol: str
    side: str
    requested_quantity: int
    requested_notional: float
    confidence: float = 0.0
    priority: int = 0
    score: float = 0.0
    timestamp: datetime | None = None
    setup_id: str | None = None
    reason_code: str | None = None
    risk_hint: float | None = None
    capital_hint: float | None = None
    session: str | None = None
    run_mode: str | None = None
    audit_payload: dict[str, Any] = field(default_factory=dict)
    status: StrategyArbitrationStatus = StrategyArbitrationStatus.NO_ACTION
    reason: str | None = None
    sort_key: tuple[Any, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        payload["timestamp"] = self.timestamp.isoformat() if self.timestamp else None
        payload["sort_key"] = list(self.sort_key)
        return payload


@dataclass(frozen=True)
class StrategyArbitrationBatch:
    batch_id: str
    run_mode: str
    candidates: list[StrategyIntentCandidate]
    now: datetime | None = None
    recovery_complete: bool = True
    disabled_strategies: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class StrategyArbitrationDecision:
    arbitration_id: str
    timestamp: str
    run_mode: str
    status: StrategyArbitrationStatus
    selected_intents: list[StrategyIntentCandidate]
    rejected_intents: list[StrategyIntentCandidate]
    deferred_intents: list[StrategyIntentCandidate]
    ranking_order: list[str]
    reasons: dict[str, str]
    deterministic_seed: str
    audit_payload: dict[str, Any] = field(default_factory=dict)

    @property
    def selected_intent_ids(self) -> list[str]:
        return [candidate.intent_id for candidate in self.selected_intents]

    @property
    def executable(self) -> bool:
        return self.status == StrategyArbitrationStatus.SELECTED and bool(self.selected_intents)

    def to_dict(self) -> dict[str, Any]:
        return {
            "arbitration_id": self.arbitration_id,
            "timestamp": self.timestamp,
            "run_mode": self.run_mode,
            "status": self.status.value,
            "selected_intents": [candidate.to_dict() for candidate in self.selected_intents],
            "rejected_intents": [candidate.to_dict() for candidate in self.rejected_intents],
            "deferred_intents": [candidate.to_dict() for candidate in self.deferred_intents],
            "ranking_order": list(self.ranking_order),
            "reasons": dict(self.reasons),
            "deterministic_seed": self.deterministic_seed,
            "audit_payload": dict(self.audit_payload),
        }


class StrategyArbitrationAuthority:
    """Canonical P9 authority for deterministic strategy intent arbitration."""

    DEFAULT_MAX_STALENESS_SECONDS = 300

    def __init__(
        self,
        *,
        event_collector: Any | None = None,
        max_staleness_seconds: int = DEFAULT_MAX_STALENESS_SECONDS,
        disabled_strategies: Iterable[str] | None = None,
    ) -> None:
        self.event_collector = event_collector
        self.max_staleness_seconds = int(max_staleness_seconds)
        self.disabled_strategies = {
            self._normalize_strategy(strategy_id)
            for strategy_id in (disabled_strategies or [])
        }

    def arbitrate_batch(self, batch: StrategyArbitrationBatch) -> StrategyArbitrationDecision:
        return self.arbitrate(
            batch.candidates,
            run_mode=batch.run_mode,
            now=batch.now,
            recovery_complete=batch.recovery_complete,
            disabled_strategies=batch.disabled_strategies,
            audit_payload={"batch_id": batch.batch_id},
        )

    def arbitrate(
        self,
        candidates: Sequence[StrategyIntentCandidate | object],
        *,
        run_mode: str = "SIM",
        now: datetime | str | None = None,
        recovery_complete: bool = True,
        disabled_strategies: Iterable[str] | None = None,
        audit_payload: dict[str, Any] | None = None,
    ) -> StrategyArbitrationDecision:
        effective_mode = str(run_mode or "SIM").upper()
        now_dt = self._coerce_timestamp(now)
        decision_timestamp = now_dt or datetime.now(timezone.utc)
        disabled = set(self.disabled_strategies)
        disabled.update(self._normalize_strategy(item) for item in (disabled_strategies or []))
        prepared = [
            self._with_sort_key(self.candidate_from_intent(candidate, run_mode=effective_mode))
            for candidate in candidates
        ]

        print(
            "[ARBITRATION][START] "
            f"run_mode={effective_mode} candidates={len(prepared)} recovery_complete={recovery_complete}"
        )
        for candidate in prepared:
            print(
                "[ARBITRATION][CANDIDATE] "
                f"intent_id={candidate.intent_id} strategy_id={candidate.strategy_id} "
                f"symbol={candidate.symbol} side={candidate.side} priority={candidate.priority} "
                f"confidence={candidate.confidence:.4f}"
            )

        selected: list[StrategyIntentCandidate] = []
        rejected: list[StrategyIntentCandidate] = []
        deferred: list[StrategyIntentCandidate] = []

        if not prepared:
            return self._finalize_decision(
                run_mode=effective_mode,
                timestamp=decision_timestamp,
                status=StrategyArbitrationStatus.NO_ACTION,
                selected=selected,
                rejected=rejected,
                deferred=deferred,
                ranking_order=[],
                audit_payload=audit_payload,
            )

        if not recovery_complete:
            rejected = [
                self._reject(candidate, StrategyArbitrationStatus.RECOVERY_NOT_COMPLETE, "RECOVERY_NOT_COMPLETE")
                for candidate in prepared
            ]
            return self._finalize_decision(
                run_mode=effective_mode,
                timestamp=decision_timestamp,
                status=StrategyArbitrationStatus.RECOVERY_NOT_COMPLETE,
                selected=selected,
                rejected=rejected,
                deferred=deferred,
                ranking_order=[candidate.intent_id for candidate in self._rank(prepared)],
                audit_payload=audit_payload,
            )

        if effective_mode == "READ_ONLY":
            rejected = [
                self._reject(candidate, StrategyArbitrationStatus.READ_ONLY_BLOCKED, "READ_ONLY_BLOCKED")
                for candidate in prepared
            ]
            return self._finalize_decision(
                run_mode=effective_mode,
                timestamp=decision_timestamp,
                status=StrategyArbitrationStatus.READ_ONLY_BLOCKED,
                selected=selected,
                rejected=rejected,
                deferred=deferred,
                ranking_order=[candidate.intent_id for candidate in self._rank(prepared)],
                audit_payload=audit_payload,
            )

        eligible: list[StrategyIntentCandidate] = []
        for candidate in prepared:
            if candidate.strategy_id in disabled:
                rejected.append(self._reject(candidate, StrategyArbitrationStatus.STRATEGY_DISABLED, "STRATEGY_DISABLED"))
                continue
            if self._is_stale(candidate, now_dt):
                rejected.append(self._reject(candidate, StrategyArbitrationStatus.STALE_INTENT, "STALE_INTENT"))
                continue
            if candidate.requested_quantity <= 0:
                rejected.append(self._reject(candidate, StrategyArbitrationStatus.NO_ACTION, "NO_REQUESTED_QUANTITY"))
                continue
            eligible.append(candidate)

        deduped, duplicate_rejections = self._dedupe_same_strategy(eligible)
        rejected.extend(duplicate_rejections)

        by_symbol: dict[str, list[StrategyIntentCandidate]] = {}
        for candidate in deduped:
            by_symbol.setdefault(candidate.symbol, []).append(candidate)

        ranking_order: list[str] = []
        for symbol in sorted(by_symbol.keys()):
            ranked = self._rank(by_symbol[symbol])
            ranking_order.extend(candidate.intent_id for candidate in ranked)
            winner = ranked[0]
            selected.append(self._select(winner))
            if len(ranked) > 1:
                conflict_status = self._symbol_conflict_status(ranked)
                for loser in ranked[1:]:
                    rejected.append(self._reject(loser, conflict_status, conflict_status.value))

        status = StrategyArbitrationStatus.SELECTED if selected else StrategyArbitrationStatus.BLOCKED
        return self._finalize_decision(
            run_mode=effective_mode,
            timestamp=decision_timestamp,
            status=status,
            selected=selected,
            rejected=rejected,
            deferred=deferred,
            ranking_order=ranking_order,
            audit_payload=audit_payload,
        )

    def candidate_from_intent(
        self,
        intent: StrategyIntentCandidate | object,
        *,
        run_mode: str | None = None,
    ) -> StrategyIntentCandidate:
        if isinstance(intent, StrategyIntentCandidate):
            return replace(
                intent,
                strategy_id=self._normalize_strategy(intent.strategy_id),
                symbol=self._normalize_symbol(intent.symbol),
                side=self._normalize_side(intent.side),
                requested_quantity=max(0, int(intent.requested_quantity or 0)),
                requested_notional=max(0.0, float(intent.requested_notional or 0.0)),
                confidence=self._clamp01(float(intent.confidence or 0.0)),
                run_mode=run_mode or intent.run_mode,
            )

        symbol = self._normalize_symbol(getattr(intent, "symbol", None))
        side = self._normalize_side(getattr(intent, "direction", None) or getattr(intent, "side", None))
        strategy_id = self._normalize_strategy(
            getattr(intent, "strategy_id", None)
            or getattr(intent, "strategy_name", None)
            or "UNKNOWN"
        )
        requested_quantity = self._to_int(
            getattr(intent, "requested_quantity", None)
            or getattr(intent, "quantity", None)
            or getattr(intent, "max_position_size", None),
            default=1,
        )
        reference_price = self._to_float(
            getattr(intent, "entry_price", None)
            or getattr(intent, "price", None)
            or getattr(intent, "raw_price", None),
            default=0.0,
        )
        requested_notional = self._to_float(
            getattr(intent, "requested_notional", None)
            or getattr(intent, "position_exposure", None)
            or getattr(intent, "requested_exposure", None)
            or getattr(intent, "trade_value", None)
            or getattr(intent, "exposure", None),
            default=0.0,
        )
        if requested_notional <= 0.0:
            requested_notional = max(0.0, float(requested_quantity) * reference_price)

        setup_id = (
            getattr(intent, "setup_id", None)
            or getattr(intent, "setup_family_id", None)
            or getattr(intent, "pattern_name", None)
            or getattr(intent, "trigger_id", None)
        )
        intent_id = str(getattr(intent, "intent_id", None) or "").strip()
        if not intent_id:
            intent_id = self.intent_id_for(
                strategy_id=strategy_id,
                symbol=symbol,
                side=side,
                setup_id=str(setup_id or ""),
                decision_id=str(getattr(intent, "decision_id", None) or ""),
            )
            try:
                setattr(intent, "intent_id", intent_id)
            except Exception:
                pass

        confidence = self._clamp01(self._to_float(getattr(intent, "confidence", None), default=0.0))
        score = self._to_float(
            getattr(intent, "score", None)
            or getattr(intent, "quality_score", None)
            or getattr(intent, "scanner_score", None),
            default=confidence,
        )
        priority = self._to_int(
            getattr(intent, "priority", None)
            or getattr(intent, "strategy_priority", None),
            default=0,
        )
        audit_payload = dict(getattr(intent, "audit_payload", None) or {})
        audit_payload.setdefault("source_type", type(intent).__name__)

        return StrategyIntentCandidate(
            intent_id=intent_id,
            strategy_id=strategy_id,
            symbol=symbol,
            side=side,
            requested_quantity=max(0, requested_quantity),
            requested_notional=max(0.0, requested_notional),
            confidence=confidence,
            priority=priority,
            score=score,
            timestamp=self._coerce_timestamp(getattr(intent, "timestamp", None) or getattr(intent, "created_at", None)),
            setup_id=str(setup_id) if setup_id is not None else None,
            reason_code=getattr(intent, "reason_code", None),
            risk_hint=self._optional_float(getattr(intent, "risk_hint", None) or getattr(intent, "risk_score", None)),
            capital_hint=self._optional_float(
                getattr(intent, "capital_hint", None)
                or getattr(intent, "required_capital", None)
                or requested_notional
            ),
            session=getattr(intent, "session", None),
            run_mode=run_mode,
            audit_payload=audit_payload,
        )

    @staticmethod
    def intent_id_for(
        *,
        strategy_id: str,
        symbol: str,
        side: str,
        setup_id: str = "",
        decision_id: str = "",
    ) -> str:
        seed = "|".join([strategy_id, symbol, side, setup_id, decision_id])
        digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
        return f"p9-{digest}"

    def _dedupe_same_strategy(
        self,
        candidates: Sequence[StrategyIntentCandidate],
    ) -> tuple[list[StrategyIntentCandidate], list[StrategyIntentCandidate]]:
        grouped: dict[tuple[str, str, str], list[StrategyIntentCandidate]] = {}
        for candidate in candidates:
            key = (
                candidate.strategy_id,
                candidate.symbol,
                candidate.side,
            )
            grouped.setdefault(key, []).append(candidate)

        kept: list[StrategyIntentCandidate] = []
        rejected: list[StrategyIntentCandidate] = []
        for key in sorted(grouped.keys()):
            ranked = self._rank(grouped[key])
            kept.append(ranked[0])
            for duplicate in ranked[1:]:
                rejected.append(
                    self._reject(
                        duplicate,
                        StrategyArbitrationStatus.DUPLICATE_SYMBOL,
                        "DUPLICATE_STRATEGY_INTENT",
                    )
                )
        return kept, rejected

    def _rank(self, candidates: Sequence[StrategyIntentCandidate]) -> list[StrategyIntentCandidate]:
        return sorted(candidates, key=lambda candidate: candidate.sort_key or self._sort_key(candidate))

    def _with_sort_key(self, candidate: StrategyIntentCandidate) -> StrategyIntentCandidate:
        return replace(candidate, sort_key=self._sort_key(candidate))

    def _sort_key(self, candidate: StrategyIntentCandidate) -> tuple[Any, ...]:
        timestamp_score = candidate.timestamp.timestamp() if candidate.timestamp else 0.0
        risk_hint = candidate.risk_hint if candidate.risk_hint is not None else 0.0
        capital_hint = candidate.capital_hint if candidate.capital_hint is not None else 0.0
        return (
            -int(candidate.priority),
            -float(candidate.confidence),
            -float(candidate.score),
            float(risk_hint),
            float(capital_hint),
            -float(timestamp_score),
            candidate.strategy_id,
            candidate.symbol,
            candidate.intent_id,
        )

    def _symbol_conflict_status(
        self,
        ranked: Sequence[StrategyIntentCandidate],
    ) -> StrategyArbitrationStatus:
        sides = {self._direction_group(candidate.side) for candidate in ranked}
        if "LONG" in sides and "SHORT" in sides:
            print(f"[ARBITRATION][OPPOSING] symbol={ranked[0].symbol}")
            return StrategyArbitrationStatus.OPPOSING_INTENT
        print(f"[ARBITRATION][DUPLICATE] symbol={ranked[0].symbol}")
        return StrategyArbitrationStatus.DUPLICATE_SYMBOL

    def _is_stale(self, candidate: StrategyIntentCandidate, now: datetime | None) -> bool:
        if now is None or candidate.timestamp is None:
            return False
        age_seconds = (now - candidate.timestamp).total_seconds()
        if age_seconds > self.max_staleness_seconds:
            print(f"[ARBITRATION][STALE] intent_id={candidate.intent_id} age_seconds={age_seconds:.0f}")
            return True
        return False

    def _select(self, candidate: StrategyIntentCandidate) -> StrategyIntentCandidate:
        selected = replace(candidate, status=StrategyArbitrationStatus.SELECTED, reason="SELECTED")
        print(
            "[ARBITRATION][SELECTED] "
            f"intent_id={selected.intent_id} strategy_id={selected.strategy_id} symbol={selected.symbol}"
        )
        return selected

    def _reject(
        self,
        candidate: StrategyIntentCandidate,
        status: StrategyArbitrationStatus,
        reason: str,
    ) -> StrategyIntentCandidate:
        rejected = replace(candidate, status=status, reason=reason)
        print(
            "[ARBITRATION][REJECTED] "
            f"intent_id={rejected.intent_id} strategy_id={rejected.strategy_id} "
            f"symbol={rejected.symbol} status={status.value} reason={reason}"
        )
        return rejected

    def _finalize_decision(
        self,
        *,
        run_mode: str,
        timestamp: datetime,
        status: StrategyArbitrationStatus,
        selected: list[StrategyIntentCandidate],
        rejected: list[StrategyIntentCandidate],
        deferred: list[StrategyIntentCandidate],
        ranking_order: list[str],
        audit_payload: dict[str, Any] | None,
    ) -> StrategyArbitrationDecision:
        reasons = {
            candidate.intent_id: str(candidate.reason or candidate.status.value)
            for candidate in [*selected, *rejected, *deferred]
        }
        deterministic_seed = self._deterministic_seed(
            run_mode=run_mode,
            status=status,
            selected=selected,
            rejected=rejected,
            deferred=deferred,
            ranking_order=ranking_order,
        )
        decision = StrategyArbitrationDecision(
            arbitration_id=f"arb-{deterministic_seed[:16]}",
            timestamp=timestamp.isoformat(),
            run_mode=run_mode,
            status=status,
            selected_intents=selected,
            rejected_intents=rejected,
            deferred_intents=deferred,
            ranking_order=list(ranking_order),
            reasons=reasons,
            deterministic_seed=deterministic_seed,
            audit_payload={
                **(audit_payload or {}),
                "selected_count": len(selected),
                "rejected_count": len(rejected),
                "deferred_count": len(deferred),
            },
        )
        print(
            "[ARBITRATION][AUDIT] "
            f"arbitration_id={decision.arbitration_id} selected={len(selected)} "
            f"rejected={len(rejected)} deferred={len(deferred)}"
        )
        self._emit_audit_event(decision)
        print(
            "[ARBITRATION][COMPLETE] "
            f"arbitration_id={decision.arbitration_id} status={decision.status.value}"
        )
        return decision

    def _emit_audit_event(self, decision: StrategyArbitrationDecision) -> None:
        if self.event_collector is None:
            return
        emitter = getattr(self.event_collector, "emit", None)
        if not callable(emitter):
            return
        payload = {
            "arbitration_id": decision.arbitration_id,
            "run_mode": decision.run_mode,
            "timestamp": decision.timestamp,
            "status": decision.status.value,
            "selected_intent_ids": decision.selected_intent_ids,
            "rejected_intent_ids": [candidate.intent_id for candidate in decision.rejected_intents],
            "deferred_intent_ids": [candidate.intent_id for candidate in decision.deferred_intents],
            "ranking_order": decision.ranking_order,
            "reasons": decision.reasons,
            "deterministic_seed": decision.deterministic_seed,
            "audit_payload": decision.audit_payload,
        }
        try:
            emitter(
                event_type="STRATEGY_ARBITRATION_DECISION",
                source="StrategyArbitrationAuthority",
                payload=payload,
            )
        except TypeError:
            emitter("STRATEGY_ARBITRATION_DECISION", "StrategyArbitrationAuthority", payload)

    def _deterministic_seed(
        self,
        *,
        run_mode: str,
        status: StrategyArbitrationStatus,
        selected: Sequence[StrategyIntentCandidate],
        rejected: Sequence[StrategyIntentCandidate],
        deferred: Sequence[StrategyIntentCandidate],
        ranking_order: Sequence[str],
    ) -> str:
        rows = [
            run_mode,
            status.value,
            ",".join(ranking_order),
            ",".join(f"{candidate.intent_id}:{candidate.status.value}" for candidate in selected),
            ",".join(f"{candidate.intent_id}:{candidate.status.value}" for candidate in rejected),
            ",".join(f"{candidate.intent_id}:{candidate.status.value}" for candidate in deferred),
        ]
        return hashlib.sha256("|".join(rows).encode("utf-8")).hexdigest()

    @staticmethod
    def _normalize_strategy(value: Any) -> str:
        return str(value or "UNKNOWN").strip().upper()

    @staticmethod
    def _normalize_symbol(value: Any) -> str:
        return str(value or "").strip().upper()

    @classmethod
    def _normalize_side(cls, value: Any) -> str:
        side = str(value or "").strip().upper()
        if side in {"BUY", "LONG"}:
            return "LONG"
        if side in {"SELL", "SHORT"}:
            return "SHORT"
        return side or "UNKNOWN"

    @classmethod
    def _direction_group(cls, side: str) -> str:
        return cls._normalize_side(side)

    @staticmethod
    def _to_float(value: Any, default: float) -> float:
        try:
            if value is None:
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    @classmethod
    def _optional_float(cls, value: Any) -> float | None:
        if value is None:
            return None
        return cls._to_float(value, 0.0)

    @staticmethod
    def _to_int(value: Any, default: int) -> int:
        try:
            if value is None:
                return default
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _clamp01(value: float) -> float:
        if value < 0.0:
            return 0.0
        if value > 1.0:
            return 1.0
        return value

    @staticmethod
    def _coerce_timestamp(value: datetime | str | None) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc)
        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return None
            if raw.endswith("Z"):
                raw = f"{raw[:-1]}+00:00"
            try:
                parsed = datetime.fromisoformat(raw)
            except ValueError:
                return None
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        return None
