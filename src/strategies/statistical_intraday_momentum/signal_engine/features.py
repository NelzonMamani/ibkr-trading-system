"""Feature extraction helpers for statistical intraday momentum."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from collections.abc import Iterator
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from statistics import pstdev
from typing import Iterable, Mapping


@dataclass(frozen=True)
class FeatureVector:
    """Lightweight container for deterministic features."""

    return_1m: float
    return_5m: float
    return_15m: float
    volatility: float
    volume_accel: float
    persistence: float
    time_of_day_bucket: str


def _extract_series(bars: Iterable[Mapping[str, float]], key: str) -> list[float]:
    return [float(bar[key]) for bar in bars if key in bar]


def compute_returns(prices: list[float]) -> list[float]:
    if len(prices) < 2:
        return []
    return [(prices[i] / prices[i - 1]) - 1.0 for i in range(1, len(prices))]


def compute_return(prices: list[float]) -> float:
    if len(prices) < 2:
        return 0.0
    return (prices[-1] / prices[0]) - 1.0


def realized_volatility(returns: list[float]) -> float:
    if len(returns) < 2:
        return 0.0
    return pstdev(returns)


def volume_acceleration(bars_1m: list[Mapping[str, float]], window: int = 5) -> float:
    volumes = _extract_series(bars_1m, "volume")
    if len(volumes) < window * 2:
        return 0.0
    recent = sum(volumes[-window:])
    prior = sum(volumes[-window * 2 : -window])
    if prior <= 0:
        return 0.0
    return (recent / prior) - 1.0


def persistence(returns: list[float], window: int = 10) -> float:
    if len(returns) < window:
        return 0.0
    recent = returns[-window:]
    positives = sum(1 for value in recent if value > 0)
    return positives / window


def build_feature_vector(
    bars_1m: list[Mapping[str, float]],
    bars_5m: list[Mapping[str, float]],
    time_of_day_bucket: str,
) -> FeatureVector:
    closes_1m = _extract_series(bars_1m, "close")
    closes_5m = _extract_series(bars_5m, "close")

    return_1m = compute_return(closes_1m[-2:])
    return_5m = compute_return(closes_1m[-6:])
    return_15m = compute_return(closes_1m[-16:])

    returns_1m = compute_returns(closes_1m)
    vol = realized_volatility(returns_1m[-15:])

    volume_accel = volume_acceleration(bars_1m)
    persistence_score = persistence(returns_1m, window=10)

    return FeatureVector(
        return_1m=return_1m,
        return_5m=return_5m,
        return_15m=return_15m,
        volatility=vol,
        volume_accel=volume_accel,
        persistence=persistence_score,
        time_of_day_bucket=time_of_day_bucket,
    )


# NEW project policy: validated completed context only. This is neither a setup
# nor executable admission; ATR and the native Core structural veto stay closed.
class CompletedContextError(ValueError):
    pass


def _context_fingerprint(value) -> str:
    def encode(item):
        if isinstance(item, datetime):
            return {"datetime": item.isoformat(), "fold": item.fold}
        raise TypeError("Unsupported context source value")
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=encode,
        allow_nan=False, separators=(",", ":")).encode()).hexdigest()


def _context_utc(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise CompletedContextError("TIME_UNKNOWN")
    return value.astimezone(timezone.utc)


def _context_number(value, *, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise CompletedContextError("NONFINITE_OR_MISSING_NUMBER")
    if value < 0 or (positive and value == 0):
        raise CompletedContextError("INVALID_NUMBER")
    return value


def _context_identity(identity):
    if (type(identity.get("con_id")) is not int or identity["con_id"] <= 0
            or identity.get("sec_type") != "STK" or identity.get("currency") != "USD"
            or not isinstance(identity.get("symbol"), str) or not identity["symbol"]
            or identity["symbol"] != identity["symbol"].strip().upper()):
        raise CompletedContextError("SECURITY_UNKNOWN")
    return tuple(identity[key] for key in ("con_id", "symbol", "sec_type", "currency"))


def _completed_context_values(source, *, assessed_at):
    from src.market_data.session_pct_change import covered_opening_window
    from src.domain.quote_freshness import quote_evidence, evidence_rejection
    from src.risk.data_quality_contract import data_quality_blocking_causes
    from src.market_data.reference_resolver import _parse_trading_date
    from src.adapters.data.historical_data_provider import normalize_intraday_bar_timestamp
    from src.config.config_resolver import get_config
    now = _context_utc(assessed_at)
    window = covered_opening_window(now)
    if window is None or window.phase != "RTH_OPEN":
        raise CompletedContextError("COVERED_RTH_OPEN_UNKNOWN")
    identity = _context_identity(source["identity"])
    history, quote, reference = (source[key] for key in ("history", "quote", "reference"))
    if (_context_identity(history["contract_identity"]) != identity
            or _context_identity(history["dispatched_contract_identity"]) != identity
            or _context_identity(reference["qualified_identity"]) != identity
            or reference["identity_key"] != f"conid:{identity[0]}"
            or reference["symbol"] != identity[1]
            or type(quote["con_id"]) is not int or quote["con_id"] != identity[0]
            or quote["symbol"] != identity[1]):
        raise CompletedContextError("SECURITY_CONFLICT")
    for source_identity in (history["contract_identity"], history["dispatched_contract_identity"], reference["qualified_identity"]):
        if any(source_identity[key] is not None and source["identity"][key] is not None
               and source_identity[key] != source["identity"][key]
               for key in ("exchange", "primary_exchange", "trading_class", "local_symbol")):
            raise CompletedContextError("SECURITY_ROUTING_CONFLICT")
    spec = history["request_spec"]
    if (history["status"] != "COMPLETE_BARS" or history["end_received"] is not True
            or type(history["request_id"]) is not int or history["request_id"] <= 0
            or not isinstance(spec, dict) or spec.get("bar_size_setting") != "1 min"
            or spec.get("what_to_show") != "TRADES" or type(spec.get("format_date")) is not int
            or spec["format_date"] != 2 or spec.get("timestamp_semantics") != "UTC_BAR_START"
            or type(spec.get("use_rth")) is not int or spec["use_rth"] not in {0, 1}
            or spec.get("keep_up_to_date") is not False or spec.get("chart_options_empty") is not True
            or not isinstance(spec.get("duration_str"), str) or not spec["duration_str"]
            or not isinstance(spec.get("end_date_time"), str)):
        raise CompletedContextError("HISTORY_REQUEST_UNVERIFIED")
    dispatched = _context_utc(history["request_dispatched_at_utc"])
    completed = _context_utc(history["completed_at_utc"])
    if not dispatched <= completed <= now:
        raise CompletedContextError("HISTORY_CLOCK_CONFLICT")
    if (not all(reference[key] is True for key in ("reference_resolved", "qualification_usable_reference",
            "execution_usable_reference", "continuity_usable_reference", "reference_is_previous_completed_session"))
            or reference["reference_semantics"] != "PREVIOUS_COMPLETED_RTH_CLOSE"
            or _parse_trading_date(reference["reference_trading_date"]) != datetime.fromisoformat(window.previous_session).date()
            or reference["reference_degraded"] is not False or reference["reference_synthetic"] is not False
            or reference["reference_quality_tier"] not in {"PRIMARY", "SECONDARY"}
            or reference["reference_failure_reason"]):
        raise CompletedContextError("REFERENCE_UNVERIFIED")
    _context_number(reference["reference_price"], positive=True)
    if (quote["snapshot_complete"] is not True or quote["market_data_type_confirmed"] is not True
            or quote["returned_market_data_type"] != "LIVE" or quote["market_data_type"] != "LIVE"
            or quote["requested_market_data_type"] != "LIVE"
            or type(quote["request_id"]) is not int or quote["request_id"] <= 0
            or data_quality_blocking_causes(quote["data_quality_flags"])):
        raise CompletedContextError("QUOTE_UNVERIFIED")
    if evidence_rejection(quote_evidence(quote["market_timestamp_utc"], quote["timestamp_source"],
                                        quote["data_quality_flags"]), now=now):
        raise CompletedContextError("QUOTE_TIME_REJECTED")
    if not _context_utc(quote["market_timestamp_utc"]) <= _context_utc(quote["asof_utc"]) <= now:
        raise CompletedContextError("QUOTE_ACQUISITION_CLOCK_CONFLICT")
    last, bid, ask = (_context_number(quote[key], positive=True) for key in ("last", "bid", "ask"))
    volume = _context_number(quote["volume"])
    if bid > ask:
        raise CompletedContextError("QUOTE_CROSSED")
    bars = history["bars"]
    selected_count = history["normalization_selected_count"]
    raw_selected = history["normalization_source_bars"]
    raw_stamps = history["normalized_raw_bar_timestamps"]
    if (type(history["source_bar_count"]) is not int
            or history["source_bar_count"] != len(history["raw_bar_timestamps"])
            or type(selected_count) is not int or selected_count > history["source_bar_count"]
            or type(history["normalization_rejected_count"]) is not int
            or history["normalization_rejected_count"] != 0 or raw_selected is None
            or selected_count != len(bars) or selected_count != len(raw_selected)
            or selected_count != len(raw_stamps)
            or history["raw_source_bars"] is None
            or len(history["raw_source_bars"]) != history["source_bar_count"]
            or tuple(history["raw_source_bars"][-selected_count:]) != tuple(raw_selected)
            or tuple(row["date"] for row in raw_selected) != tuple(raw_stamps)
            or tuple(history["raw_bar_timestamps"][-selected_count:]) != tuple(raw_stamps)):
        raise CompletedContextError("NORMALIZATION_UNVERIFIED_OR_REJECTED")
    if len(bars) < 16:
        raise CompletedContextError("HISTORY_LOOKBACK_INCOMPLETE")
    projected = []
    expected = window.current_open
    for bar, raw_timestamp, raw_bar in zip(bars, raw_stamps, raw_selected):
        # The owner supplies normalized Candle timestamps. Do not guess numeric,
        # naive or ambiguous broker-local strings into UTC interval starts.
        if not isinstance(bar.get("timestamp"), datetime):
            raise CompletedContextError("BAR_START_UNKNOWN")
        start = _context_utc(bar["timestamp"])
        if isinstance(raw_timestamp, bool) or _context_utc(normalize_intraday_bar_timestamp(raw_timestamp)) != start:
            raise CompletedContextError("BAR_RAW_TIMESTAMP_CONFLICT")
        end = start + timedelta(minutes=1)
        if start != expected or end > completed:
            raise CompletedContextError("BAR_COVERAGE_OR_COMPLETION_CONFLICT")
        values = {key: _context_number(bar[key], positive=key != "volume")
                  for key in ("open", "high", "low", "close", "volume")}
        if any(isinstance(raw_bar[key], bool) or float(raw_bar[key]) != values[key] for key in values):
            raise CompletedContextError("NORMALIZATION_RAW_CONFLICT")
        if not values["low"] <= min(values["open"], values["close"]) <= max(values["open"], values["close"]) <= values["high"]:
            raise CompletedContextError("BAR_GEOMETRY_INVALID")
        projected.append(dict(values, timestamp=start, end_timestamp=end,
                              raw_timestamp=raw_timestamp))
        expected = end
    if not 0 <= (now - expected).total_seconds() < 60:
        raise CompletedContextError("HISTORY_STALE_OR_FUTURE")
    five = []
    for offset in range(0, len(projected) - 4, 5):
        block = projected[offset:offset + 5]
        five.append(dict(timestamp=block[0]["timestamp"], end_timestamp=block[-1]["end_timestamp"],
            open=block[0]["open"], high=max(b["high"] for b in block), low=min(b["low"] for b in block),
            close=block[-1]["close"], volume=sum(b["volume"] for b in block),
            source_timestamps=tuple(b["raw_timestamp"] for b in block)))
    return dict(symbol=identity[1], last_price=last, day_volume=volume,
        minutes_since_open=int((now - window.current_open).total_seconds() // 60),
        bars_1m=projected, bars_5m=five, spread_pct=(ask - bid) / last,
        now_ts=now.isoformat(), completed_context_calendar=window.snapshot(),
        completed_context_configuration={"quote_max_age_seconds": get_config("IBKR_SNAPSHOT_MAX_AGE_SECONDS")})


@dataclass(frozen=True)
class CompletedSignalContext(Mapping[str, object]):
    """Detached component facts. Revalidation is required before consumption."""
    source_facts: dict
    payload: dict
    source_fingerprint: str
    derived_fingerprint: str

    def __getitem__(self, key):
        return self.payload[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.payload)

    def __len__(self):
        return len(self.payload)

    def revalidated(self, *, assessed_at):
        if (_context_fingerprint(self.source_facts) != self.source_fingerprint
                or _context_fingerprint(self.payload) != self.derived_fingerprint):
            raise CompletedContextError("CONTEXT_MUTATED")
        current = _completed_context_values(self.source_facts, assessed_at=assessed_at)
        if current["completed_context_calendar"] != self.payload["completed_context_calendar"]:
            raise CompletedContextError("CALENDAR_CHANGED")
        if current["completed_context_configuration"] != self.payload["completed_context_configuration"]:
            raise CompletedContextError("CONFIGURATION_CHANGED")
        return current


def build_completed_context(*, history, identity, quote, reference, assessed_at):
    """Validate real historical-owner metadata without acquiring external data."""
    from src.ibkr.market_data_client import HistoricalDataResult
    from src.market_data.candidate_identity import CandidateIdentity
    from src.domain.market_snapshot import MarketSnapshot
    from src.market_data.reference_resolver import CanonicalReferenceResult
    if not (isinstance(history, HistoricalDataResult) and isinstance(identity, CandidateIdentity)
            and isinstance(quote, MarketSnapshot) and isinstance(reference, CanonicalReferenceResult)):
        raise CompletedContextError("SOURCE_TYPE_UNKNOWN")
    try:
        source = deepcopy({key: asdict(value) for key, value in
            dict(history=history, identity=identity, quote=quote, reference=reference).items()})
        values = _completed_context_values(source, assessed_at=assessed_at)
        return CompletedSignalContext(source, values, _context_fingerprint(source), _context_fingerprint(values))
    except (KeyError, TypeError, ValueError, OverflowError, AttributeError) as exc:
        if isinstance(exc, CompletedContextError):
            raise
        raise CompletedContextError("SOURCE_MALFORMED") from exc


@dataclass(frozen=True)
class CompletedATRMeasurement:
    """Measurement only. No numerical admission bounds have been adopted."""
    policy: str
    source_sha256: str
    derived_sha256: str
    member_starts: tuple[str, ...]
    true_ranges: tuple[float, ...]
    seed_at: str
    seed_usd: float
    update_at: tuple[str, ...]
    atr_usd: tuple[float, ...]
    atr_pct: tuple[float, ...]
    latest_completed_close: float
    admission: str = "UNKNOWN"
    eligible: bool = False
    lower_bound_pct: None = None
    upper_bound_pct: None = None


def measure_completed_atr(context, *, assessed_at) -> CompletedATRMeasurement:
    """Wilder14 over the original open-aligned completed stream, never a suffix."""
    if not isinstance(context, CompletedSignalContext):
        raise CompletedContextError("CONTEXT_TYPE_UNKNOWN")
    values = context.revalidated(assessed_at=assessed_at)
    bars = values["bars_1m"]
    ranges = tuple(max(bar["high"] - bar["low"], abs(bar["high"] - prior["close"]),
                       abs(bar["low"] - prior["close"]))
                   for prior, bar in zip(bars, bars[1:]))
    if len(ranges) < 14:
        raise CompletedContextError("ATR_WARMUP_INCOMPLETE")
    seed = sum(ranges[:14]) / 14
    levels = [seed]
    for value in ranges[14:]:
        levels.append((13 * levels[-1] + value) / 14)
    percentages = tuple(100 * level / bar["close"] for level, bar in zip(levels, bars[14:]))
    if not all(math.isfinite(x) and x >= 0 for x in (*ranges, *levels, *percentages)):
        raise CompletedContextError("ATR_ARITHMETIC_INVALID")
    # Check the detached source and derived members again before returning evidence.
    context.revalidated(assessed_at=assessed_at)
    return CompletedATRMeasurement(
        policy="P02_ATR_MEASUREMENT_V1", source_sha256=context.source_fingerprint,
        derived_sha256=context.derived_fingerprint,
        member_starts=tuple(bar["timestamp"].isoformat() for bar in bars),
        true_ranges=ranges, seed_at=bars[14]["end_timestamp"].isoformat(), seed_usd=seed,
        update_at=tuple(bar["end_timestamp"].isoformat() for bar in bars[14:]),
        atr_usd=tuple(levels), atr_pct=percentages, latest_completed_close=bars[-1]["close"])


def offline_atr_report(raw: bytes, *, expected_sha256: str) -> bytes:
    """Validate immutable supplied evidence; no IO, acquisition or live permission.

    Recorded assessments are retrospective only. Effective existing calendar and
    configuration must reproduce each supplied derived fingerprint. No config is
    installed from the input. MARKET_UNVERIFIED is a label, never data approval.
    """
    def refuse(reason):
        raise CompletedContextError(reason)

    def digest(value):
        return (isinstance(value, str) and len(value) == 64
                and all(c in "0123456789abcdef" for c in value))

    if type(raw) is not bytes or not 0 < len(raw) <= 16 * 1024 * 1024:
        refuse("OFFLINE_BYTES_INVALID")
    actual_hash = hashlib.sha256(raw).hexdigest()
    if not digest(expected_sha256) or actual_hash != expected_sha256:
        refuse("OFFLINE_HASH_CONFLICT")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                refuse("OFFLINE_DUPLICATE_KEY")
            result[key] = value
        return result

    def decode(value):
        if isinstance(value, dict):
            if "datetime" in value or "fold" in value:
                if (set(value) != {"datetime", "fold"} or type(value["fold"]) is not int
                        or value["fold"] not in (0, 1) or not isinstance(value["datetime"], str)):
                    refuse("OFFLINE_DATETIME_INVALID")
                _context_utc(value["datetime"])  # validate awareness without rewriting original offset
                return datetime.fromisoformat(value["datetime"].replace("Z", "+00:00")).replace(fold=value["fold"])
            return {k: decode(v) for k, v in value.items()}
        if isinstance(value, list):
            return [decode(v) for v in value]
        return value

    try:
        bundle = json.loads(raw.decode("utf-8"), object_pairs_hook=unique,
                            parse_constant=lambda _: refuse("OFFLINE_NONFINITE"))
        if (type(bundle) is not dict or set(bundle) != {"schema", "dataset_id", "classification", "sessions"}
                or bundle["schema"] != "P02_ATR_OFFLINE_V1"
                or bundle["classification"] not in ("SYNTHETIC", "MARKET_UNVERIFIED")
                or not isinstance(bundle["dataset_id"], str) or not bundle["dataset_id"].strip()
                or len(bundle["dataset_id"]) > 256 or type(bundle["sessions"]) is not list
                or not 1 <= len(bundle["sessions"]) <= 512):
            refuse("OFFLINE_SCHEMA_INVALID")
        reports, seen = [], set()
        for row in bundle["sessions"]:
            if (type(row) is not dict or set(row) != {"source_facts", "assessed_at",
                    "expected_source_sha256", "expected_derived_sha256"}
                    or not digest(row["expected_source_sha256"]) or not digest(row["expected_derived_sha256"])):
                refuse("OFFLINE_SESSION_SCHEMA_INVALID")
            source = decode(row["source_facts"])
            assessed = _context_utc(row["assessed_at"])
            source_hash = _context_fingerprint(source)
            if source_hash != row["expected_source_sha256"]:
                refuse("OFFLINE_SOURCE_CONFLICT")
            values = _completed_context_values(source, assessed_at=assessed)
            derived_hash = _context_fingerprint(values)
            if derived_hash != row["expected_derived_sha256"]:
                refuse("OFFLINE_DERIVED_CONFLICT")
            key = (_context_identity(source["identity"]), values["completed_context_calendar"]["target_session"])
            if key in seen:
                refuse("OFFLINE_DUPLICATE_SESSION")
            seen.add(key)
            context = CompletedSignalContext(source, values, source_hash, derived_hash)
            measurement = measure_completed_atr(context, assessed_at=assessed)
            history = source["history"]
            reports.append(dict(measurement=asdict(measurement), identity=source["identity"],
                source_facts=source,
                calendar=values["completed_context_calendar"], configuration=values["completed_context_configuration"],
                assessed_at=assessed.isoformat(), assessment_use="HISTORICAL_REPLAY_ONLY",
                request_id=history["request_id"], request_spec=history["request_spec"],
                dispatched_at=history["request_dispatched_at_utc"], completed_at=history["completed_at_utc"],
                raw_member_timestamps=history["normalized_raw_bar_timestamps"],
                coverage=dict(completed_1m=len(values["bars_1m"]), complete_5m=len(values["bars_5m"]),
                    true_range_count=len(measurement.true_ranges), start=measurement.member_starts[0],
                    end=measurement.update_at[-1]),
                quote_availability="VALIDATED_CONTEXT_QUOTE", costs_availability="UNAVAILABLE"))
        return json.dumps(dict(schema="P02_ATR_REPORT_V1", input_sha256=actual_hash,
            dataset_id=bundle["dataset_id"], classification=bundle["classification"],
            approved_dataset=False, performance_claims=False, sessions=reports),
            sort_keys=True, allow_nan=False, separators=(",", ":"),
            default=lambda value: {"datetime": value.isoformat(), "fold": value.fold}
                if isinstance(value, datetime) else refuse("OFFLINE_ENCODING_INVALID")).encode("utf-8")
    except (KeyError, TypeError, ValueError, OverflowError, AttributeError, RecursionError) as exc:
        if isinstance(exc, CompletedContextError):
            raise
        raise CompletedContextError("OFFLINE_INPUT_MALFORMED") from exc
