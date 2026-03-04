# IBKR Trading System

A modular, multi-strategy algorithmic trading system designed for Interactive Brokers (IBKR).

## Implemented Strategies

- Ross Momentum — Intraday momentum trading (LIVE)
- Statistical Intraday Momentum — Quantitative intraday continuation/reversion (PAPER/LIVE)
- Long Horizon Value — Fundamental investing (execution locked)
- Mean Reversion — Intraday exhaustion-based mean reversion (implemented, execution locked)

Mean Reversion is governed, tested, and integrated, but not yet enabled for live execution.

Refer to SYSTEM_STATE.md for authoritative runtime status.

## Paper Open Smoke Trade Command (P01–P04)

Run the full PAPER open smoke path (scan → watchlist → runners → intents → risk gate → single order submit → audit artifacts):

```bash
scripts/run_paper_open_smoke_trade.sh
```

The verification script writes evidence to:

`TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/paper_open_smoke_trade/<timestamp>/`
