from __future__ import annotations

import json
import shutil
import sqlite3
import time
from pathlib import Path

from src.config.runtime_config import get_persistence_sqlite_path
from src.data.float_discovery_worker import get_float_discovery_worker
from src.scanner import scanner_runner


def main() -> int:
    cache_path = Path("data/reference/float_cache.json")
    print(f"[VERIFY][FLOAT] canonical_cache_path={cache_path.resolve()}")

    backup_path = cache_path.with_suffix(".json.bak_verify_float_wiring")
    if cache_path.exists():
        shutil.copy2(cache_path, backup_path)
        cache_path.unlink()
        print(f"[VERIFY][FLOAT] backed_up_existing_cache={backup_path.resolve()}")
    else:
        print("[VERIFY][FLOAT] no_existing_cache_to_backup")

    symbols = ["ZZZT1", "ZZZT2"]
    expected = {"ZZZT1": 5_910_303, "ZZZT2": 19_626_616}
    try:
        print(f"[VERIFY][FLOAT] requesting_discovery symbols={symbols}")

        worker = get_float_discovery_worker(cache_path)

        def fake_yahoo(symbol: str):
            value = expected.get(str(symbol).upper())
            if value is None:
                return None, "MISSING_TEST_SYMBOL"
            return value, "OK"

        worker._provider.provider_yahoo = fake_yahoo  # type: ignore[attr-defined]
        worker._provider.provider_finviz = lambda symbol: (None, "TEST_DISABLED")  # type: ignore[attr-defined]

        for symbol in symbols:
            queued = worker.enqueue(symbol)
            print(f"[VERIFY][FLOAT] enqueue symbol={symbol} queued={queued}")

        deadline = time.time() + 10
        while time.time() < deadline:
            if not getattr(worker, "_queued", set()):
                break
            time.sleep(0.2)

        cache_exists = cache_path.exists()
        print(f"[VERIFY][FLOAT] cache_exists={cache_exists}")
        if not cache_exists:
            print("[VERIFY][FLOAT] FAIL reason=cache_not_created")
            return 1

        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        print(f"[VERIFY][FLOAT] cache_symbols={sorted(payload.keys())}")

        persisted = [s for s in symbols if isinstance(payload.get(s), dict) and payload[s].get("float")]
        print(f"[VERIFY][FLOAT] persisted_symbols={persisted}")

        sqlite_path = Path(get_persistence_sqlite_path(default="data/ibkr_system.db"))
        db_hits: list[str] = []
        if sqlite_path.exists():
            with sqlite3.connect(sqlite_path) as conn:
                for symbol in symbols:
                    row = conn.execute(
                        "SELECT float, source FROM symbol_fundamentals WHERE symbol = ?",
                        (symbol,),
                    ).fetchone()
                    if row is not None:
                        db_hits.append(symbol)
            print(f"[VERIFY][FLOAT] sqlite_path={sqlite_path.resolve()} sqlite_hits={db_hits}")
        else:
            print(f"[VERIFY][FLOAT] sqlite_path_missing={sqlite_path.resolve()}")

        class _DummyProvider:
            pass

        normalized = scanner_runner._bootstrap_float_cache(symbols, _DummyProvider())
        provenance_ok = any(
            isinstance(normalized.get(symbol), dict)
            and normalized[symbol].get("float_value") == expected[symbol]
            and normalized[symbol].get("float_source") == "YAHOO"
            for symbol in symbols
        )
        print(f"[VERIFY][FLOAT] scanner_provenance_ok={provenance_ok}")

        passed = cache_exists and bool(persisted) and provenance_ok
        print("[VERIFY][FLOAT] PASS" if passed else "[VERIFY][FLOAT] FAIL")
        return 0 if passed else 1
    finally:
        if backup_path.exists():
            if cache_path.exists():
                cache_path.unlink()
            shutil.move(str(backup_path), str(cache_path))
            print(f"[VERIFY][FLOAT] restored_original_cache={cache_path.resolve()}")


if __name__ == "__main__":
    raise SystemExit(main())
