from __future__ import annotations

import json
import os
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4


class TraceBus:
    """Simple JSONL + console trace utility."""

    def __init__(self, log_dir: str | None = None) -> None:
        resolved_dir = log_dir or os.getenv("TRACE_LOG_DIR", "logs")
        self.log_dir = Path(resolved_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def trace_event(
        self,
        stage: str,
        payload: dict[str, Any],
        *,
        cycle_id: str,
        run_mode: str,
        strategy: str,
        summary: str | None = None,
    ) -> dict[str, Any]:
        timestamp = datetime.now(timezone.utc).isoformat()
        component = payload.get("component", stage)
        action = payload.get("action", stage)
        decision = payload.get("decision") or payload.get("action") or "UNSPECIFIED"
        reason_code = payload.get("reason_code") or payload.get("reason") or "UNSPECIFIED"
        record = {
            "event_id": str(uuid4()),
            "timestamp": timestamp,
            "stage": stage,
            "component": component,
            "action": action,
            "entity_id": self._extract_entity_id(payload),
            "decision": decision,
            "reason_code": reason_code,
            "cycle_id": cycle_id,
            "run_mode": run_mode,
            "strategy": strategy,
            "metadata": self._normalize(payload),
        }
        log_path = self._log_path_for_date(timestamp)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")

        console_summary = summary or self._compact_summary(stage, payload)
        print(
            "[TRACE] "
            f"stage={stage} cycle_id={cycle_id} run_mode={run_mode} "
            f"strategy={strategy} {console_summary}"
        )
        return record

    def _log_path_for_date(self, timestamp: str) -> Path:
        date_key = timestamp[:10].replace("-", "")
        return self.log_dir / f"trace_{date_key}.jsonl"

    def _compact_summary(self, stage: str, payload: dict[str, Any]) -> str:
        if stage == "UNIVERSE":
            symbols = [entry.get("symbol") for entry in payload.get("universe", [])]
            return f"top_n={len(symbols)} symbols={self._cap_list(symbols, 5)}"
        if stage == "WATCHLIST":
            symbols = payload.get("watchlist_symbols", [])
            return f"watchlist={len(symbols)} symbols={self._cap_list(symbols, 5)}"
        if stage == "FOCUS":
            symbols = [entry.get("symbol") for entry in payload.get("focus", [])]
            return f"focus={len(symbols)} symbols={self._cap_list(symbols, 5)}"
        if stage == "ACTION":
            action = payload.get("action")
            orders = payload.get("orders", [])
            return f"action={action} orders={len(orders)}"
        if stage == "HALT":
            return (
                f"reason_code={payload.get('reason_code')} "
                f"message={payload.get('message')}"
            )
        return ""

    def _cap_list(self, items: Iterable[Any], limit: int) -> list[Any]:
        collected = list(items)
        sliced = collected[:limit]
        if len(collected) > limit:
            return sliced + ["..."]
        return sliced

    def _normalize(self, payload: Any) -> Any:
        if is_dataclass(payload):
            return asdict(payload)
        if isinstance(payload, dict):
            return {key: self._normalize(value) for key, value in payload.items()}
        if isinstance(payload, list):
            return [self._normalize(item) for item in payload]
        if isinstance(payload, tuple):
            return [self._normalize(item) for item in payload]
        return payload

    @staticmethod
    def _extract_entity_id(payload: dict[str, Any]) -> Any:
        for key in (
            "entity_id",
            "symbol",
            "client_order_id",
            "order_id",
            "trade_id",
            "position_id",
            "scanner_id",
        ):
            if key in payload:
                return payload.get(key)
        return None
