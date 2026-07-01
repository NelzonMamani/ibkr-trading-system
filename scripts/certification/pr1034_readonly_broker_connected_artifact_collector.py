#!/usr/bin/env python
"""PR1034 READ_ONLY broker-connected artifact collector.

This operator tool can connect to IBKR only when explicitly requested with
--connect-ibkr-readonly and only after the READ_ONLY safety environment passes.
It does not submit, cancel, modify, stage, preview-submit, flatten, or reconcile
orders. It captures a broker connection/order-audit shell, writes PR1032-shaped
raw artifacts, and then delegates normalization/redaction/hashing to the PR1033
validator.

The collector is intentionally narrower than PAPER readiness: scanner, catalyst,
setup, risk, and storage artifacts produced here are marked as collector-only
placeholders unless they are supplied by a future full READ_ONLY strategy run.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = "PR1034.readonly_broker_connected_artifact_collector.v1"
PR1032_MANIFEST_PATH = Path(
    "docs/certification/PR1032_READ_ONLY_BROKER_RUNTIME_ARTIFACT_MANIFEST.example.json"
)
PR1032_RUNBOOK_PATH = Path(
    "docs/certification/PR1032_READ_ONLY_BROKER_CONNECTED_OPERATOR_RUNBOOK.md"
)
PR1033_SCRIPT_NAME = "pr1033_readonly_broker_artifact_capture.py"
FORBIDDEN_OPEN_ORDER_AUDIT_STATUSES = frozenset(
    {
        "OPEN_ORDER_REQUEST_FAILED",
        "OPEN_ORDER_READ_FAILED",
        "OPEN_ORDER_AUDIT_FAILED",
        "OPEN_ORDER_AUDIT_UNAVAILABLE",
        "ERROR",
        "FAILED",
        "UNKNOWN",
        "UNAVAILABLE",
    }
)
BROKER_SNAPSHOT_REQUIRED_FIELDS = (
    "provider_name",
    "connected",
    "host",
    "port",
    "client_id",
    "market_data_type",
    "account_id_redacted",
    "submitted_orders_count",
    "cancelled_orders_count",
    "modified_orders_count",
    "open_orders_before",
    "open_orders_after",
)


def _load_pr1033_validator():
    try:
        import pr1033_readonly_broker_artifact_capture as validator  # type: ignore

        return validator
    except ModuleNotFoundError:
        validator_path = Path(__file__).with_name(PR1033_SCRIPT_NAME)
        spec = importlib.util.spec_from_file_location("pr1033_validator", validator_path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"unable to load PR1033 validator: {validator_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module


pr1033 = _load_pr1033_validator()


class CollectorValidationError(RuntimeError):
    """Raised when PR1034 collection would be unsafe or incomplete."""


@dataclass(frozen=True)
class BrokerConnectionConfig:
    host: str
    port: int
    client_id: int
    timeout_seconds: float
    market_data_type: str


def ensure_asyncio_event_loop() -> None:
    """Create a current asyncio loop before importing ib_insync."""

    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())


def bootstrap_ib_insync_event_loop(util_module: Any | None = None) -> None:
    """Ensure an asyncio loop and optionally apply ib_insync's asyncio patch."""

    ensure_asyncio_event_loop()
    patch_asyncio = getattr(util_module, "patchAsyncio", None)
    if callable(patch_asyncio):
        try:
            patch_asyncio()
        except Exception as exc:
            raise CollectorValidationError("ib_insync event-loop bootstrap failed") from exc


def load_ib_insync_ib_after_bootstrap() -> Any:
    """Return ib_insync.IB only after asyncio and util bootstrap are complete."""

    ensure_asyncio_event_loop()
    try:
        from ib_insync import util
    except ImportError as exc:
        raise CollectorValidationError("ib_insync is required for broker connection") from exc
    bootstrap_ib_insync_event_loop(util)
    try:
        from ib_insync import IB
    except ImportError as exc:
        raise CollectorValidationError("ib_insync IB is required for broker connection") from exc
    return IB


