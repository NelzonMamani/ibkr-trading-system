from __future__ import annotations

from datetime import datetime, timezone
import json
import threading
from typing import Any, Mapping

IBKR_MARKET_DATA_ERROR_CODES = {10089, 10167}
MARKET_DATA_REQUEST_TYPES = {"MARKET_DATA", "MARKET_SNAPSHOT", "SCANNER_DATA"}
MARKET_DATA_ERROR_SIGNATURES = (
    "additional subscription",
    "not subscribed",
    "delayed market data",
    "displaying delayed",
)

_EVENTS: list[dict[str, Any]] = []
_SEEN: set[str] = set()
_LOCK = threading.Lock()
_INSTALLED = False


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "value"):
        return _json_safe(getattr(value, "value"))
    if hasattr(value, "__dict__"):
        return _json_safe(vars(value))
    return str(value)


def _stable_key(event: Mapping[str, Any]) -> str:
    comparable = {key: value for key, value in event.items() if key != "timestamp"}
    return json.dumps(_json_safe(comparable), sort_keys=True, default=str, separators=(",", ":"))


def _coerce_code(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        try:
            parsed = int(float(str(value).strip()))
        except (TypeError, ValueError):
            return None
    return parsed


def _coerce_req_id(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _is_market_data_error(code: int | None, message: str, request_type: str | None = None) -> bool:
    if request_type in MARKET_DATA_REQUEST_TYPES:
        return True
    if code in IBKR_MARKET_DATA_ERROR_CODES:
        return True
    lowered = message.lower()
    return any(signature in lowered for signature in MARKET_DATA_ERROR_SIGNATURES)


def _first_nonempty(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def _contract_context(contract: Any) -> dict[str, Any]:
    if contract is None:
        return {}
    return {
        "symbol": _first_nonempty(getattr(contract, "symbol", None), getattr(contract, "localSymbol", None)),
        "con_id": getattr(contract, "conId", None),
        "exchange": getattr(contract, "exchange", None),
        "primary_exchange": getattr(contract, "primaryExchange", None),
    }


def _client_request_context(client: Any, req_id: int | None) -> dict[str, Any]:
    if req_id is None:
        return {}
    context: dict[str, Any] = {}
    request_type_by_req_id = getattr(client, "_request_type_by_req_id", {}) or {}
    request_type = request_type_by_req_id.get(req_id)
    if request_type:
        context["request_type"] = request_type
    ticker = (getattr(client, "_ticker_by_req_id", {}) or {}).get(req_id)
    contract = getattr(ticker, "contract", None)
    context.update({key: value for key, value in _contract_context(contract).items() if value is not None})
    market_data_type = getattr(client, "market_data_type", None)
    if market_data_type:
        context["market_data_type"] = str(market_data_type).upper()
    return context


def _add_event(event: Mapping[str, Any]) -> None:
    normalized = {key: _json_safe(value) for key, value in event.items() if value is not None}
    key = _stable_key(normalized)
    with _LOCK:
        if key in _SEEN:
            return
        _SEEN.add(key)
        _EVENTS.append(dict(normalized))


def record_runtime_ibkr_market_data_error_event(
    *,
    code: Any,
    message: Any,
    req_id: Any = None,
    symbol: Any = None,
    con_id: Any = None,
    exchange: Any = None,
    primary_exchange: Any = None,
    market_data_type: Any = None,
    attempt_label: Any = None,
    source: str = "IBKR_ERROR_CALLBACK",
    raw_event: Mapping[str, Any] | None = None,
) -> None:
    parsed_code = _coerce_code(code)
    message_text = str(message or "").strip()
    parsed_req_id = _coerce_req_id(req_id)
    if not _is_market_data_error(parsed_code, message_text):
        return
    event = {
        "code": parsed_code,
        "message": message_text,
        "req_id": parsed_req_id,
        "ticker_id": parsed_req_id,
        "callback_id": parsed_req_id,
        "symbol": str(symbol or "").strip().upper(),
        "con_id": con_id,
        "exchange": exchange,
        "primary_exchange": primary_exchange,
        "market_data_type": str(market_data_type).upper() if market_data_type else None,
        "attempt_label": attempt_label,
        "timestamp": _utc_now_iso(),
        "source": source,
        "raw_event": raw_event or {},
    }
    _add_event(event)


def record_ibkr_client_market_data_error(
    client: Any,
    req_id: Any,
    error_code: Any,
    error_message: Any,
    *,
    attempt_label: Any = None,
) -> None:
    parsed_req_id = _coerce_req_id(req_id)
    message_text = str(error_message or "").strip()
    request_context = _client_request_context(client, parsed_req_id)
    request_type = request_context.get("request_type")
    parsed_code = _coerce_code(error_code)
    if not _is_market_data_error(parsed_code, message_text, str(request_type) if request_type else None):
        return
    record_runtime_ibkr_market_data_error_event(
        code=parsed_code,
        message=message_text,
        req_id=parsed_req_id,
        symbol=request_context.get("symbol"),
        con_id=request_context.get("con_id"),
        exchange=request_context.get("exchange"),
        primary_exchange=request_context.get("primary_exchange"),
        market_data_type=request_context.get("market_data_type"),
        attempt_label=attempt_label,
        source="IBKR_GENERIC_ERROR_CALLBACK_MARKET_DATA",
        raw_event={
            "callback": "IbkrClient.error",
            "reqId": parsed_req_id,
            "errorCode": parsed_code,
            "errorString": message_text,
            "request_type": request_type,
            "legacy_log_labels": ["[ORDER][ERROR]", "[IBKR][ORDER_ERROR]"],
        },
    )


def record_market_data_client_error(
    client: Any,
    req_id: Any,
    error_code: Any,
    error_message: Any,
    *,
    contract: Any = None,
    attempt_label: Any = None,
) -> None:
    context = _contract_context(contract)
    record_runtime_ibkr_market_data_error_event(
        code=error_code,
        message=error_message,
        req_id=req_id,
        symbol=context.get("symbol"),
        con_id=context.get("con_id"),
        exchange=context.get("exchange"),
        primary_exchange=context.get("primary_exchange"),
        market_data_type=getattr(client, "market_data_type", None),
        attempt_label=attempt_label,
        source="IB_INSYNC_ERROR_EVENT_MARKET_DATA",
        raw_event={
            "callback": "MarketDataClient._on_ib_error",
            "reqId": _coerce_req_id(req_id),
            "errorCode": _coerce_code(error_code),
            "errorString": str(error_message or "").strip(),
        },
    )


def get_runtime_ibkr_market_data_error_events() -> list[dict[str, Any]]:
    with _LOCK:
        return [dict(event) for event in _EVENTS]


def reset_runtime_ibkr_market_data_error_events() -> None:
    with _LOCK:
        _EVENTS.clear()
        _SEEN.clear()


def install_runtime_ibkr_market_data_error_capture() -> bool:
    global _INSTALLED
    if _INSTALLED:
        return True
    installed = False

    try:
        from src.adapters.brokers.ibkr.ibkr_client import IbkrClient

        original_error = IbkrClient.error
        if not getattr(original_error, "_pr1049_market_data_capture", False):

            def captured_error(self, reqId, errorCode, errorString, *args, **kwargs):
                record_ibkr_client_market_data_error(self, reqId, errorCode, errorString)
                return original_error(self, reqId, errorCode, errorString, *args, **kwargs)

            captured_error._pr1049_market_data_capture = True  # type: ignore[attr-defined]
            captured_error._pr1049_original = original_error  # type: ignore[attr-defined]
            IbkrClient.error = captured_error  # type: ignore[method-assign]
            installed = True
        else:
            installed = True
    except Exception:
        pass

    try:
        from src.ibkr.market_data_client import MarketDataClient

        original_on_error = MarketDataClient._on_ib_error
        if not getattr(original_on_error, "_pr1049_market_data_capture", False):

            def captured_on_ib_error(self, req_id, error_code, error_string, contract=None):
                record_market_data_client_error(
                    self,
                    req_id,
                    error_code,
                    error_string,
                    contract=contract,
                )
                return original_on_error(self, req_id, error_code, error_string, contract=contract)

            captured_on_ib_error._pr1049_market_data_capture = True  # type: ignore[attr-defined]
            captured_on_ib_error._pr1049_original = original_on_error  # type: ignore[attr-defined]
            MarketDataClient._on_ib_error = captured_on_ib_error  # type: ignore[method-assign]
            installed = True
        else:
            installed = True
    except Exception:
        pass

    _INSTALLED = installed
    return installed
