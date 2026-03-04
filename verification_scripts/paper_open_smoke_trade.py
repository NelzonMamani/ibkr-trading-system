#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.config.config_resolver import get_config
from src.config.runtime_config import (
    RunMode,
    get_execution_enabled,
    get_ibkr_ack_timeout_seconds,
    get_ibkr_client_id_order_submit,
    get_ibkr_default_currency,
    get_ibkr_default_exchange,
    get_ibkr_host,
    get_ibkr_kill_switch,
    get_ibkr_live_port,
    get_ibkr_market_data_type,
    get_ibkr_max_orders_per_run,
    get_ibkr_order_submission_enabled,
    get_ibkr_order_translation_enabled,
    get_ibkr_paper_host,
    get_ibkr_paper_only_enforced,
    get_ibkr_paper_port,
    get_ibkr_port,
    get_ibkr_readonly_enabled,
    get_ibkr_snapshot_timeout_seconds,
    get_run_mode,
)
from src.core.active_trade_registry import ActiveTradeRegistry
from src.core.event_collector import EventCollector
from src.core.stop_controller import StopController
from src.risk.risk_engine import RiskEngine
from src.scanner.scanner_runner import run_scanner_cycle
from src.strategies.long_horizon_value.strategy import LongHorizonValueStrategy
from src.strategies.mean_reversion.strategy import MeanReversionStrategy
from src.strategies.ross_momentum_strategy_v1 import RossMomentumStrategyV1
from src.strategies.statistical_intraday_momentum.strategy import StatisticalIntradayMomentum
from src.strategy.strategy_runner import StrategyRunner


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ts() -> str:
    return _now().strftime("%Y%m%dT%H%M%SZ")


def _safe_json(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, dict):
        return {str(k): _safe_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_safe_json(v) for v in value]
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            return str(value)
    if hasattr(value, "__dict__"):
        return _safe_json(vars(value))
    return value


