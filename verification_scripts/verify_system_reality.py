"""
verify_system_reality.py

Single-shot, authoritative system reality check.
NO side effects. NO trades. READ-ONLY introspection.

Purpose:
- Eliminate guessing
- Prove whether PAPER trading is even architecturally possible
"""

import os
import sqlite3
import pkgutil
import inspect
import json
from datetime import datetime

REPORT = {
    "timestamp_utc": datetime.utcnow().isoformat(),
    "runtime": {},
    "execution_layer": {},
    "strategy_layer": {},
    "strategy_runner": {},
    "database": {},
    "verdict": {},
}

# -------------------------------------------------
# 1️⃣ Runtime truth
# -------------------------------------------------
try:
    from src.config.runtime_config import get_config

    REPORT["runtime"] = {
        "RUN_MODE": get_config("RUN_MODE"),
        "EXECUTION_ENABLED": get_config("EXECUTION_ENABLED"),
        "IBKR_READONLY_ENABLED": get_config("IBKR_READONLY_ENABLED"),
        "LIVE_MICRO_1_SHARE_ONLY": get_config("LIVE_MICRO_1_SHARE_ONLY"),
    }
except Exception as e:
    REPORT["runtime"]["error"] = str(e)

# -------------------------------------------------
# 2️⃣ Execution layer reality
# -------------------------------------------------
try:
    import src.execution as execution_pkg

    execution_modules = [
        m.name
        for m in pkgutil.walk_packages(
            execution_pkg.__path__, execution_pkg.__name__ + "."
        )
    ]

    REPORT["execution_layer"]["modules"] = execution_modules

    try:
        from src.execution.execution_engine import ExecutionEngine
        engine = ExecutionEngine()
        REPORT["execution_layer"]["engine_instantiated"] = True
    except Exception as e:
        REPORT["execution_layer"]["engine_instantiated"] = False
        REPORT["execution_layer"]["engine_error"] = str(e)

except Exception as e:
    REPORT["execution_layer"]["error"] = str(e)

# -------------------------------------------------
# 3️⃣ Ross strategy inspection
# -------------------------------------------------
try:
    from src.strategies.ross_momentum import strategy_policy as ross_policy

    classes = {
        name: obj
        for name, obj in vars(ross_policy).items()
        if inspect.isclass(obj)
    }

    REPORT["strategy_layer"]["ross_classes"] = list(classes.keys())

    ross_policy_src = inspect.getsource(ross_policy)
    REPORT["strategy_layer"]["ross_policy_length_lines"] = len(
        ross_policy_src.splitlines()
    )

except Exception as e:
    REPORT["strategy_layer"]["error"] = str(e)

# -------------------------------------------------
# 4️⃣ StrategyRunner bridge
# -------------------------------------------------
try:
    from src.execution.strategy_runner import StrategyRunner

    runner_src = inspect.getsource(StrategyRunner)

    REPORT["strategy_runner"] = {
        "exists": True,
        "length_lines": len(runner_src.splitlines()),
        "mentions_execution": "Execution" in runner_src or "execution" in runner_src,
    }

except Exception as e:
    REPORT["strategy_runner"] = {
        "exists": False,
        "error": str(e),
    }

# -------------------------------------------------
# 5️⃣ Database ground truth
# -------------------------------------------------
try:
    db_path = os.path.join("data", "ibkr_system.db")
    REPORT["database"]["path"] = db_path
    REPORT["database"]["exists"] = os.path.exists(db_path)

    if os.path.exists(db_path):
        con = sqlite3.connect(db_path)
        cur = con.cursor()

        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in cur.fetchall()]
        REPORT["database"]["tables"] = tables

        def count(table):
            try:
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                return cur.fetchone()[0]
            except Exception:
                return None

        REPORT["database"]["counts"] = {
            "events": count("events"),
            "trades": count("trades"),
            "trade_records": count("trade_records"),
            "execution_results": count("execution_results"),
            "watchlists": count("watchlists"),
        }

        con.close()

except Exception as e:
    REPORT["database"]["error"] = str(e)

# -------------------------------------------------
# 6️⃣ Final verdict
# -------------------------------------------------
execution_possible = (
    REPORT["runtime"].get("EXECUTION_ENABLED") is True
    and REPORT["execution_layer"].get("engine_instantiated") is True
)

has_trade_history = (
    REPORT["database"].get("counts", {}).get("trades", 0) not in (None, 0)
)

REPORT["verdict"] = {
    "paper_execution_architecturally_possible": execution_possible,
    "any_trades_ever_recorded": has_trade_history,
    "status": (
        "READY_FOR_PAPER_TRADING"
        if execution_possible
        else "EXECUTION_PATH_BROKEN"
    ),
}

# -------------------------------------------------
# OUTPUT
# -------------------------------------------------
print("\n=== SYSTEM REALITY REPORT ===")
print(json.dumps(REPORT, indent=2))
