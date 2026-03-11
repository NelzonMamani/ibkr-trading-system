from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup

from src.config.runtime_config import get_persistence_sqlite_path

try:
    import yfinance as yf
except Exception:
    yf = None


@dataclass(frozen=True)
class FloatResult:
    value: Optional[int]
    source: str


class FloatProvider:
    """
    Canonical float discovery service.

    Sources:
    1) Yahoo Finance (primary)
    2) Finviz HTML parsing (fallback)

    Results are cached in:
        data/reference/float_cache.json

    and persisted in SQLite:
        symbol_fundamentals table
    """

    def __init__(
        self,
        cache_path: str | Path = "data/reference/float_cache.json",
        ttl_days: int = 7,
        sqlite_path: str | None = None,
    ) -> None:

        self.cache_path = Path(cache_path)
        print(f"[FLOAT][CACHE_PATH] path={self.cache_path.resolve()}")
        self.ttl = timedelta(days=max(int(ttl_days), 1))

        self.sqlite_path = sqlite_path or get_persistence_sqlite_path(
            default="data/ibkr_system.db"
        )

        self._cache = self._load_cache()

        self._ensure_db()

    def record_discovery(self, symbol: str, value: int, source: str) -> None:
        """Persist a discovered float to canonical JSON + sqlite."""
        self._handle_success(symbol=str(symbol or "").upper().strip(), value=int(value), source=str(source or "UNKNOWN"))

    # ======================================================
    # PUBLIC ENTRY POINT
    # ======================================================

    def get_float(self, symbol: str) -> tuple[Optional[int], str]:

        symbol = str(symbol or "").upper().strip()

        if not symbol:
            return None, "UNKNOWN"

        # ----------------------------------
        # DB CACHE
        # ----------------------------------

        db_value = self._get_db_float(symbol)

        if db_value is not None:
            return db_value.value, db_value.source

        # ----------------------------------
        # JSON CACHE
        # ----------------------------------

        cache_entry = self._cache.get(symbol)

        if isinstance(cache_entry, dict):

            if not self._is_stale(cache_entry.get("timestamp")):

                value = cache_entry.get("float")

                if isinstance(value, int) and value > 0:

                    source = str(cache_entry.get("source") or "CACHE")

                    self._upsert_db(symbol, value, source)

                    return value, source

        # ----------------------------------
        # DISCOVERY
        # ----------------------------------

        value, reason = self.provider_yahoo(symbol)

        if value:
            self._handle_success(symbol, value, "YAHOO")
            return value, "YAHOO"

        value, reason = self.provider_finviz(symbol)

        if value:
            self._handle_success(symbol, value, "FINVIZ")
            return value, "FINVIZ"

        return None, "UNKNOWN"

    # ======================================================
    # PROVIDERS
    # ======================================================

    def provider_yahoo(self, symbol: str) -> tuple[Optional[int], str]:

        if yf is None:
            return None, "YFINANCE_UNAVAILABLE"

        try:

            ticker = yf.Ticker(symbol)

            info = ticker.info

            value = info.get("floatShares")

            if value and int(value) > 0:

                return int(value), "OK"

        except Exception:

            return None, "REQUEST_ERROR"

        return None, "FIELD_NOT_FOUND"

    def provider_finviz(self, symbol: str) -> tuple[Optional[int], str]:

        url = f"https://finviz.com/quote.ashx?t={symbol}"

        try:

            response = requests.get(
                url,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=8,
            )

            soup = BeautifulSoup(response.content, "html.parser")

            table = soup.find("table", class_="snapshot-table2")

            if not table:
                return None, "TABLE_NOT_FOUND"

            cells = table.find_all("td")

            for i, cell in enumerate(cells):

                if cell.text.strip() == "Float":

                    float_text = cells[i + 1].text.strip().replace(",", "")

                    parsed = self._parse_shares_value(float_text)

                    if parsed:
                        return parsed, "OK"

                    return None, "PARSE_ERROR"

        except Exception:

            return None, "REQUEST_ERROR"

        return None, "FIELD_NOT_FOUND"

    # ======================================================
    # SUCCESS HANDLING
    # ======================================================

    def _handle_success(self, symbol: str, value: int, source: str) -> None:

        print(
            "[FLOAT][DISCOVERY] "
            f"symbol={symbol} provider={source} result=SUCCESS value={value}"
        )

        self._write_cache_entry(symbol, value, source)

        self._upsert_db(symbol, value, source)

    # ======================================================
    # CACHE
    # ======================================================

    def _load_cache(self) -> dict[str, dict]:

        try:

            if not self.cache_path.exists():
                print(f"[FLOAT][CACHE_LOAD] path={self.cache_path.resolve()} entries=0")
                return {}

            payload = json.loads(self.cache_path.read_text(encoding="utf-8"))

            if isinstance(payload, dict):
                print(f"[FLOAT][CACHE_LOAD] path={self.cache_path.resolve()} entries={len(payload)}")
                return payload

        except Exception:
            print(f"[FLOAT][CACHE_LOAD] path={self.cache_path.resolve()} entries=0")
            return {}

        return {}

    def _write_cache_entry(self, symbol: str, value: int, source: str) -> None:

        self.cache_path.parent.mkdir(parents=True, exist_ok=True)

        self._cache[symbol] = {
            "float": int(value),
            "source": source,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        self.cache_path.write_text(
            json.dumps(self._cache, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        print(
            "[FLOAT][CACHE_WRITE] "
            f"symbol={symbol} path={self.cache_path.resolve()} source={source} value={int(value)}"
        )

    # ======================================================
    # DB
    # ======================================================

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

        value = row[0]

        source = str(row[1] or "UNKNOWN")

        last_updated = row[2]

        if value is None:
            return None

        if self._is_stale(last_updated):
            return None

        return FloatResult(value=int(value), source=source)

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
                (
                    symbol,
                    int(value),
                    source,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

            conn.commit()

    # ======================================================
    # UTILITIES
    # ======================================================

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

    @staticmethod
    def _parse_shares_value(value: object) -> Optional[int]:

        if value is None:
            return None

        text = str(value).strip().upper().replace(",", "")

        if text.endswith("B"):
            return int(float(text[:-1]) * 1_000_000_000)

        if text.endswith("M"):
            return int(float(text[:-1]) * 1_000_000)

        if text.endswith("K"):
            return int(float(text[:-1]) * 1_000)

        try:
            return int(float(text))
        except Exception:
            return None
