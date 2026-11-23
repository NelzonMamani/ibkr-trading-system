"""Private same-contract calibration for the installed native IBKR source.

IBKR's watchlist tick and its filtered historical bars are distinct data series.
Each needs its own independent TWS display comparison in explicit shares.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo

from src.domain.quote_freshness import quote_time_rejection
from src.domain.volume_evidence import native_stock_volume_rejection

SCHEMA = "ROSS_IBKR_EXACT_CONTRACT_VOLUME_V2"
HISTORICAL_BASIS = "IBKR_RTH_TRADES_DAILY"
_MAX_BYTES = 32768
_NY = ZoneInfo("America/New_York")


def _read(path):
    try:
        path = Path(path)
        if not path.is_file():
            raise RuntimeError("PAPER_RELEASE_VOLUME_CALIBRATION_REQUIRED")
        with path.open("rb") as handle:
            data = handle.read(_MAX_BYTES + 1)
        if len(data) > _MAX_BYTES:
            raise RuntimeError("PAPER_RELEASE_VOLUME_CALIBRATION_FORMAT")
        return json.loads(data), hashlib.sha256(data).hexdigest()
    except (OSError, ValueError, TypeError) as exc:
        raise RuntimeError("PAPER_RELEASE_VOLUME_CALIBRATION_FORMAT") from exc


def _require(condition, gate):
    if not condition:
        raise RuntimeError("PAPER_RELEASE_VOLUME_" + gate)


def _time(value):
    try:
        stamp = datetime.fromisoformat(value)
        if stamp.utcoffset() is not None:
            return stamp
    except (TypeError, ValueError):
        pass
    raise RuntimeError("PAPER_RELEASE_VOLUME_COMPARISON_TIME")


def _same_number(api, independent):
    return type(independent) is int and type(api) in (int, float) and independent > 0 and api == independent


def validate_paper_volume_calibration(record, *, now=None):
    now = now or datetime.now(timezone.utc)
    _require(type(record) is dict and set(record) == {"schema", "probe", "comparison"}
             and record["schema"] == SCHEMA, "CALIBRATION_FORMAT")
    probe, comparison = record["probe"], record["comparison"]
    _require(type(probe) is dict and set(probe) == {"watchlist", "history"}
             and type(comparison) is dict, "CALIBRATION_FORMAT")
    _require(set(comparison) == {"tws_build", "con_id", "watchlist_observed_at", "watchlist_shares",
              "historical_bar_date", "historical_bar_shares", "watchlist_shares_setting",
              "historical_shares_setting"}, "COMPARISON_REQUIRED")
    _require(isinstance(comparison["tws_build"], str)
             and re.fullmatch(r"[0-9][0-9A-Za-z. -]{1,39}", comparison["tws_build"])
             and comparison["watchlist_shares_setting"] is True
             and comparison["historical_shares_setting"] is True, "TWS_BUILD_AND_SHARE_SETTINGS_REQUIRED")
    watch, history = probe["watchlist"], probe["history"]
    _require(type(watch) is dict and type(history) is dict, "NATIVE_PROBE_REQUIRED")
    observed = _time(comparison["watchlist_observed_at"])
    received = _time(watch.get("received_at_utc"))
    captured = max(observed, received, _time(watch.get("market_timestamp_utc")))
    _require(native_stock_volume_rejection(watch, now=captured) is None
             and type(comparison["con_id"]) is int and comparison["con_id"] == watch["con_id"]
             and quote_time_rejection(observed, "LAST_TRADE", now=captured) is None
             and _same_number(watch.get("raw_value"), comparison["watchlist_shares"]), "WATCHLIST_COMPARISON_MISMATCH")
    _require(captured <= now and captured.astimezone(_NY).date() == now.astimezone(_NY).date(),
             "CALIBRATION_TRADING_DATE_CHANGED")
    completed = _time(history.get("completed_at_utc"))
    _require(history.get("basis") == HISTORICAL_BASIS and history.get("end_received") is True
             and history.get("con_id") == watch["con_id"]
             and history.get("connection_epoch") == watch["connection_epoch"]
             and history.get("client_id") == watch["client_id"]
             and history.get("server_version") == watch["server_version"]
             and received <= completed <= now
             and completed.astimezone(_NY).date() == captured.astimezone(_NY).date()
             and isinstance(history.get("bars"), list), "HISTORICAL_PROBE_UNVERIFIED")
    bar_date = comparison["historical_bar_date"]
    _require(isinstance(bar_date, str) and re.fullmatch(r"[0-9]{8}", bar_date)
             and bar_date < captured.astimezone(_NY).strftime("%Y%m%d"), "HISTORICAL_COMPARISON_DATE")
    matches = [row for row in history["bars"] if isinstance(row, list)
               and len(row) == 2 and row[0] == bar_date]
    _require(len(matches) == 1 and _same_number(matches[0][1], comparison["historical_bar_shares"]),
             "HISTORICAL_COMPARISON_MISMATCH")
    return {
        "con_id": watch["con_id"], "symbol": watch["symbol"],
        "primary_exchange": watch["primary_exchange"],
        "server_version": watch["server_version"], "sdk_distribution": watch["sdk_distribution"],
        "trading_date": captured.astimezone(_NY).date(),
    }


def prepare_paper_volume_calibration(probe_path, comparison_path, output_path, *, now=None):
    probe, _ = _read(probe_path)
    comparison, _ = _read(comparison_path)
    record = {"schema": SCHEMA, "probe": probe, "comparison": comparison}
    validate_paper_volume_calibration(record, now=now)
    with Path(output_path).open("x", encoding="utf-8") as handle:
        json.dump(record, handle, sort_keys=True)


def load_paper_volume_calibration(path, *, now=None):
    record, digest = _read(path)
    return {**validate_paper_volume_calibration(record, now=now), "calibration_id": digest}
