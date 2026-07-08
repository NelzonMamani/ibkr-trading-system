from __future__ import annotations

from collections import Counter
import json
import re
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = "PR1046.ibkr_market_data_diagnostic.v1"

MARKET_DATA_SUBSCRIPTION_REQUIRED = "MARKET_DATA_SUBSCRIPTION_REQUIRED"
MARKET_DATA_NOT_SUBSCRIBED = "MARKET_DATA_NOT_SUBSCRIBED"
DELAYED_DATA_AVAILABLE_BUT_UNUSABLE = "DELAYED_DATA_AVAILABLE_BUT_UNUSABLE"
SNAPSHOT_TIMEOUT = "SNAPSHOT_TIMEOUT"
SNAPSHOT_FIELDS_MISSING = "SNAPSHOT_FIELDS_MISSING"
MARKET_DATA_USABLE = "MARKET_DATA_USABLE"
MARKET_DATA_DIAGNOSTIC_UNKNOWN = "MARKET_DATA_DIAGNOSTIC_UNKNOWN"

MARKET_DATA_DIAGNOSTIC_CLASSIFICATIONS = (
    MARKET_DATA_SUBSCRIPTION_REQUIRED,
    MARKET_DATA_NOT_SUBSCRIBED,
    DELAYED_DATA_AVAILABLE_BUT_UNUSABLE,
    SNAPSHOT_TIMEOUT,
    SNAPSHOT_FIELDS_MISSING,
    MARKET_DATA_USABLE,
    MARKET_DATA_DIAGNOSTIC_UNKNOWN,
)

IBKR_MARKET_DATA_ERROR_CODES = (10089, 10167)
ERROR_CODE_RE = re.compile(r"\b(10089|10167)\b")

REQUIRED_QUOTE_FIELDS = ("last", "close", "volume", "bid", "ask")
QUOTE_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "last": ("last", "last_price", "price", "mark", "market_price"),
    "close": ("close", "previous_close", "prev_close", "prior_close"),
    "volume": ("volume", "day_volume", "snapshot_volume", "total_volume"),
    "bid": ("bid", "bid_price"),
    "ask": ("ask", "ask_price"),
}

CANDIDATE_ROW_KEYS = (
    "candidate_metrics",
    "candidates",
    "top_n",
    "top_n_rows",
    "symbols_rows",
    "watchlist_k",
    "watchlist_rows",
    "focus_m",
    "focus_rows",
)

ERROR_CODE_KEYS = (
    "code",
    "error_code",
    "ib_error_code",
    "ibkr_error_code",
    "errorCode",
    "error_id",
)
ERROR_MESSAGE_KEYS = (
    "message",
    "error_message",
    "ib_error_message",
    "ibkr_error_message",
    "msg",
    "text",
    "description",
)
SYMBOL_KEYS = ("symbol", "ticker", "local_symbol", "localSymbol", "contract_symbol")
SNAPSHOT_TIMEOUT_REASONS = {"DATA_QUALITY_FAIL_SNAPSHOT", "SNAPSHOT_TIMEOUT", "SNAPSHOT_TIMED_OUT"}


def _normalize_text(value: Any) -> str:
    if hasattr(value, "value"):
        value = getattr(value, "value")
    if value is None:
        return ""
    return str(value)


def _normalize_upper(value: Any) -> str:
    return _normalize_text(value).strip().upper()


