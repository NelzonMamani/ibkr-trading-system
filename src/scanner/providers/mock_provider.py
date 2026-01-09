from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Optional

from src.config.config_resolver import get_config
from .base import IntradayStats, QuoteData, ScannerDataProvider


def _load_mock_symbols(path: Path, fallback: list[str]) -> list[str]:
    if not path.exists():
        return fallback
    symbols: list[str] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            symbol = line.strip().upper()
            if not symbol or symbol.startswith("#"):
                continue
            symbols.append(symbol)
    except Exception:
        return fallback
    return symbols or fallback


def _rng_for_symbol(symbol: str, seed: int) -> random.Random:
    symbol_seed = f"{symbol}:{seed}"
    return random.Random(symbol_seed)


def _load_float_cache(path: Path) -> dict:
    try:
        if not path.exists():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception:
        return {}
    return {}


class MockScannerProvider(ScannerDataProvider):
    source_name = "MOCK"

    def __init__(self, symbols: Optional[list[str]] = None, seed: Optional[int] = None) -> None:
        self.seed = seed if seed is not None else int(get_config("SCANNER_MOCK_SEED"))
        default_file = (
            Path(__file__).resolve().parents[1] / "mock_universe.txt"
        )
        symbols_file = Path(get_config("SCANNER_MOCK_SYMBOLS_FILE") or str(default_file))
        fallback = [
            "AAPL",
            "MSFT",
            "NVDA",
            "AMD",
            "TSLA",
            "META",
            "AMZN",
            "GOOGL",
            "NFLX",
            "BABA",
            "PLTR",
            "RIVN",
            "SNOW",
            "CRWD",
            "COIN",
            "SOFI",
            "LCID",
            "NIO",
            "MARA",
            "RIOT",
            "CLSK",
            "GME",
            "AMC",
            "DKNG",
            "ROKU",
            "UPST",
            "SHOP",
            "AI",
            "PATH",
            "FUBO",
            "SOUN",
            "IONQ",
            "AVGO",
            "INTC",
            "MU",
            "TSM",
            "ADBE",
            "ORCL",
            "QCOM",
            "SPOT",
            "UBER",
            "LYFT",
            "BA",
            "GE",
            "XOM",
            "CVX",
            "JPM",
            "BAC",
            "C",
            "WFC",
        ]
        self.symbols = symbols or _load_mock_symbols(symbols_file, fallback)
        float_cache_path = Path(get_config("SCANNER_FLOAT_CACHE_FILE"))
        self.float_cache = _load_float_cache(float_cache_path)

    def connect(self) -> None:
        return None

    def disconnect(self) -> None:
        return None

    def get_top_gainers(self, limit: int) -> list[str]:
        return self.symbols[:limit]

    def get_quote(self, symbol: str) -> QuoteData:
        rng = _rng_for_symbol(symbol, self.seed)
        prev_close = round(rng.uniform(2.0, 10.0), 2)
        pct_change = rng.uniform(12.0, 28.0)
        last = round(prev_close * (1.0 + pct_change / 100.0), 2)
        last = min(last, 19.5)
        gap_pct = rng.uniform(0.5, 6.5)
        open_price = round(prev_close * (1.0 + gap_pct / 100.0), 2)
        high = round(max(last, open_price) * rng.uniform(1.0, 1.2), 2)
        low = round(min(last, open_price) * rng.uniform(0.85, 1.0), 2)
        bid = round(last - rng.uniform(0.01, 0.05), 2)
        ask = round(last + rng.uniform(0.01, 0.05), 2)
        vwap = round((last + open_price + high + low) / 4.0, 2)
        volume = int(rng.uniform(150_000, 8_500_000))
        return QuoteData(
            symbol=symbol,
            bid=bid,
            ask=ask,
            last=last,
            vwap=vwap,
            open=open_price,
            high=high,
            low=low,
            close=prev_close,
            volume=volume,
            timestamp_utc=None,
            data_quality_flags=("MOCK",),
        )

    def get_prev_close(self, symbol: str) -> Optional[float]:
        rng = _rng_for_symbol(symbol, self.seed)
        return round(rng.uniform(2.0, 10.0), 2)

    def get_intraday_stats(self, symbol: str) -> IntradayStats:
        rng = _rng_for_symbol(symbol, self.seed)
        avg_volume = int(rng.uniform(400_000, 3_500_000))
        current_volume = int(avg_volume * rng.uniform(5.0, 9.0))
        relative_volume = round(current_volume / avg_volume, 2) if avg_volume else None
        return IntradayStats(
            current_intraday_volume=current_volume,
            current_volume_source_label="MOCK",
            average_daily_volume_20d=avg_volume,
            average_daily_volume_window_days=20,
            relative_volume=relative_volume,
            relative_volume_category="HIGH" if relative_volume and relative_volume >= 3 else "NORMAL",
            volume_velocity_5m=int(rng.uniform(5_000, 150_000)),
            volume_velocity_15m=int(rng.uniform(10_000, 300_000)),
            volume_data_quality_flag="MOCK",
        )

    def get_float(self, symbol: str) -> Optional[int]:
        cached = self.float_cache.get(symbol)
        try:
            if cached is None:
                return None
            return int(cached)
        except Exception:
            return None
