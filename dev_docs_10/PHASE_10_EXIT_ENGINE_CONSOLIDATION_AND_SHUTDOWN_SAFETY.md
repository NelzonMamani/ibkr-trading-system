PHASE_10_EXIT_ENGINE_CONSOLIDATION_AND_SHUTDOWN_SAFETY.md

PHASE 10 — REAL TRADE LIFECYCLES
STEP 10.6 — CENTRALIZED EXIT PRECEDENCE + GUARANTEED SHUTDOWN CLEANUP

OBJECTIVE
---------
Fix all remaining Phase 10 issues by making TradeExitEngine the single authority
for trade exits, enforcing strict exit precedence, registering missing event
schemas, and guaranteeing zero active trades at shutdown.

After this step:
- No trade may remain open at shutdown
- No component except TradeExitEngine may close trades
- Exit logic must be deterministic and replay-safe
- Phase 10 must be structurally complete and stable

NON-NEGOTIABLE RULES
-------------------
1. Strategies MAY NOT close trades
2. Strategies MAY ONLY emit exit signals
3. TradeExitEngine decides AND executes all exits
4. Exit precedence MUST be centralized in TradeExitEngine
5. Shutdown MUST force-close all remaining trades
6. Registry MUST verify zero active trades at shutdown

IMPLEMENTATION TASKS
--------------------

1) ADD CENTRAL EXIT DECISION LOGIC

File: src/core/trade_exit_engine.py

Add a single authoritative method:

```python
def decide_exit(
    self,
    trade,
    current_tick: int,
    current_price: float,
    strategy_exit_signal: bool,
    config,
):
    """
    Authoritative exit decision.
    Returns ExitDecision or None (HOLD).
    """

    # 1. HARD TIME EXIT (max hold)
    if trade.hold_duration(current_tick) >= config.MAX_HOLD_TICKS:
        return ExitDecision(
            category="TIME_MAX",
            reason="Max hold duration reached",
            exit_tick=current_tick,
            exit_price=current_price,
        )

    # 2. STOP LOSS
    if trade.stop_loss_price is not None and current_price <= trade.stop_loss_price:
        return ExitDecision(
            category="PRICE_STOP",
            reason="Stop loss breached",
            exit_tick=current_tick,
            exit_price=current_price,
        )

    # 3. TAKE PROFIT
    if trade.take_profit_price is not None and current_price >= trade.take_profit_price:
        return ExitDecision(
            category="PRICE_TP",
            reason="Take profit reached",
            exit_tick=current_tick,
            exit_price=current_price,
        )

    # 4. MIN HOLD PROTECTION (blocks strategy exits)
    if trade.hold_duration(current_tick) < config.MIN_HOLD_TICKS:
        return None

    # 5. STRATEGY REQUESTED EXIT
    if strategy_exit_signal:
        return ExitDecision(
            category="STRATEGY_SIGNAL",
            reason="Strategy requested exit",
            exit_tick=current_tick,
            exit_price=current_price,
        )

    return None