def _get_value(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(key, default)
    return getattr(value, key, default)


def _safe_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        parsed = float(value)
        return parsed if parsed > 0.0 else None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = float(text.replace(",", ""))
    except ValueError:
        return None
    return parsed if parsed > 0.0 else None


def _stable_json(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    except TypeError:
        return str(value)


def _walk(value: Any):
    yield value
    if isinstance(value, Mapping):
        for key, item in value.items():
            yield key
            yield from _walk(item)
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            yield from _walk(item)


def _text_corpus(payload: Any) -> list[str]:
    texts: list[str] = []
    for item in _walk(payload):
        if item is None:
            continue
        if isinstance(item, (str, int, float, bool)):
            text = _normalize_text(item).strip()
            if text:
                texts.append(text)
    return texts


def _coerce_error_code(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value if value in IBKR_MARKET_DATA_ERROR_CODES else None
    text = str(value)
    for match in ERROR_CODE_RE.finditer(text):
        parsed = int(match.group(1))
        if parsed in IBKR_MARKET_DATA_ERROR_CODES:
            return parsed
    try:
        parsed = int(float(text.strip()))
    except (TypeError, ValueError):
        return None
    return parsed if parsed in IBKR_MARKET_DATA_ERROR_CODES else None


def _first_present(mapping: Mapping[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        if key in mapping:
            return mapping.get(key)
    return None


def _symbol(value: Any) -> str:
    for key in SYMBOL_KEYS:
        symbol = _get_value(value, key)
        if str(symbol or "").strip():
            return str(symbol).strip().upper()
    return ""


def _extract_error_observations(payload: Any) -> tuple[list[int], list[str], dict[str, list[str]]]:
    codes: set[int] = set()
    messages: set[str] = set()
    symbols_by_code: dict[str, set[str]] = {str(code): set() for code in IBKR_MARKET_DATA_ERROR_CODES}

    for item in _walk(payload):
        if isinstance(item, Mapping):
            code = None
            for key in ERROR_CODE_KEYS:
                if key in item:
                    code = _coerce_error_code(item.get(key))
                    if code is not None:
                        break
            message = _first_present(item, ERROR_MESSAGE_KEYS)
            if code is not None:
                codes.add(code)
                text = _normalize_text(message).strip()
                if text:
                    messages.add(text)
                symbol = _symbol(item)
                if symbol:
                    symbols_by_code[str(code)].add(symbol)
            else:
                text = _stable_json(item)
                for match in ERROR_CODE_RE.finditer(text):
                    codes.add(int(match.group(1)))
        else:
            text = _normalize_text(item).strip()
            if not text:
                continue
            for match in ERROR_CODE_RE.finditer(text):
                codes.add(int(match.group(1)))
                messages.add(text)
            lowered = text.lower()
            if (
                "additional subscription" in lowered
                or "not subscribed" in lowered
                or "delayed market data" in lowered
                or "snapshot timeout" in lowered
            ):
                messages.add(text)

    return (
        sorted(codes),
        sorted(messages),
        {code: sorted(symbols) for code, symbols in symbols_by_code.items() if symbols},
    )


def extract_candidate_rows(scanner_payload: Mapping[str, Any] | None) -> list[Any]:
    if not isinstance(scanner_payload, Mapping):
        return []
    rows: list[Any] = []
    seen: set[str] = set()
    for key in CANDIDATE_ROW_KEYS:
        value = scanner_payload.get(key)
        if not isinstance(value, (list, tuple, set)):
            continue
        for row in value:
            if not isinstance(row, Mapping) and not hasattr(row, "__dict__"):
                continue
            stable = _stable_json(row)
            if stable in seen:
                continue
            seen.add(stable)
            rows.append(row)
    return rows


def _valid_required_field(row: Any, required_field: str) -> bool:
    for alias in QUOTE_FIELD_ALIASES[required_field]:
        if _safe_float(_get_value(row, alias)) is not None:
            return True
    return False


def _missing_required_fields(row: Any) -> list[str]:
    return [field for field in REQUIRED_QUOTE_FIELDS if not _valid_required_field(row, field)]


def _missing_fields_by_symbol(rows: Sequence[Any]) -> dict[str, list[str]]:
    missing: dict[str, list[str]] = {}
    for index, row in enumerate(rows, start=1):
        fields = _missing_required_fields(row)
        if fields:
            symbol = _symbol(row) or f"UNKNOWN_ROW_{index}"
            missing[symbol] = fields
    return missing


def _symbols_with_all_required_fields(rows: Sequence[Any]) -> list[str]:
    symbols: set[str] = set()
    for row in rows:
        symbol = _symbol(row)
        if symbol and not _missing_required_fields(row):
            symbols.add(symbol)
    return sorted(symbols)


def _symbols_with_any_required_field(rows: Sequence[Any]) -> list[str]:
    symbols: set[str] = set()
    for row in rows:
        symbol = _symbol(row)
        if symbol and any(_valid_required_field(row, field) for field in REQUIRED_QUOTE_FIELDS):
            symbols.add(symbol)
    return sorted(symbols)


def _drop_reason_counts(scanner_payload: Mapping[str, Any] | None) -> dict[str, int]:
    if not isinstance(scanner_payload, Mapping):
        return {}
    counts: Counter[str] = Counter()
    drop_ledger = scanner_payload.get("drop_ledger", {})
    if isinstance(drop_ledger, Mapping):
        for key, value in drop_ledger.items():
            reason = _normalize_upper(key)
            if not reason:
                continue
            if isinstance(value, (list, tuple, set)):
                counts[reason] += len(value)
            else:
                counts[reason] += 1
    for row in extract_candidate_rows(scanner_payload):
        for key in ("drop_reason", "drop_reasons", "reasons"):
            value = _get_value(row, key)
            if isinstance(value, str):
                counts[_normalize_upper(value)] += 1
            elif isinstance(value, (list, tuple, set)):
                for item in value:
                    counts[_normalize_upper(item)] += 1
    return {key: value for key, value in sorted(counts.items()) if key}


def _normalized_counts(value: Mapping[str, Any] | None, scanner_payload: Mapping[str, Any] | None) -> dict[str, int]:
    if not value:
        return _drop_reason_counts(scanner_payload)
    counts: dict[str, int] = {}
    for key, item in value.items():
        reason = _normalize_upper(key)
        if not reason:
            continue
        try:
            counts[reason] = int(item)
        except (TypeError, ValueError):
            counts[reason] = 1
    return dict(sorted(counts.items()))


def _snapshot_timeout_observed(counts: Mapping[str, int], texts: Sequence[str]) -> bool:
    if any(reason in counts for reason in SNAPSHOT_TIMEOUT_REASONS):
        return True
    for text in texts:
        lowered = text.lower()
        if "snapshot timeout" in lowered or "snapshot timed out" in lowered:
            return True
        if "data_quality_fail_snapshot" in lowered:
            return True
    return False


def _probable_causes(classification: str) -> list[str]:
    if classification == MARKET_DATA_SUBSCRIPTION_REQUIRED:
        return [
            "IBKR exchange or API market-data subscription entitlement is missing for the requested symbols.",
            "TWS/Gateway can connect, but the account is not entitled to the requested live market-data feed.",
        ]
    if classification == MARKET_DATA_NOT_SUBSCRIBED:
        return [
            "IBKR reports the requested market data is not subscribed for at least one requested symbol.",
            "The account, exchange, or security type does not currently provide usable real-time API quotes.",
        ]
    if classification == DELAYED_DATA_AVAILABLE_BUT_UNUSABLE:
        return [
            "IBKR returned delayed-data availability, but the required last/close/volume/bid/ask fields were still unavailable for Ross gates.",
            "Delayed data is not acceptable evidence for PAPER readiness in this certification path.",
        ]
    if classification == SNAPSHOT_TIMEOUT:
        return [
            "IBKR quote snapshots timed out or scanner rows failed snapshot data-quality checks.",
            "TWS/Gateway market-data mode, permissions, pacing, or symbol routing may be preventing timely quote snapshots.",
        ]
    if classification == SNAPSHOT_FIELDS_MISSING:
        return [
            "Scanner rows were present, but at least one required last/close/volume/bid/ask field was missing or non-positive.",
            "The runtime should stay blocked until real quote fields are complete enough for existing Ross gates.",
        ]
    if classification == MARKET_DATA_USABLE:
        return [
            "Required quote fields were present for at least one observed scanner row and no known IBKR market-data error was detected."
        ]
    return ["No known IBKR market-data failure signature was detected from the available evidence."]


def _operator_next_steps(classification: str) -> list[str]:
    if classification == MARKET_DATA_USABLE:
        return [
            "Keep PAPER_READY=NO until the full PR1040/PR1045 observation and human review pass.",
            "Re-run the bounded READ_ONLY adapter and validate the resulting observation input with the PR1039 producer.",
        ]
    return [
        "Confirm TWS/Gateway is connected in READ_ONLY observation mode and API access is enabled.",
        "Confirm the IBKR account has the needed exchange/API market-data subscriptions for the requested symbols.",
        "Check the TWS/Gateway market-data type setting and avoid using delayed data as readiness proof.",
        "Re-run the bounded READ_ONLY adapter after fixing data access; do not enable PAPER or LIVE for this diagnostic.",
    ]


def classify_ibkr_market_data(
    *,
    scanner_payload: Mapping[str, Any] | None = None,
    candidate_rows: Sequence[Any] | None = None,
    drop_reason_counts: Mapping[str, Any] | None = None,
) -> str:
    rows = list(candidate_rows) if candidate_rows is not None else extract_candidate_rows(scanner_payload)
    texts = _text_corpus(scanner_payload or {})
    codes, messages, _ = _extract_error_observations(scanner_payload or {})
    joined_text = "\n".join(texts + messages).lower()
    counts = _normalized_counts(drop_reason_counts, scanner_payload)
    missing_by_symbol = _missing_fields_by_symbol(rows)
    fields_missing = bool(rows and missing_by_symbol)
    snapshot_timeout = _snapshot_timeout_observed(counts, texts + messages)
    delayed_observed = "delayed market data" in joined_text or "displaying delayed" in joined_text
    subscription_required = 10089 in codes or "requires additional subscription" in joined_text
    not_subscribed = 10167 in codes or "not subscribed" in joined_text

    if subscription_required:
        return MARKET_DATA_SUBSCRIPTION_REQUIRED
    if not_subscribed and delayed_observed and fields_missing:
        return DELAYED_DATA_AVAILABLE_BUT_UNUSABLE
    if not_subscribed:
        return MARKET_DATA_NOT_SUBSCRIBED
    if snapshot_timeout:
        return SNAPSHOT_TIMEOUT
    if fields_missing:
        return SNAPSHOT_FIELDS_MISSING
    if rows and _symbols_with_all_required_fields(rows):
        return MARKET_DATA_USABLE
    return MARKET_DATA_DIAGNOSTIC_UNKNOWN


def build_ibkr_market_data_diagnostic(
    *,
    scanner_payload: Mapping[str, Any] | None = None,
    env: Mapping[str, Any] | None = None,
    candidate_rows: Sequence[Any] | None = None,
    drop_reason_counts: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload = scanner_payload if isinstance(scanner_payload, Mapping) else {}
    rows = list(candidate_rows) if candidate_rows is not None else extract_candidate_rows(payload)
    counts = _normalized_counts(drop_reason_counts, payload)
    codes, messages, symbols_by_code = _extract_error_observations(payload)
    texts = _text_corpus(payload)
    joined_text = "\n".join(texts + messages).lower()
    missing_by_symbol = _missing_fields_by_symbol(rows)
    classification = classify_ibkr_market_data(
        scanner_payload=payload,
        candidate_rows=rows,
        drop_reason_counts=counts,
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "provider": "IBKR",
        "classification": classification,
        "observed_error_codes": codes,
        "observed_error_messages": messages,
        "symbols_by_error_code": symbols_by_code,
        "required_quote_fields": list(REQUIRED_QUOTE_FIELDS),
        "required_quote_field_aliases": {key: list(values) for key, values in QUOTE_FIELD_ALIASES.items()},
        "missing_fields_by_symbol": missing_by_symbol,
        "symbols_with_all_required_fields": _symbols_with_all_required_fields(rows),
        "symbols_with_any_required_field": _symbols_with_any_required_field(rows),
        "delayed_data_observed": "delayed market data" in joined_text or "displaying delayed" in joined_text,
        "subscription_required_observed": 10089 in codes or "requires additional subscription" in joined_text,
        "not_subscribed_observed": 10167 in codes or "not subscribed" in joined_text,
        "snapshot_timeout_observed": _snapshot_timeout_observed(counts, texts + messages),
        "snapshot_fields_missing": bool(rows and missing_by_symbol),
        "drop_reason_counts": counts,
        "requested_market_data_type": str((env or {}).get("IBKR_MARKET_DATA_TYPE") or "IBKR_READ_ONLY"),
        "scanner_mode": str((env or {}).get("SCANNER_MODE") or "LIVE_READONLY"),
        "run_mode": str((env or {}).get("RUN_MODE") or "READ_ONLY"),
        "read_only_runtime": True,
        "execution_enabled": False,
        "order_submission_enabled": False,
        "paper_ready": "NO",
        "paper_readiness_gate": "FAIL",
        "probable_causes": _probable_causes(classification),
        "operator_next_steps": _operator_next_steps(classification),
    }