def _disconnect_after_failed_connect(ib: Any) -> None:
    disconnect = getattr(ib, "disconnect", None)
    if not callable(disconnect):
        return
    try:
        disconnect()
    except Exception:
        # Preserve the original connect failure as the actionable abort reason.
        return


class IBInsyncReadOnlyProvider:
    """Small IBKR read-only adapter used only by operator-invoked CLI runs."""

    def __init__(self, config: BrokerConnectionConfig):
        self.config = config
        self._ib: Any | None = None

    def connect_readonly(self) -> None:
        IB = load_ib_insync_ib_after_bootstrap()
        ib = IB()
        try:
            ib.connect(
                self.config.host,
                self.config.port,
                clientId=self.config.client_id,
                timeout=self.config.timeout_seconds,
                readonly=True,
            )
        except TimeoutError as exc:
            _disconnect_after_failed_connect(ib)
            raise CollectorValidationError(
                "IBKR READ_ONLY connection timed out before broker audit could start"
            ) from exc
        except Exception as exc:
            _disconnect_after_failed_connect(ib)
            raise CollectorValidationError(
                "IBKR READ_ONLY connection failed before broker audit could start"
            ) from exc
        self._ib = ib

    def disconnect(self) -> None:
        if self._ib is not None and self._ib.isConnected():
            self._ib.disconnect()

    def _open_orders_snapshot(self) -> list[dict[str, Any]]:
        if self._ib is None:
            raise CollectorValidationError("IBKR provider is not connected for open-order audit")
        try:
            self._ib.reqOpenOrders()
        except Exception as exc:
            raise CollectorValidationError(
                "IBKR open-order request failed; aborting READ_ONLY capture"
            ) from exc
        try:
            open_orders = list(self._ib.openOrders())
        except Exception as exc:
            raise CollectorValidationError(
                "IBKR open-order read failed; aborting READ_ONLY capture"
            ) from exc
        rows: list[dict[str, Any]] = []
        for order in open_orders:
            rows.append(
                {
                    "order_id": str(getattr(order, "orderId", "")),
                    "action": str(getattr(order, "action", "")),
                    "order_type": str(getattr(order, "orderType", "")),
                    "total_quantity": str(getattr(order, "totalQuantity", "")),
                }
            )
        return rows

    def collect_snapshot(self) -> dict[str, Any]:
        if self._ib is None or not self._ib.isConnected():
            raise CollectorValidationError("IBKR provider is not connected")
        open_orders_before = self._open_orders_snapshot()
        open_orders_after = self._open_orders_snapshot()
        try:
            managed_accounts = list(self._ib.managedAccounts())
        except Exception as exc:
            raise CollectorValidationError(
                "IBKR managed-account read failed; aborting READ_ONLY capture"
            ) from exc
        return {
            "provider_name": "IB_INSYNC_READONLY",
            "connected": True,
            "host": self.config.host,
            "port": self.config.port,
            "client_id": self.config.client_id,
            "market_data_type": self.config.market_data_type,
            "account_id_redacted": "REDACTED" if managed_accounts else "NO_SECRET_DATA_PRESENT",
            "submitted_orders_count": 0,
            "cancelled_orders_count": 0,
            "modified_orders_count": 0,
            "open_orders_before": open_orders_before,
            "open_orders_after": open_orders_after,
        }


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _as_zero_int(snapshot: Mapping[str, Any], key: str) -> int:
    try:
        value = int(snapshot.get(key, 0))
    except (TypeError, ValueError) as exc:
        raise CollectorValidationError(f"{key} must be numeric zero") from exc
    if value != 0:
        raise CollectorValidationError(f"{key} must be zero")
    return value


def _as_positive_int(snapshot: Mapping[str, Any], key: str) -> int:
    try:
        value = int(snapshot.get(key, 0))
    except (TypeError, ValueError) as exc:
        raise CollectorValidationError(f"{key} must be a positive integer") from exc
    if value <= 0:
        raise CollectorValidationError(f"{key} must be a positive integer")
    return value


