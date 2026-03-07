from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import requests

from src.config.runtime_config import get_persistence_sqlite_path

try:
    import yfinance as yf
except Exception:  # pragma: no cover - optional dependency in some environments.
    yf = None


@dataclass(frozen=True)
class FloatResult:
    value: Optional[int]
    source: str


class FloatProvider:
    """Authoritative float discovery service with cache + DB persistence."""

    def __init__(
        self,
        cache_path: str | Path = "data/fundamentals/float_cache.json",
        ttl_days: int = 7,
        sqlite_path: str | None = None,
    ) -> None:
        self.cache_path = Path(cache_path)
        self.ttl = timedelta(days=max(int(ttl_days), 1))
        self.sqlite_path = sqlite_path or get_persistence_sqlite_path(default="data/ibkr_system.db")
        self.last_float_failures: list[tuple[str, str]] = []
        self._cache = self._load_cache()
        self._ensure_db()

    def get_float(self, symbol: str) -> tuple[Optional[int], str]:
        symbol = str(symbol or "").upper().strip()
        if not symbol:
            return None, "UNKNOWN"

        cached_db = self._get_db_float(symbol)
        if cached_db is not None:
            return cached_db.value, cached_db.source

        cached_json = self._cache.get(symbol)
        if isinstance(cached_json, dict) and not self._is_stale(cached_json.get("timestamp")):
            value = self._parse_shares_value(cached_json.get("float"))
            source = str(cached_json.get("source") or "UNKNOWN").upper()
            if value is not None:
                self._upsert_db(symbol, value, source)
                return value, source

        self.last_float_failures = []
        for provider_name, provider_fn in (
            ("YAHOO", self.provider_yahoo),
            ("FINVIZ", self.provider_finviz),
        ):
            value, reason = provider_fn(symbol)
            if value is not None and value > 0:
                self._log_discovery(symbol=symbol, provider=provider_name, result="SUCCESS", value=value)
                self._write_cache_entry(symbol, value, provider_name)
                self._upsert_db(symbol, value, provider_name)
                return value, provider_name
            fail_reason = reason or "UNKNOWN"
            self.last_float_failures.append((provider_name, fail_reason))
            self._log_discovery(symbol=symbol, provider=provider_name, result="FAIL", reason=fail_reason)

        return None, "UNKNOWN"

    def provider_yahoo(self, symbol: str) -> tuple[Optional[int], str]:
        if yf is None:
            return None, "YFINANCE_UNAVAILABLE"
        try:
            ticker = yf.Ticker(symbol)
        except Exception:
            return None, "REQUEST_ERROR"

        try:
            fast_info = getattr(ticker, "fast_info", {}) or {}
            value = self._parse_shares_value(fast_info.get("floatShares"))
            if value is not None and value > 0:
                return value, "OK"
        except Exception:
            pass

        try:
            info = getattr(ticker, "info", {}) or {}
            value = self._parse_shares_value(info.get("floatShares"))
            if value is not None and value > 0:
                return value, "OK"
            return None, "FIELD_NOT_FOUND"
        except Exception:
            return None, "REQUEST_ERROR"

    def provider_finviz(self, symbol: str) -> tuple[Optional[int], str]:
        url = f"https://finviz.com/quote.ashx?t={symbol}"
        try:
            response = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
            response.raise_for_status()
        except requests.RequestException:
            return None, "REQUEST_ERROR"

        html = response.text
        match = re.search(
            r">\s*Float\s*</td>\s*<td[^>]*>\s*([^<]+)</td>",
            html,
            re.IGNORECASE,
        )
        if not match:
            return None, "FIELD_NOT_FOUND"
        parsed = self._parse_shares_value(match.group(1).strip())
        if parsed is None or parsed <= 0:
            return None, "PARSE_ERROR"
        return parsed, "OK"

    def _load_cache(self) -> dict[str, dict[str, object]]:
        try:
            if not self.cache_path.exists():
                return {}
            payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return {str(k).upper(): v for k, v in payload.items() if isinstance(v, dict)}
        except Exception:
            return {}
        return {}

    def _write_cache_entry(self, symbol: str, value: int, source: str) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._cache[symbol] = {
            "float": int(value),
            "source": source,
            "timestamp": datetime.now(timezone.utc).replace(second=0, microsecond=0).isoformat(),
        }
        self.cache_path.write_text(json.dumps(self._cache, indent=2, sort_keys=True), encoding="utf-8")

    def _is_stale(self, timestamp: object) -> bool:
        if not isinstance(timestamp, str):
            return True
        try:
            parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError:
            return True
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - parsed > self.ttl

    def _ensure_db(self) -> None:
        path = Path(self.sqlite_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS symbol_fundamentals (
                    symbol TEXT PRIMARY KEY,
                    float INTEGER,
                    source TEXT,
                    last_updated TEXT
                )
                """
            )
            conn.commit()

    def _get_db_float(self, symbol: str) -> FloatResult | None:
        with sqlite3.connect(self.sqlite_path) as conn:
            row = conn.execute(
                "SELECT float, source, last_updated FROM symbol_fundamentals WHERE symbol = ?",
                (symbol,),
            ).fetchone()
        if row is None:
            return None
        value = self._parse_shares_value(row[0])
        source = str(row[1] or "UNKNOWN").upper()
        last_updated = row[2]
        if value is None:
            return None
        if self._is_stale(last_updated):
            return None
        return FloatResult(value=value, source=source)

    def _upsert_db(self, symbol: str, value: int, source: str) -> None:
        with sqlite3.connect(self.sqlite_path) as conn:
            conn.execute(
                """
                INSERT INTO symbol_fundamentals(symbol, float, source, last_updated)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    float=excluded.float,
                    source=excluded.source,
                    last_updated=excluded.last_updated
                """,
                (symbol, int(value), source, datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()

    @staticmethod
    def _log_discovery(
        *,
        symbol: str,
        provider: str,
        result: str,
        value: Optional[int] = None,
        reason: Optional[str] = None,
    ) -> None:
        if result == "SUCCESS":
            print(
                "[FLOAT][DISCOVERY] "
                f"symbol={symbol} provider={provider} result=SUCCESS value={int(value or 0)}"
            )
            return
        print(
            "[FLOAT][DISCOVERY] "
            f"symbol={symbol} provider={provider} result=FAIL reason={reason or 'UNKNOWN'}"
        )

    @staticmethod
    def _parse_shares_value(value: object) -> Optional[int]:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return int(value) if float(value) > 0 else None
        text = str(value).strip().upper().replace(",", "")
        if text in {"", "N/A", "NA", "-", "--", "NONE", "NULL"}:
            return None
        match = re.match(r"^([\d]*\.?[\d]+)\s*([KMB])?$", text)
        if not match:
            return None
        number = float(match.group(1))
        suffix = match.group(2)
        multiplier = {None: 1, "K": 1_000, "M": 1_000_000, "B": 1_000_000_000}[suffix]
        return int(number * multiplier) if number > 0 else None