def _write_text(path: Path, text: str) -> None:
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def _abort(message: str, preflight_lines: list[str], evidence_dir: Path, payload: dict[str, Any]) -> None:
    payload["status"] = "FAIL"
    payload["failure_reason"] = message
    _write_text(evidence_dir / "preflight.md", "\n".join(preflight_lines))
    _write_text(evidence_dir / "summary.md", f"# PAPER Open Smoke Trade Summary\n\n- Status: **FAIL**\n- Reason: {message}\n")
    _write_text(evidence_dir / "intents.md", "# Intents\n\nNot reached due to preflight failure.")
    _write_text(evidence_dir / "order_submission.md", "# Order Submission\n\nNot reached due to preflight failure.")
    (evidence_dir / "payload.json").write_text(json.dumps(_safe_json(payload), indent=2) + "\n", encoding="utf-8")
    print(f"[FAIL] {message}")
    print(f"[EVIDENCE] {evidence_dir}")
    raise SystemExit(1)


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    evidence_dir = repo_root / "TRADING_OS_MASTER_CATALOGUE" / "AUDIT_EVIDENCE" / "paper_open_smoke_trade" / _ts()
    evidence_dir.mkdir(parents=True, exist_ok=True)

    run_mode = get_run_mode()
    execution_enabled = get_execution_enabled()
    ibkr_host = get_ibkr_host()
    ibkr_port = get_ibkr_port()
    paper_host = get_ibkr_paper_host()
    paper_port = get_ibkr_paper_port()
    live_port = get_ibkr_live_port()
    readonly = get_ibkr_readonly_enabled(default=False)
    translation_enabled = get_ibkr_order_translation_enabled()
    submission_enabled = get_ibkr_order_submission_enabled(default=False)
    paper_only_enforced = get_ibkr_paper_only_enforced()
    kill_switch = get_ibkr_kill_switch()

    preflight = {
        "timestamp_utc": _now().isoformat(),
        "run_mode": run_mode.value,
        "execution_enabled": execution_enabled,
        "ibkr_host": ibkr_host,
        "ibkr_port": ibkr_port,
        "ibkr_paper_host": paper_host,
        "ibkr_paper_port": paper_port,
        "ibkr_live_port": live_port,
        "ibkr_readonly_enabled": readonly,
        "ibkr_order_translation_enabled": translation_enabled,
        "ibkr_order_submission_enabled": submission_enabled,
        "ibkr_paper_only_enforced": paper_only_enforced,
        "ibkr_kill_switch": kill_switch,
        "account": str(__import__("os").environ.get("IBKR_ACCOUNT", "UNKNOWN")),
        "account_type": str(__import__("os").environ.get("IBKR_ACCOUNT_TYPE", "UNKNOWN")),
    }
    payload: dict[str, Any] = {"preflight": preflight, "evidence_dir": str(evidence_dir.relative_to(repo_root))}
    lines = [
        "# Preflight",
        "",
        f"- timestamp_utc: {preflight['timestamp_utc']}",
        f"- run_mode: {run_mode.value}",
        f"- execution_enabled: {execution_enabled}",
        f"- broker: IBKR socket API",
        f"- host: {paper_host}",
        f"- paper_port: {paper_port}",
        f"- configured_live_port: {live_port}",
        f"- global_ibkr_port: {ibkr_port}",
        f"- order_translation_enabled: {translation_enabled}",
        f"- order_submission_enabled: {submission_enabled}",
        f"- read_only_enabled: {readonly}",
        f"- kill_switch: {kill_switch}",
        f"- account_type: {preflight['account_type']}",
        f"- account: {preflight['account']}",
    ]

    print("PAPER OPEN SMOKE TRADE — PREFLIGHT")
    for line in lines[2:]:
        print(line.replace("- ", "  "))

    if run_mode != RunMode.PAPER:
        _abort("RUN_MODE must be PAPER.", lines, evidence_dir, payload)
    if not execution_enabled:
        _abort("EXECUTION_ENABLED must be true for this smoke trade.", lines, evidence_dir, payload)
    if paper_port != 7497:
        _abort(f"IBKR_PAPER_PORT must be 7497 for this script (found {paper_port}).", lines, evidence_dir, payload)
    if ibkr_port == 7496 or paper_port == 7496:
        _abort("Detected LIVE socket port 7496; refusing to run in smoke PAPER command.", lines, evidence_dir, payload)
    if not translation_enabled:
        _abort("IBKR_ORDER_TRANSLATION_ENABLED must be true.", lines, evidence_dir, payload)
    if not submission_enabled:
        _abort("IBKR_ORDER_SUBMISSION_ENABLED must be true for real PAPER brokerage submission.", lines, evidence_dir, payload)
    if readonly:
        _abort("IBKR_READONLY_ENABLED must be false for order submission.", lines, evidence_dir, payload)
    if kill_switch:
        _abort("IBKR_KILL_SWITCH is engaged.", lines, evidence_dir, payload)
    if get_ibkr_max_orders_per_run() != 1:
        _abort("IBKR_MAX_ORDERS_PER_RUN must be exactly 1.", lines, evidence_dir, payload)

    _write_text(evidence_dir / "preflight.md", "\n".join(lines))

    scanner_result = run_scanner_cycle(mode="integrated")
    watchlist = list(scanner_result.get("watchlist_rows") or [])
    if not watchlist:
        synthetic_symbols = ["AAPL", "MSFT", "SPY"]
        watchlist = [{"symbol": symbol} for symbol in synthetic_symbols]

    strategy_runner = StrategyRunner(
        strategies=[
            RossMomentumStrategyV1(),
            StatisticalIntradayMomentum(),
            MeanReversionStrategy(),
            LongHorizonValueStrategy(),
        ]
    )
    timestamp_utc = _now().isoformat()
    strategy_runner.receive_watchlist_snapshot(
        watchlist_symbols=[getattr(row, "symbol", row.get("symbol")) for row in watchlist if getattr(row, "symbol", row.get("symbol"))],
        snapshots={},
        session_label="OPENING_0_30",
        timestamp_utc=timestamp_utc,
    )
    intents = strategy_runner.process(
        strategy_key="paper_open_smoke_trade",
        watchlist=watchlist,
        snapshots={},
        session_label="OPENING_0_30",
        timestamp_utc=timestamp_utc,
        mode=RunMode.PAPER,
        session_phase="OPENING_0_30",
    )

    risk_engine = RiskEngine(
        trade_registry=ActiveTradeRegistry(),
        event_collector=EventCollector(),
        stop_controller=StopController(),
    )
    admitted: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    all_intents: list[dict[str, Any]] = []
    for idx, intent in enumerate(intents):
        if not getattr(intent, "decision_id", None):
            setattr(intent, "decision_id", f"paper-open-smoke-{idx}-{uuid4().hex[:8]}")
        decision = risk_engine.evaluate_trade_intent(intent)
        row = {
            "symbol": intent.symbol,
            "strategy_name": intent.strategy_name,
            "direction": intent.direction,
            "confidence": intent.confidence,
            "decision_id": getattr(intent, "decision_id", None),
            "allowed": decision.allowed,
            "risk_reasons": list(decision.risk_reasons or []),
            "rationale": decision.rationale,
        }
        all_intents.append(row)
        if decision.allowed:
            admitted.append(row)
        else:
            blocked.append(row)

    intents_md = [
        "# Intents and Admission Gate",
        "",
        f"- intents_emitted: {len(intents)}",
        f"- admitted: {len(admitted)}",
        f"- blocked: {len(blocked)}",
        "",
        "## Intents",
        json.dumps(all_intents, indent=2),
    ]
    _write_text(evidence_dir / "intents.md", "\n".join(intents_md))
    payload["scanner"] = {
        "provider": scanner_result.get("diagnostics", {}).get("provider_source", "UNKNOWN"),
        "watchlist_count": len(watchlist),
        "watchlist_symbols": [getattr(row, "symbol", row.get("symbol")) for row in watchlist],
    }
    payload["intents"] = {"emitted": all_intents, "admitted": admitted, "blocked": blocked}

    if not admitted:
        _write_text(
            evidence_dir / "order_submission.md",
            "# Order Submission\n\nNo admitted intents. No order submission attempted.",
        )
        _write_text(
            evidence_dir / "summary.md",
            "# PAPER Open Smoke Trade Summary\n\n- Status: **FAIL**\n- Reason: No admitted intents after admission gate.\n",
        )
        payload["status"] = "FAIL"
        payload["failure_reason"] = "No admitted intents"
        (evidence_dir / "payload.json").write_text(json.dumps(_safe_json(payload), indent=2) + "\n", encoding="utf-8")
        print("[FAIL] No admitted intents. See intents.md for gate reasons.")
        print(f"[EVIDENCE] {evidence_dir}")
        return 1

    try:
        from src.adapters.brokers.ibkr.ibkr_client import IbkrClient
        from src.adapters.brokers.ibkr.ibkr_order_submitter import IbkrOrderSubmitter, OrderSubmissionSettings
        from src.adapters.brokers.ibkr.ibkr_order_translator import IbkrOrderTranslator
        from src.adapters.brokers.ibkr.submission_guard import SubmissionGuard
        from src.domain.models.internal_order import InternalOrder
    except ModuleNotFoundError as exc:
        _write_text(evidence_dir / "order_submission.md", f"# Order Submission\n\nDependency missing: {exc}")
        _write_text(evidence_dir / "summary.md", "# PAPER Open Smoke Trade Summary\n\n- Status: **FAIL**\n- Reason: Missing broker dependency (ibapi).\n")
        payload["status"] = "FAIL"
        payload["failure_reason"] = f"Missing dependency: {exc}"
        (evidence_dir / "payload.json").write_text(json.dumps(_safe_json(payload), indent=2) + "\n", encoding="utf-8")
        print(f"[FAIL] Missing dependency: {exc}")
        print(f"[EVIDENCE] {evidence_dir}")
        return 1

    chosen = admitted[0]
    direction = "SHORT" if str(chosen.get("direction", "")).upper() == "SHORT" else "LONG"
    internal_order = InternalOrder(
        client_order_id=f"paper-open-smoke-{uuid4().hex[:12]}",
        symbol=str(chosen["symbol"]).upper(),
        direction=direction,
        quantity=1,
        order_type="MKT",
        limit_price=None,
        time_in_force="DAY",
        strategy_name=str(chosen.get("strategy_name") or "UNKNOWN"),
        trader_type="SMOKE",
    )

    translator = IbkrOrderTranslator(
        order_translation_enabled=True,
        default_exchange=get_ibkr_default_exchange(),
        default_currency=get_ibkr_default_currency(),
    )
    guard = SubmissionGuard(max_orders_per_run=1, persist_path=str(evidence_dir / "submission_guard.json"))
    event_bus = EventCollector()
    ibkr_client = IbkrClient(
        host=paper_host,
        port=paper_port,
        client_id=get_ibkr_client_id_order_submit(),
        snapshot_timeout_seconds=get_ibkr_snapshot_timeout_seconds(),
        market_data_type=get_ibkr_market_data_type(),
        readonly_enabled=True,
    )
    settings = OrderSubmissionSettings(
        run_mode=RunMode.PAPER,
        order_submission_enabled=True,
        kill_switch=False,
        max_orders_per_run=1,
        paper_only_enforced=paper_only_enforced,
        paper_host=paper_host,
        paper_port=paper_port,
        live_port=live_port,
        submit_only_symbol=None,
        ack_timeout_seconds=get_ibkr_ack_timeout_seconds(),
        client_id=get_ibkr_client_id_order_submit(),
        submit_only_order_type="MKT",
        allow_shorting=False,
    )
    submitter = IbkrOrderSubmitter(
        ibkr_client=ibkr_client,
        translator=translator,
        event_bus=event_bus,
        config=settings,
        guard=guard,
    )

    result = submitter.submit_once(internal_order)
    order_payload = {
        "order_request": _safe_json(internal_order),
        "submission_result": _safe_json(result),
    }
    payload["order_submission"] = order_payload

    trusted_ip_hint = None
    status_upper = str(result.status).upper()
    if status_upper in {"FAILED", "TIMED_OUT"}:
        error_text = str(result.error or "")
        if any(token in error_text.lower() for token in ["timeout", "502", "1100", "connection", "refused", "not connected"]):
            trusted_ip_hint = (
                "Connection failed before/at handshake. Verify TWS/IB Gateway PAPER is running on 7497, "
                "API is enabled, and trusted IP includes this host (or localhost)."
            )

    order_lines = [
        "# Order Submission",
        "",
        f"- submitted_symbol: {internal_order.symbol}",
        f"- quantity: {internal_order.quantity}",
        f"- order_type: {internal_order.order_type}",
        f"- tif: {internal_order.time_in_force}",
        f"- status: {result.status}",
        f"- ibkr_order_id: {result.ibkr_order_id}",
        f"- error: {result.error}",
    ]
    if trusted_ip_hint:
        order_lines.append(f"- trusted_ip_or_prompt_hint: {trusted_ip_hint}")
    _write_text(evidence_dir / "order_submission.md", "\n".join(order_lines))

    passed = status_upper in {"ACKED", "SUBMITTED", "FILLED", "PARTIALLY_FILLED"}
    if result.filled_quantity is not None and int(result.filled_quantity) > 0:
        passed = True

    summary = [
        "# PAPER Open Smoke Trade Summary",
        "",
        f"- Status: **{'PASS' if passed else 'FAIL'}**",
        f"- Evidence dir: `{evidence_dir}`",
        f"- Intents emitted: {len(intents)}",
        f"- Intents admitted: {len(admitted)}",
        f"- Submitted symbol: {internal_order.symbol}",
        f"- Broker status: {result.status}",
    ]
    if trusted_ip_hint:
        summary.append(f"- Next action: {trusted_ip_hint}")
    _write_text(evidence_dir / "summary.md", "\n".join(summary))

    payload["status"] = "PASS" if passed else "FAIL"
    payload["trusted_ip_hint"] = trusted_ip_hint
    (evidence_dir / "payload.json").write_text(json.dumps(_safe_json(payload), indent=2) + "\n", encoding="utf-8")

    print(f"[RESULT] status={payload['status']} order_status={result.status} symbol={internal_order.symbol}")
    print(f"[EVIDENCE] {evidence_dir}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