def _as_nonempty_string(snapshot: Mapping[str, Any], key: str) -> str:
    value = str(snapshot.get(key, "")).strip()
    if not value:
        raise CollectorValidationError(f"{key} must be present in broker snapshot")
    return value


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _require_open_order_rows(snapshot: Mapping[str, Any], key: str) -> list[Any]:
    rows = snapshot.get(key)
    if not isinstance(rows, list):
        raise CollectorValidationError(f"{key} must be a list")
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise CollectorValidationError(f"{key}[{index}] must be a mapping")
        status = str(row.get("status", "")).strip().upper()
        if (
            status in FORBIDDEN_OPEN_ORDER_AUDIT_STATUSES
            or status.endswith("_FAILED")
            or status.endswith("_ERROR")
        ):
            raise CollectorValidationError(
                f"{key}[{index}] contains open-order audit failure status: {status}"
            )
    return rows


def assert_broker_snapshot_safe(snapshot: Mapping[str, Any]) -> None:
    missing = [key for key in BROKER_SNAPSHOT_REQUIRED_FIELDS if key not in snapshot]
    if missing:
        raise CollectorValidationError(
            f"broker snapshot missing required field(s): {', '.join(missing)}"
        )
    if snapshot.get("connected") is not True:
        raise CollectorValidationError("broker snapshot must prove connected=True")
    _as_nonempty_string(snapshot, "provider_name")
    _as_nonempty_string(snapshot, "host")
    _as_positive_int(snapshot, "port")
    _as_positive_int(snapshot, "client_id")
    _as_nonempty_string(snapshot, "market_data_type")
    _as_nonempty_string(snapshot, "account_id_redacted")
    _as_zero_int(snapshot, "submitted_orders_count")
    _as_zero_int(snapshot, "cancelled_orders_count")
    _as_zero_int(snapshot, "modified_orders_count")
    before = _require_open_order_rows(snapshot, "open_orders_before")
    after = _require_open_order_rows(snapshot, "open_orders_after")
    if _stable_json(before) != _stable_json(after):
        raise CollectorValidationError("open order snapshot changed during READ_ONLY collection")


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def _safe_runtime_payload(runtime_env: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "RUN_MODE": "READ_ONLY",
        "RUN_MODE_EFFECTIVE": "READ_ONLY",
        "EXECUTION_ENABLED": False,
        "EXECUTION_ENABLED_EFFECTIVE": False,
        "EVENT_REPLAY_MODE": "OFF",
        "EVENT_REPLAY_MODE_EFFECTIVE": "OFF",
        "IBKR_API_WRITE_ALLOWED": False,
        "IBKR_ORDER_SUBMISSION_ENABLED": False,
        "FORCE_CLEAN_START": False,
        "collector_runtime_env": dict(runtime_env),
    }


