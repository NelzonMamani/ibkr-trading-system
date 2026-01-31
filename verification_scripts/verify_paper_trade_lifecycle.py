#!/usr/bin/env python3
"""
verify_paper_trade_lifecycle.py

Purpose:
    Verifies that PAPER mode can execute a full trade lifecycle:
    ENTRY -> POSITION OPEN -> EXIT (simulated)

This is the single most important verification for tradability.

What this proves:
    - PAPER runtime is wired correctly
    - ExecutionEngine accepts intents
    - Trades are persisted
    - Exit logic runs
    - No IBKR dependency exists

If this fails:
    The system CANNOT trade, regardless of strategy or scanner correctness.
"""

import os
import sys
import time
from datetime import datetime, timezone

# ---------------------------------------------------------------------
# Force PAPER runtime (hard override – no guessing)
# ---------------------------------------------------------------------
os.environ["RUN_MODE"] = "PAPER"
os.environ["EXECUTION_ENABLED"] = "True"
os.environ["IBKR_READONLY_ENABLED"] = "False"
os.environ["IBKR_ORDER_SUBMISSION_ENABLED"] = "False"
os.environ["IBKR_MARKET_DATA_TYPE"] = "DELAYED"
os.environ["EVENT_REPLAY_MODE"] = "OFF"

# ---------------------------------------------------------------------
# Imports (after env lock)
# ---------------------------------------------------------------------
from src.core.orchestrator import CoreOrchestrator
from src.storage.storage_engine import StorageEngine
from src.execution.intent import TradeIntent

# ---------------------------------------------------------------------
# Test constants
# ---------------------------------------------------------------------
TEST_SYMBOL = "AAPL"
TEST_QTY = 10
TEST_PRICE = 100.0

# ---------------------------------------------------------------------
def fail(msg: str):
    print(f"[FAIL] {msg}")
    sys.exit(1)


def ok(msg: str):
    print(f"[OK] {msg}")


# ---------------------------------------------------------------------
def main():
    print("\n=== PAPER TRADE LIFECYCLE VERIFICATION ===\n")

    # -------------------------------------------------------------
    # 1. Boot orchestrator in PAPER mode
    # -------------------------------------------------------------
    orch = CoreOrchestrator()

    if orch.runtime.mode != "PAPER":
        fail(f"Runtime mode is {orch.runtime.mode}, expected PAPER")

    if not orch.runtime.allow_orders:
        fail("PAPER runtime does not allow orders")

    ok("PAPER runtime active and allows orders")

    # -------------------------------------------------------------
    # 2. Create a synthetic trade intent (bypass scanner & strategy)
    # -------------------------------------------------------------
    intent = TradeIntent(
        strategy_key="verification",
        symbol=TEST_SYMBOL,
        side="BUY",
        qty=TEST_QTY,
        order_type="MARKET",
        price_hint=TEST_PRICE,
        timestamp_utc=datetime.now(timezone.utc),
        metadata={"source": "verify_paper_trade_lifecycle"}
    )

    ok("Synthetic trade intent created")

    # -------------------------------------------------------------
    # 3. Submit intent directly to ExecutionEngine
    # -------------------------------------------------------------
    exec_engine = orch.execution_engine

    if exec_engine is None:
        fail("ExecutionEngine not initialised")

    exec_engine.submit_intents([intent])

    ok("Trade intent submitted to ExecutionEngine")

    # -------------------------------------------------------------
    # 4. Allow execution loop to process
    # -------------------------------------------------------------
    time.sleep(1.5)

    # -------------------------------------------------------------
    # 5. Verify trade exists in DB
    # -------------------------------------------------------------
    db = StorageEngine()

    trades = db.fetch_all("""
        SELECT symbol, side, qty, status
        FROM trades
        WHERE symbol = ?
        ORDER BY created_utc DESC
        LIMIT 1
    """, (TEST_SYMBOL,))

    if not trades:
        fail("No trade record found in DB after submission")

    symbol, side, qty, status = trades[0]

    ok(f"Trade recorded in DB: {symbol} {side} {qty} status={status}")

    # -------------------------------------------------------------
    # 6. Force exit (simulate strategy exit / stop)
    # -------------------------------------------------------------
    exec_engine.force_flatten_symbol(TEST_SYMBOL)

    time.sleep(1.0)

    exits = db.fetch_all("""
        SELECT symbol, status
        FROM trades
        WHERE symbol = ?
        ORDER BY updated_utc DESC
        LIMIT 1
    """, (TEST_SYMBOL,))

    if not exits:
        fail("Trade disappeared after exit attempt")

    _, exit_status = exits[0]

    if exit_status not in ("CLOSED", "EXITED", "FLAT"):
        fail(f"Trade did not close correctly, status={exit_status}")

    ok(f"Trade exited successfully, status={exit_status}")

    # -------------------------------------------------------------
    print("\n=== PAPER TRADE LIFECYCLE: PASS ===\n")
    return 0


# ---------------------------------------------------------------------
if __name__ == "__main__":
    sys.exit(main())
