# FILE: verification_scripts/verify_db_readiness.py
# TITLE: DB readiness: tables + last runs/cycles/events/watchlists/trades (no scanner_symbol_state assumption)

import sqlite3
from pathlib import Path
from typing import Dict, Any, List, Tuple

def _q(cur, sql: str, params: Tuple = ()) -> List[Tuple]:
    cur.execute(sql, params)
    return cur.fetchall()

def verify_db_readiness(db_path: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {"status": "PASS", "details": {}}
    p = Path(db_path)
    if not p.exists():
        return {"status": "FAIL", "details": {"reason": f"DB not found: {db_path}"}}

    con = sqlite3.connect(str(p))
    cur = con.cursor()

    tables = _q(cur, "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    table_names = [t[0] for t in tables]

    # Minimal expected core tables (based on your verify_db output)
    expected = {
        "schema_meta", "runs", "cycles", "events", "watchlists",
        "trades", "trade_records", "execution_results"
    }
    missing = sorted(list(expected - set(table_names)))

    # Pull last few rows from key tables if present
    details: Dict[str, Any] = {
        "db_path": str(p),
        "tables": table_names,
        "missing_expected_tables": missing,
    }

    def tail(table: str, cols: str, order_col: str = "id", limit: int = 5):
        if table not in table_names:
            return None
        return _q(cur, f"SELECT {cols} FROM {table} ORDER BY {order_col} DESC LIMIT {limit}")

    details["tail_runs"] = tail("runs", "id, started_utc, run_mode, status", "id", 5)
    details["tail_cycles"] = tail("cycles", "id, run_id, started_utc, status", "id", 5)
    details["tail_events"] = tail("events", "id, event_type, created_utc, source", "id", 10)
    details["tail_watchlists"] = tail("watchlists", "id, created_utc, session, count, strategy", "id", 10)
    details["tail_trades"] = tail("trades", "id, created_utc, symbol, side, qty, status", "id", 10)
    details["tail_trade_records"] = tail("trade_records", "id, created_utc, symbol, action, qty, status", "id", 10)

    # Hard FAIL criteria: if DB exists but nothing is being recorded at all
    if details["tail_runs"] is None and details["tail_events"] is None:
        out["status"] = "FAIL"
        details["reason"] = "DB exists but core tables not readable / missing"
    elif details["tail_events"] is not None and len(details["tail_events"]) == 0:
        out["status"] = "FAIL"
        details["reason"] = "DB has events table but it's empty (system not writing events?)"

    out["details"] = details
    con.close()
    return out
# END