def build_raw_artifacts(
    *,
    broker_snapshot: Mapping[str, Any],
    operator: str,
    collected_at: str,
    runtime_env: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    assert_broker_snapshot_safe(broker_snapshot)
    blockers = [
        "PR1034 collected broker connection and zero-order audit shell only.",
        "Scanner, catalyst, setup, risk, and storage artifacts still require a full READ_ONLY strategy observation.",
        "PAPER_READY remains NO.",
    ]
    return {
        "operator_runbook_acknowledgement": {
            "runbook_path": str(PR1032_RUNBOOK_PATH.as_posix()),
            "operator": operator,
            "acknowledged_at_utc": collected_at,
            "pre_run_checklist_status": "PASS",
            "abort_conditions_reviewed": True,
            "paper_ready": "NO",
            "collector_schema_version": SCHEMA_VERSION,
        },
        "runtime_config_snapshot": _safe_runtime_payload(runtime_env),
        "broker_connection_snapshot": {
            "connected": True,
            "host": str(broker_snapshot.get("host", "")),
            "port": int(broker_snapshot.get("port", 0)),
            "client_id": int(broker_snapshot.get("client_id", 0)),
            "market_data_type": str(broker_snapshot.get("market_data_type", "READ_ONLY")),
            "account_id_redacted": str(broker_snapshot.get("account_id_redacted", "REDACTED")),
            "provider_name": str(broker_snapshot.get("provider_name", "READ_ONLY_PROVIDER")),
            "readonly_connection": True,
            "collector_schema_version": SCHEMA_VERSION,
            "collected_at_utc": collected_at,
        },
        "scanner_cycle_artifact": {
            "provider_source": "PR1034_COLLECTOR_ONLY",
            "scanner_contract": {
                "contract_valid": False,
                "reason": "collector_does_not_run_strategy_scanner",
            },
            "top_n_symbols": [],
            "drop_ledger": {"PR1034": "collector_only_no_scanner_cycle"},
            "selection_spec": {"ranking_intent": "NOT_EVALUATED_BY_COLLECTOR"},
            "blockers": blockers,
        },
        "catalyst_news_artifact": {
            "news_source_mode": "NOT_COLLECTED_BY_PR1034_COLLECTOR",
            "news_asof": collected_at,
            "catalyst_status_by_symbol": {},
            "fresh_news_count": 0,
            "blockers": blockers,
        },
        "watchlist_focus_artifact": {
            "watchlist_k_symbols": [],
            "focus_m_symbols": [],
            "watchlist_rows": [],
            "focus_rows": [],
            "blockers": blockers,
        },
        "pattern_input_artifact": {
            "symbol": "NO_SYMBOL_COLLECTOR_ONLY",
            "timeframe_provenance": {},
            "data_quality_flags": ["PR1034_COLLECTOR_DID_NOT_CAPTURE_STRATEGY_MARKET_DATA"],
            "liquidity_context": {},
            "news_context": {},
            "blockers": blockers,
        },
        "setup_decision_artifact": {
            "detected_setups": [],
            "selected_setup": "NONE_COLLECTOR_ONLY",
            "entry_model": "NO_ENTRY_COLLECTOR_ONLY",
            "stop_model": "NO_STOP_COLLECTOR_ONLY",
            "target_model": "NO_TARGET_COLLECTOR_ONLY",
            "rationale_text": "PR1034 collector captured broker connection/order-audit shell only.",
            "decision_reason": "NO_STRATEGY_DECISION_COLLECTED",
            "blockers": blockers,
        },
        "risk_gate_artifact": {
            "risk_gate_called": False,
            "risk_approved": False,
            "risk_reason": "NO_STRATEGY_INTENT_COLLECTED",
            "risk_profile": "NONE",
            "blockers": blockers,
        },
        "execution_gate_artifact": {
            "execution_enabled": False,
            "order_submission_enabled": False,
            "api_write_allowed": False,
            "execution_path": "READ_ONLY_ORDER_PATH_DISABLED",
            "order_attempt_count": 0,
            "blockers": blockers,
        },
        "broker_order_audit": {
            "submitted_orders_count": 0,
            "cancelled_orders_count": 0,
            "modified_orders_count": 0,
            "open_orders_before": list(broker_snapshot.get("open_orders_before", [])),
            "open_orders_after": list(broker_snapshot.get("open_orders_after", [])),
            "collector_schema_version": SCHEMA_VERSION,
        },
        "analytics_storage_artifact": {
            "storage_write_count": 0,
            "storage_readback_count": 0,
            "trade_plan_records": [],
            "no_trade_records": [],
            "artifact_paths": [],
            "blockers": blockers,
        },
        "final_verdict": {
            "paper_ready": "NO",
            "paper_readiness_gate": "FAIL",
            "blockers": blockers,
            "operator_signature": operator,
        },
    }


def write_raw_artifacts(raw_output_dir: Path, artifacts: Mapping[str, Mapping[str, Any]]) -> None:
    for artifact_id in pr1033.REQUIRED_ARTIFACT_IDS:
        payload = artifacts.get(artifact_id)
        if payload is None:
            raise CollectorValidationError(f"missing PR1032 artifact payload: {artifact_id}")
        _write_json(raw_output_dir / f"{artifact_id}.json", payload)


def collect_with_provider(
    *,
    provider: Any,
    raw_output_dir: Path,
    validated_output_dir: Path,
    operator: str,
    env: Mapping[str, str] | None = None,
    template_path: Path = PR1032_MANIFEST_PATH,
    runbook_path: Path = PR1032_RUNBOOK_PATH,
    force: bool = False,
) -> dict[str, Any]:
    runtime_env = pr1033.assert_safe_runtime_environment(env or os.environ)
    if raw_output_dir.resolve() == validated_output_dir.resolve():
        raise CollectorValidationError("raw and validated output directories must differ")
    pr1033.assert_output_dir_ready(raw_output_dir, force=force)

    connected = False
    try:
        provider.connect_readonly()
        connected = True
        broker_snapshot = provider.collect_snapshot()
        if not isinstance(broker_snapshot, Mapping):
            raise CollectorValidationError("broker provider returned a non-mapping snapshot")
        collected_at = utc_now_iso()
        raw_artifacts = build_raw_artifacts(
            broker_snapshot=broker_snapshot,
            operator=operator,
            collected_at=collected_at,
            runtime_env=runtime_env,
        )
        write_raw_artifacts(raw_output_dir, raw_artifacts)
        collector_manifest = {
            "schema_version": SCHEMA_VERSION,
            "status": "RAW_ARTIFACTS_COLLECTED_PENDING_PR1033_VALIDATION",
            "paper_ready": "NO",
            "paper_readiness_gate": "FAIL",
            "operator": operator,
            "collected_at_utc": collected_at,
            "raw_output_dir": str(raw_output_dir.as_posix()),
            "validated_output_dir": str(validated_output_dir.as_posix()),
            "broker_provider": str(broker_snapshot.get("provider_name", "READ_ONLY_PROVIDER")),
            "order_mutation_allowed": False,
            "blockers": raw_artifacts["final_verdict"]["blockers"],
        }
        _write_json(raw_output_dir / "pr1034_collector_manifest.json", collector_manifest)
        return pr1033.capture_bundle(
            source_dir=raw_output_dir,
            output_dir=validated_output_dir,
            operator=operator,
            template_path=template_path,
            runbook_path=runbook_path,
            env=runtime_env,
            force=force,
        )
    finally:
        if connected and hasattr(provider, "disconnect"):
            provider.disconnect()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect a PR1034 READ_ONLY broker-connected artifact shell."
    )
    parser.add_argument("--connect-ibkr-readonly", action="store_true", help="Explicitly allow a READ_ONLY IBKR connection")
    parser.add_argument("--raw-output-dir", required=True, type=Path, help="Fresh directory for raw PR1032 artifacts")
    parser.add_argument("--validated-output-dir", required=True, type=Path, help="Fresh directory for PR1033 normalized artifacts")
    parser.add_argument("--operator", required=True, help="Operator name or initials")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=7497, type=int)
    parser.add_argument("--client-id", default=1034, type=int)
    parser.add_argument("--timeout-seconds", default=10.0, type=float)
    parser.add_argument("--market-data-type", default="IBKR_READ_ONLY")
    parser.add_argument("--manifest-template", default=PR1032_MANIFEST_PATH, type=Path)
    parser.add_argument("--runbook", default=PR1032_RUNBOOK_PATH, type=Path)
    parser.add_argument("--force", action="store_true", help="Replace non-empty output directories")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if not args.connect_ibkr_readonly:
            raise CollectorValidationError("--connect-ibkr-readonly is required before any broker connection")
        provider = IBInsyncReadOnlyProvider(
            BrokerConnectionConfig(
                host=args.host,
                port=args.port,
                client_id=args.client_id,
                timeout_seconds=args.timeout_seconds,
                market_data_type=args.market_data_type,
            )
        )
        manifest = collect_with_provider(
            provider=provider,
            raw_output_dir=args.raw_output_dir,
            validated_output_dir=args.validated_output_dir,
            operator=args.operator,
            template_path=args.manifest_template,
            runbook_path=args.runbook,
            force=args.force,
        )
    except (CollectorValidationError, pr1033.CaptureValidationError) as exc:
        print(f"[PR1034][ABORT] {exc}", file=sys.stderr)
        return 2
    print(
        "[PR1034][COLLECT] "
        f"status={manifest['status']} paper_ready={manifest['paper_ready']} "
        f"artifacts={len(manifest['artifacts'])} output={args.validated_output_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
