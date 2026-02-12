from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

DATA_SOURCE_REGISTRY: list[dict[str, str]] = [
    {
        "source_id": "IBKR_SNAPSHOT",
        "source_class": "PRIMARY",
        "expected_latency": "REALTIME",
        "availability_constraints": "market_state_or_subscription_dependent",
    },
    {
        "source_id": "IBKR_STREAM",
        "source_class": "PRIMARY",
        "expected_latency": "REALTIME",
        "availability_constraints": "subscription_required",
    },
    {
        "source_id": "HIST_BARS",
        "source_class": "DERIVED",
        "expected_latency": "DELAYED",
        "availability_constraints": "provider_lookback_window",
    },
    {
        "source_id": "CACHE_DB",
        "source_class": "CACHED",
        "expected_latency": "UNKNOWN",
        "availability_constraints": "cache_ttl_and_population",
    },
    {
        "source_id": "FALLBACK_PROVIDER",
        "source_class": "FALLBACK",
        "expected_latency": "UNKNOWN",
        "availability_constraints": "network_or_provider_availability",
    },
    {
        "source_id": "SYNTHETIC",
        "source_class": "SYNTHETIC",
        "expected_latency": "UNKNOWN",
        "availability_constraints": "simulation_generation_only",
    },
]

MODE_TRUTH_MATRIX: dict[str, dict[str, Any]] = {
    "SIM": {
        "expected_sources": ["HIST_BARS", "CACHE_DB", "SYNTHETIC"],
        "expected_latencies": ["DELAYED", "UNKNOWN"],
        "allowed_fallbacks": ["FALLBACK_PROVIDER", "SYNTHETIC"],
    },
    "PAPER": {
        "expected_sources": ["IBKR_SNAPSHOT", "IBKR_STREAM", "CACHE_DB", "HIST_BARS"],
        "expected_latencies": ["REALTIME", "DELAYED", "UNKNOWN"],
        "allowed_fallbacks": ["FALLBACK_PROVIDER", "CACHE_DB"],
    },
    "READ_ONLY": {
        "expected_sources": ["IBKR_STREAM", "IBKR_SNAPSHOT", "CACHE_DB"],
        "expected_latencies": ["REALTIME", "DELAYED", "UNKNOWN"],
        "allowed_fallbacks": ["FALLBACK_PROVIDER", "CACHE_DB"],
    },
    "LIVE": {
        "expected_sources": ["IBKR_STREAM", "IBKR_SNAPSHOT", "CACHE_DB"],
        "expected_latencies": ["REALTIME", "DELAYED", "UNKNOWN"],
        "allowed_fallbacks": ["FALLBACK_PROVIDER", "CACHE_DB"],
    },
}


@dataclass(frozen=True)
class LedgerVerificationResult:
    valid: bool
    violations: list[str]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _compute_hash(prev_hash: str, payload: dict[str, Any]) -> str:
    digest = hashlib.sha256()
    digest.update(prev_hash.encode("utf-8"))
    digest.update(b"|")
    digest.update(_canonical_json(payload).encode("utf-8"))
    return digest.hexdigest()


class DataProvenanceLedger:
    """Append-only JSONL ledger with deterministic per-entry hash chaining."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append_event(self, event: dict[str, Any]) -> dict[str, Any]:
        full_event = self._normalize_event(event)
        prev_hash = self._last_hash()
        payload = {k: v for k, v in full_event.items() if k not in {"prev_event_hash", "event_hash"}}
        full_event["prev_event_hash"] = prev_hash
        full_event["event_hash"] = _compute_hash(prev_hash, payload)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(_canonical_json(full_event) + "\n")
        return full_event

    def append_hydration_event(
        self,
        *,
        symbol: str,
        mode: str,
        session_state: str,
        hydration_state: str,
        datasets_requested: list[str],
        datasets_succeeded: list[str],
        datasets_failed: list[str],
        decision_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        freshness = "REALTIME" if hydration_state == "DATA_HYDRATION_READY" else "UNKNOWN"
        confidence = "HIGH" if hydration_state == "DATA_HYDRATION_READY" else "LOW"
        limitation = "" if confidence == "HIGH" else "hydration_partial_or_degraded"
        return self.append_event(
            {
                "symbol": symbol,
                "data_type": "DERIVED_METRIC",
                "timeframe_scope": "SESSION_LEVEL",
                "timeframe_resolution": "1M",
                "source_id": "CACHE_DB",
                "mode": mode,
                "session_state": session_state,
                "freshness_class": freshness,
                "confidence_level": confidence,
                "known_limitations": limitation,
                "linkage": {
                    "signal_ids": [],
                    "decision_ids": sorted(decision_ids or []),
                    "order_ids": [],
                    "parent_event_ids": [],
                },
                "control_plane": {
                    "event_name": hydration_state,
                    "datasets_requested": sorted(datasets_requested),
                    "datasets_succeeded": sorted(datasets_succeeded),
                    "datasets_failed": sorted(datasets_failed),
                },
            }
        )

    def query(self, *, symbol: str | None = None, mode: str | None = None, decision_id: str | None = None) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for event in self.read_all_events():
            if symbol and event.get("symbol") != symbol:
                continue
            if mode and event.get("mode") != mode:
                continue
            if decision_id and decision_id not in (event.get("linkage") or {}).get("decision_ids", []):
                continue
            rows.append(event)
        return rows

    def read_all_events(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
        return rows

    def verify(self) -> LedgerVerificationResult:
        violations: list[str] = []
        expected_prev = "GENESIS"
        seen_ids: set[str] = set()
        for index, event in enumerate(self.read_all_events(), start=1):
            event_id = event.get("event_id")
            if not isinstance(event_id, str) or not event_id:
                violations.append(f"row:{index}:missing_event_id")
            elif event_id in seen_ids:
                violations.append(f"row:{index}:duplicate_event_id:{event_id}")
            else:
                seen_ids.add(event_id)

            if event.get("prev_event_hash") != expected_prev:
                violations.append(f"row:{index}:broken_prev_hash")

            payload = {k: v for k, v in event.items() if k not in {"prev_event_hash", "event_hash"}}
            expected_hash = _compute_hash(expected_prev, payload)
            if event.get("event_hash") != expected_hash:
                violations.append(f"row:{index}:hash_mismatch")

            validation_error = _validate_provenance_event(event)
            if validation_error:
                violations.append(f"row:{index}:{validation_error}")

            expected_prev = event.get("event_hash") or ""

        return LedgerVerificationResult(valid=not violations, violations=sorted(violations))

    def _last_hash(self) -> str:
        events = self.read_all_events()
        if not events:
            return "GENESIS"
        return str(events[-1].get("event_hash") or "GENESIS")

    def _normalize_event(self, event: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(event)
        normalized.setdefault("event_id", str(uuid4()))
        timestamp = normalized.get("timestamp_observed") or utc_now_iso()
        normalized.setdefault("timestamp_observed", timestamp)
        normalized.setdefault("timestamp_used", timestamp)
        normalized.setdefault("checksum_or_fingerprint", "")
        linkage = dict(normalized.get("linkage") or {})
        linkage.setdefault("signal_ids", [])
        linkage.setdefault("decision_ids", [])
        linkage.setdefault("order_ids", [])
        linkage.setdefault("parent_event_ids", [])
        normalized["linkage"] = {
            "signal_ids": sorted(str(item) for item in linkage["signal_ids"]),
            "decision_ids": sorted(str(item) for item in linkage["decision_ids"]),
            "order_ids": sorted(str(item) for item in linkage["order_ids"]),
            "parent_event_ids": sorted(str(item) for item in linkage["parent_event_ids"]),
        }
        error = _validate_provenance_event(normalized)
        if error:
            raise ValueError(error)
        return normalized


def _validate_provenance_event(event: dict[str, Any]) -> str | None:
    required_fields = [
        "event_id",
        "symbol",
        "data_type",
        "timeframe_scope",
        "timeframe_resolution",
        "source_id",
        "mode",
        "session_state",
        "timestamp_observed",
        "timestamp_used",
        "freshness_class",
        "confidence_level",
        "known_limitations",
        "checksum_or_fingerprint",
        "linkage",
    ]
    missing = [field for field in required_fields if field not in event]
    if missing:
        return f"missing_required_fields:{','.join(sorted(missing))}"

    if event.get("confidence_level") != "HIGH" and not str(event.get("known_limitations") or "").strip():
        return "known_limitations_required_when_confidence_not_high"
    if event.get("freshness_class") != "REALTIME" and not str(event.get("known_limitations") or "").strip():
        return "known_limitations_required_when_freshness_not_realtime"

    linkage = event.get("linkage")
    if not isinstance(linkage, dict):
        return "linkage_must_be_object"
    for key in ("signal_ids", "decision_ids", "order_ids", "parent_event_ids"):
        value = linkage.get(key)
        if not isinstance(value, list):
            return f"linkage_{key}_must_be_list"

    return None
