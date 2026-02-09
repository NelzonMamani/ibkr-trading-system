# PR Verification Report

## Update — M2 Contract Registry Certification (2026-02-09)

### Summary
- Objective: certify M2 contract registry and add verification tooling.
- Status: compileall + pytest + verifier passed; audit evidence captured under M2 folder.

### Commands Run
1) `python -m compileall -q src > TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/M2_CONTRACT_REGISTRY/compileall.txt 2>&1`
2) `pytest -q tests/metadata -q > TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/M2_CONTRACT_REGISTRY/pytest.txt 2>&1`
3) `pytest -q > TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/M2_CONTRACT_REGISTRY/pytest_full.txt 2>&1`
4) `python verification_scripts/verify_m2_contract_registry.py --output-json TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/M2_CONTRACT_REGISTRY/verification_output.json --output-md TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/M2_CONTRACT_REGISTRY/verification_summary.md`

### Outputs Written
- `TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/M2_CONTRACT_REGISTRY/compileall.txt`
- `TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/M2_CONTRACT_REGISTRY/pytest.txt`
- `TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/M2_CONTRACT_REGISTRY/pytest_full.txt`
- `TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/M2_CONTRACT_REGISTRY/verification_output.json`
- `TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/M2_CONTRACT_REGISTRY/verification_summary.md`
- `TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/M2_CONTRACT_REGISTRY/certification_verdict.json`
- `TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/M2_CONTRACT_REGISTRY/contract_registry.json`
- `TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/M2_CONTRACT_REGISTRY/M2_EVIDENCE_INDEX.json`

### Verdict
- CERTIFIED

## Update — Mean Reversion Wiring (2026-02-02)

### Summary
- Objective: wire Mean Reversion strategy end-to-end and validate readiness across READ_ONLY/PAPER/LIVE.
- Status: compileall + pytest passed; READ_ONLY/PAPER smoke runs completed with IBKR connection warnings; LIVE smoke required termination because LIVE mode loops when market session is CLOSED.

### Mandatory Verification Commands (Mean Reversion)

1) Command:
```
python -m compileall src > output/verification/compileall_mean_reversion.log
```
Result: PASS

2) Command:
```
pytest -q > output/verification/pytest_mean_reversion.log
```
Result: PASS (warnings about IBKR connect coroutine)

3) Command:
```
pytest -q src/strategies/mean_reversion/tests > output/verification/pytest_mean_reversion_strategy_local.log
```
Result: PASS

4) Command:
```
python -m src.main --mode READ_ONLY --cycles 1 --strategy mean_reversion > output/verification/mean_reversion_READ_ONLY.log
```
Result: PASS (IBKR connection refused in this environment; fallback handled, no crash)

5) Command:
```
python -m src.main --mode PAPER --cycles 1 --strategy mean_reversion > output/verification/mean_reversion_PAPER.log
```
Result: PASS (IBKR connection refused in this environment; fallback handled, no crash)

6) Command:
```
python -m src.main --mode LIVE --cycles 1 --strategy mean_reversion > output/verification/mean_reversion_LIVE_smoke.log
```
Result: WARN (LIVE loop does not increment cycles when session is CLOSED; process was terminated after confirming startup wiring. Run during an open market session to complete.)

## Update — Ross Scanner Contract Lock (2026-01-30)

### Summary
- Objective: lock Ross scanner contract, enforce strategy-sourced request, and prevent live-mode MOCK fallback.
- Status: Python checks passed; IBKR connection-dependent commands ran but could not connect in this environment.

### Mandatory Verification Commands (Ross Scanner Contract Lock)

1) Command:
```
python -m compileall -q src
```
Result: PASS

2) Command:
```
pytest -q
```
Result: PASS (1 warning about IBKR connect coroutine)

3) Command:
```
$env:IBKR_PORT="7496"
python -m src.scanner.scanner_main --strategy ross_momentum --session PRE --topn 150
```
Result: WARN (IBKR connection refused in this environment; scanner emitted empty universe)
Excerpt:
```
[SCANNER][POLICY] source=STRATEGY policy_name=ROSS_MOMENTUM price=1.0-20.0 ...
[SCANNER][ENTRY] strategy=ROSS_MOMENTUM requested_top_n=150 watchlist_k=15 focus_m=5 universe=IBKR_TOP_GAINERS scan_code=TOP_PERC_GAIN instrument=STK location=STK.US.MAJOR above_price=1.0 below_price=20.0
[SCANNER][PROVIDER] provider=IBKR fallback_reason=[Errno 111] Connect call failed ('127.0.0.1', 7496)
WATCHLIST_K_SELECTED (K=0): []
```

4) Command:
```
$env:IBKR_PORT="7497"
python -m src.scanner.scanner_main --strategy ross_momentum --session PRE --topn 150
```
Result: WARN (IBKR connection refused in this environment; scanner emitted empty universe)
Excerpt:
```
[SCANNER][ENTRY] strategy=ROSS_MOMENTUM requested_top_n=150 watchlist_k=15 focus_m=5 universe=IBKR_TOP_GAINERS scan_code=TOP_PERC_GAIN instrument=STK location=STK.US.MAJOR above_price=1.0 below_price=20.0
[SCANNER][PROVIDER] provider=IBKR fallback_reason=[Errno 111] Connect call failed ('127.0.0.1', 7497)
WATCHLIST_K_SELECTED (K=0): []
```

5) Command:
```
$env:IBKR_PORT="7496"
python -m src.main --mode LIVE_READ_ONLY --cycles 1 --strategy ross_momentum
```
Result: WARN (IBKR connection refused in this environment; scanner emitted empty universe)
Excerpt:
```
[ORCH][SCANNER_REQUEST] strategy=ross_momentum policy=ROSS_MOMENTUM instrument=STK locationCode=STK.US.MAJOR scanCode=TOP_PERC_GAIN numberOfRows=150 abovePrice=1.0 belowPrice=20.0
[SCANNER][PROVIDER] provider=IBKR fallback_reason=[Errno 111] Connect call failed ('127.0.0.1', 7496)
WATCHLIST_K_SELECTED (K=0): []
```

6) Command:
```
python -m src.main --mode SIM --cycles 1 --strategy ross_momentum --session CLOSED
```
Result: PASS

---

## Summary
- Objective: verify traceability additions, supervised retry loop, and strategy-specific selection specs.
- Status: Required Python verification commands executed successfully; pytest emitted pre-existing mock-provider warnings.

## Log Directory
- `logs/`

---

## Mandatory Verification Commands

1) Command:
```
python -m compileall -q src
```
Result: PASS

2) Command:
```
pytest -q
```
Result: PASS (warnings about mock provider IBKR connect coroutine)
Excerpt:
```
127 passed, 7 skipped, 4 warnings in 11.46s
```

3) Command:
```
python -m src.main --mode SIM --cycles 1 --strategy ross_momentum
```
Result: PASS

4) Command:
```
python -m src.main --mode SIM --cycles 1 --strategy statistical_intraday_momentum
```
Result: PASS

---

## Sample Console Output (Trace Snapshots)

### Ross Momentum (SIM)
```
[TRACE] stage=UNIVERSE cycle_id=35b41169-3715-4dbb-b145-b703f222a222 run_mode=SIM strategy=ross_momentum top_n=50 symbols=['AAPL', 'MSFT', 'NVDA', 'AMD', 'TSLA', 'META', 'AMZN', 'GOOGL', 'NFLX', 'BABA', 'PLTR', 'RIVN', 'SNOW', 'CRWD', 'COIN', 'SOFI', 'LCID', 'NIO', 'MARA', 'RIOT', 'CLSK', 'GME', 'AMC', 'DKNG', 'ROKU', 'UPST', 'SHOP', 'AI', 'PATH', 'FUBO', 'SOUN', 'IONQ', 'AVGO', 'INTC', 'MU', 'TSM', 'ADBE', 'ORCL', 'QCOM', 'SPOT', 'UBER', 'LYFT', 'BA', 'GE', 'XOM', 'CVX', 'JPM', 'BAC', 'C', 'WFC']
[TRACE] stage=WATCHLIST cycle_id=35b41169-3715-4dbb-b145-b703f222a222 run_mode=SIM strategy=ross_momentum watchlist=15 symbols=['ROKU', 'SNOW', 'GME', 'NFLX', 'MU', 'BAC', 'PLTR', 'CVX', 'AMD', 'JPM', 'AAPL', 'MARA', 'CLSK', 'AMZN', 'RIOT'] drop_reasons={'DROP_RANK_BELOW_WATCHLIST': 35}
[TRACE] stage=FOCUS cycle_id=35b41169-3715-4dbb-b145-b703f222a222 run_mode=SIM strategy=ross_momentum focus=5 symbols=['GME', 'ROKU', 'MU', 'NFLX', 'SNOW']
```

### Statistical Intraday Momentum (SIM)
```
[TRACE] stage=UNIVERSE cycle_id=3acd49b3-b267-4d58-ac13-32cf54595056 run_mode=SIM strategy=statistical_intraday_momentum top_n=50 symbols=['AAPL', 'MSFT', 'NVDA', 'AMD', 'TSLA', 'META', 'AMZN', 'GOOGL', 'NFLX', 'BABA', 'PLTR', 'RIVN', 'SNOW', 'CRWD', 'COIN', 'SOFI', 'LCID', 'NIO', 'MARA', 'RIOT', 'CLSK', 'GME', 'AMC', 'DKNG', 'ROKU', 'UPST', 'SHOP', 'AI', 'PATH', 'FUBO', 'SOUN', 'IONQ', 'AVGO', 'INTC', 'MU', 'TSM', 'ADBE', 'ORCL', 'QCOM', 'SPOT', 'UBER', 'LYFT', 'BA', 'GE', 'XOM', 'CVX', 'JPM', 'BAC', 'C', 'WFC']
[TRACE] stage=WATCHLIST cycle_id=3acd49b3-b267-4d58-ac13-32cf54595056 run_mode=SIM strategy=statistical_intraday_momentum watchlist=20 symbols=['ROKU', 'GME', 'NFLX', 'BAC', 'CVX', 'AMD', 'AAPL', 'MARA', 'RIOT', 'RIVN', 'META', 'TSLA', 'PATH', 'GE', 'NVDA', '...'] drop_reasons={'DROP_PRICE_RANGE': 17, 'DROP_RANK_BELOW_WATCHLIST': 13}
[TRACE] stage=FOCUS cycle_id=3acd49b3-b267-4d58-ac13-32cf54595056 run_mode=SIM strategy=statistical_intraday_momentum focus=5 symbols=['BAC', 'NFLX', 'CVX', 'ROKU', 'GME']
```

---

## Trace Log Example

- JSONL path: `logs/trace_20260126.jsonl`
- Example line:
```
{"cycle_id": "3f1af660-416b-469a-9229-2412f1ccd60e", "payload": {"scan_request": {"requested_top_n": 50, "scan_code": "TOP_PERC_GAIN", "universe_source": "IBKR_TOP_GAINERS"}, "selection_spec": {"max_symbols_per_cycle": 50, "policy_name": "ROSS_MOMENTUM", "relaxed_gates": [], "session_allowlist": ["PRE", "REG", "AFTER"], "top_gainers_n": 50}, "universe": [{"gap_pct": 24.56, "last_price": 12.07, "pct_change": 24.56, "rank": 1, "rvol": 8.14, "spread_pct": 0.0058, "symbol": "AAPL", "volume": 27515675}, {"gap_pct": 13.94, "last_price": 7.93, "pct_change": 13.94, "rank": 2, "rvol": 5.49, "spread_pct": 0.005, "symbol": "MSFT", "volume": 12731375}, {"gap_pct": 20.81, "last_price": 11.61, "pct_change": 20.81, "rank": 3, "rvol": 7.21, "spread_pct": 0.0052, "symbol": "NVDA", "volume": 24154533}, {"gap_pct": 25.69, "last_price": 10.08, "pct_change": 25.69, "rank": 4, "rvol": 8.41, "spread_pct": 0.006, "symbol": "AMD", "volume": 22987348}, {"gap_pct": 22.0, "last_price": 10.15, "pct_change": 22.0, "rank": 5, "rvol": 7.49, "spread_pct": 0.0079, "symbol": "TSLA", "volume": 21329714}, {"gap_pct": 22.42, "last_price": 6.99, "pct_change": 22.42, "rank": 6, "rvol": 7.6, "spread_pct": 0.01, "symbol": "META", "volume": 13960964}, {"gap_pct": 22.96, "last_price": 3.91, "pct_change": 22.96, "rank": 7, "rvol": 7.73, "spread_pct": 0.0204, "symbol": "AMZN", "volume": 6621166}, {"gap_pct": 18.15, "last_price": 9.96, "pct_change": 18.15, "rank": 8, "rvol": 6.52, "spread_pct": 0.005, "symbol": "GOOGL", "volume": 18857628}, {"gap_pct": 27.66, "last_price": 7.2, "pct_change": 27.66, "rank": 9, "rvol": 8.92, "spread_pct": 0.0069, "symbol": "NFLX", "volume": 16144452}, {"gap_pct": 18.18, "last_price": 8.84, "pct_change": 18.18, "rank": 10, "rvol": 6.54, "spread_pct": 0.0034, "symbol": "BABA", "volume": 16503911}, {"gap_pct": 26.85, "last_price": 4.96, "pct_change": 26.85, "rank": 11, "rvol": 8.71, "spread_pct": 0.0141, "symbol": "PLTR", "volume": 9945212}, {"gap_pct": 22.57, "last_price": 11.08, "pct_change": 22.57, "rank": 12, "rvol": 7.64, "spread_pct": 0.0036, "symbol": "RIVN", "volume": 23904875}, {"gap_pct": 27.82, "last_price": 3.17, "pct_change": 27.82, "rank": 13, "rvol": 8.99, "spread_pct": 0.0283, "symbol": "SNOW", "volume": 5286581}, {"gap_pct": 21.54, "last_price": 4.57, "pct_change": 21.54, "rank": 14, "rvol": 7.41, "spread_pct": 0.0066, "symbol": "CRWD", "volume": 8027486}, {"gap_pct": 20.23, "last_price": 11.71, "pct_change": 20.23, "rank": 15, "rvol": 7.05, "spread_pct": 0.0026, "symbol": "COIN", "volume": 23953418}, {"gap_pct": 14.85, "last_price": 3.48, "pct_change": 14.85, "rank": 16, "rvol": 5.75, "spread_pct": 0.0144, "symbol": "SOFI", "volume": 4592370}, {"gap_pct": 15.89, "last_price": 8.17, "pct_change": 15.89, "rank": 17, "rvol": 5.99, "spread_pct": 0.0061, "symbol": "LCID", "volume": 14117645}, {"gap_pct": 15.52, "last_price": 7.07, "pct_change": 15.52, "rank": 18, "rvol": 5.88, "spread_pct": 0.0056, "symbol": "NIO", "volume": 11747831}, {"gap_pct": 23.5, "last_price": 10.67, "pct_change": 23.5, "rank": 19, "rvol": 7.87, "spread_pct": 0.0047, "symbol": "MARA", "volume": 23413407}, {"gap_pct": 22.87, "last_price": 8.65, "pct_change": 22.87, "rank": 20, "rvol": 7.7, "spread_pct": 0.0104, "symbol": "RIOT", "volume": 18135261}, {"gap_pct": 23.0, "last_price": 2.62, "pct_change": 23.0, "rank": 21, "rvol": 7.79, "spread_pct": 0.0269, "symbol": "CLSK", "volume": 3523423}, {"gap_pct": 27.81, "last_price": 12.5, "pct_change": 27.81, "rank": 22, "rvol": 8.94, "spread_pct": 0.0032, "symbol": "GME", "volume": 30534216}, {"gap_pct": 18.36, "last_price": 10.83, "pct_change": 18.36, "rank": 23, "rvol": 6.58, "spread_pct": 0.0074, "symbol": "AMC", "volume": 20867124}, {"gap_pct": 16.19, "last_price": 10.26, "pct_change": 16.19, "rank": 24, "rvol": 6.04, "spread_pct": 0.0088, "symbol": "DKNG", "volume": 18408138}, {"gap_pct": 27.89, "last_price": 12.15, "pct_change": 27.89, "rank": 25, "rvol": 8.97, "spread_pct": 0.0074, "symbol": "ROKU", "volume": 29655267}, {"gap_pct": 20.42, "last_price": 5.19, "pct_change": 20.42, "rank": 26, "rvol": 7.11, "spread_pct": 0.0135, "symbol": "UPST", "volume": 9210829}, {"gap_pct": 19.59, "last_price": 10.5, "pct_change": 19.59, "rank": 27, "rvol": 6.9, "spread_pct": 0.0029, "symbol": "SHOP", "volume": 20873985}, {"gap_pct": 16.21, "last_price": 5.52, "pct_change": 16.21, "rank": 28, "rvol": 6.07, "spread_pct": 0.009, "symbol": "AI", "volume": 8904396}, {"gap_pct": 21.49, "last_price": 9.27, "pct_change": 21.49, "rank": 29, "rvol": 7.37, "spread_pct": 0.0097, "symbol": "PATH", "volume": 19024157}, {"gap_pct": 12.32, "last_price": 4.74, "pct_change": 12.32, "rank": 30, "rvol": 5.09, "spread_pct": 0.0168, "symbol": "FUBO", "volume": 6424855}, {"gap_pct": 20.78, "last_price": 6.51, "pct_change": 20.78, "rank": 31, "rvol": 7.18, "spread_pct": 0.0031, "symbol": "SOUN", "volume": 12298089}, {"gap_pct": 13.46, "last_price": 5.48, "pct_change": 13.46, "rank": 32, "rvol": 5.39, "spread_pct": 0.0091, "symbol": "IONQ", "volume": 8057223}, {"gap_pct": 15.74, "last_price": 6.69, "pct_change": 15.74, "rank": 33, "rvol": 5.93, "spread_pct": 0.0075, "symbol": "AVGO", "volume": 11061161}, {"gap_pct": 19.73, "last_price": 3.58, "pct_change": 19.73, "rank": 34, "rvol": 6.96, "spread_pct": 0.0139, "symbol": "INTC", "volume": 5467061}, {"gap_pct": 27.27, "last_price": 4.2, "pct_change": 27.27, "rank": 35, "rvol": 8.8, "spread_pct": 0.0095, "symbol": "MU", "volume": 7956142}, {"gap_pct": 15.88, "last_price": 8.83, "pct_change": 15.88, "rank": 36, "rvol": 5.98, "spread_pct": 0.0045, "symbol": "TSM", "volume": 15392467}, {"gap_pct": 19.75, "last_price": 2.85, "pct_change": 19.75, "rank": 37, "rvol": 6.97, "spread_pct": 0.014, "symbol": "ADBE", "volume": 3805094}, {"gap_pct": 16.93, "last_price": 8.01, "pct_change": 16.93, "rank": 38, "rvol": 6.22, "spread_pct": 0.005, "symbol": "ORCL", "volume": 14161925}, {"gap_pct": 17.84, "last_price": 6.01, "pct_change": 17.84, "rank": 39, "rvol": 6.48, "spread_pct": 0.0067, "symbol": "QCOM", "volume": 10373831}, {"gap_pct": 21.53, "last_price": 4.12, "pct_change": 21.53, "rank": 40, "rvol": 7.35, "spread_pct": 0.0097, "symbol": "SPOT", "volume": 6909951}, {"gap_pct": 20.77, "last_price": 4.71, "pct_change": 20.77, "rank": 41, "rvol": 7.21, "spread_pct": 0.017, "symbol": "UBER", "volume": 8187184}, {"gap_pct": 15.14, "last_price": 5.17, "pct_change": 15.14, "rank": 42, "rvol": 5.76, "spread_pct": 0.0039, "symbol": "LYFT", "volume": 7849706}, {"gap_pct": 15.43, "last_price": 4.34, "pct_change": 15.43, "rank": 43, "rvol": 5.89, "spread_pct": 0.0115, "symbol": "BA", "volume": 6380119}, {"gap_pct": 21.02, "last_price": 7.83, "pct_change": 21.02, "rank": 44, "rvol": 7.26, "spread_pct": 0.0051, "symbol": "GE", "volume": 15490488}, {"gap_pct": 12.8, "last_price": 2.82, "pct_change": 12.8, "rank": 45, "rvol": 5.17, "spread_pct": 0.0106, "symbol": "XOM", "volume": 3073980}, {"gap_pct": 26.3, "last_price": 8.5, "pct_change": 26.3, "rank": 46, "rvol": 8.59, "spread_pct": 0.0082, "symbol": "CVX", "volume": 19160381}, {"gap_pct": 24.91, "last_price": 3.51, "pct_change": 24.91, "rank": 47, "rvol": 8.26, "spread_pct": 0.017, "symbol": "JPM", "volume": 5891085}, {"gap_pct": 26.93, "last_price": 11.69, "pct_change": 26.93, "rank": 48, "rvol": 8.74, "spread_pct": 0.006, "symbol": "BAC", "volume": 27946342}, {"gap_pct": 17.43, "last_price": 4.85, "pct_change": 17.43, "rank": 49, "rvol": 6.36, "spread_pct": 0.0185, "symbol": "C", "volume": 7808369}, {"gap_pct": 13.83, "last_price": 3.21, "pct_change": 13.83, "rank": 50, "rvol": 5.43, "spread_pct": 0.0125, "symbol": "WFC", "volume": 3885582}]}, "run_mode": "SIM", "stage": "UNIVERSE", "strategy": "ross_momentum", "timestamp": "2026-01-26T18:52:52.780088+00:00"}
```

---

## Update — Statistical Intraday Momentum Enablement (2026-01-29)

### Commands Executed
1) `git status --short`
   - Result: working tree contained only tracked source changes after cleanup.

2) `python -m compileall -q src`
   - Result: PASS

3) `pytest -q`
   - Result: PASS (warnings about mock provider IBKR connect coroutine)

4) `python -m src.main --mode SIM --cycles 1 --strategy ross_momentum`
   - Result: PASS

5) `python -m src.main --mode LIVE_READ_ONLY --cycles 1 --strategy ross_momentum`
   - Result: PASS (IBKR connection refused; fallback handled, no crash)

6) `python -m src.main --mode SIM --cycles 1 --strategy statistical_intraday_momentum`
   - Result: PASS (strategy enabled, intents emitted in SIM with focus_m)

7) `python -m src.main --mode LIVE_READ_ONLY --cycles 1 --strategy statistical_intraday_momentum`
   - Result: PASS (scan-only; session gating retained)

8) `python -m src.main --mode PAPER --cycles 1 --strategy statistical_intraday_momentum`
   - Result: PASS (IBKR connection refused; fallback handled, no crash)

### What Changed
- Enabled statistical strategy when selected, with clear config resolution log.
- Added minimal Statistical Intraday Momentum policy decision path to produce TradeIntents in SIM and respect data quality gates in PAPER/LIVE_READ_ONLY.
- Ensured focus_m is used for statistical strategy evaluation and registered STRATEGY_INTERFACE_INTENTS schema.
- Hardened IBKR connection fallback defaults and trace timeline emit handling.

### Why It’s Safe
- RossMomentum selection, outputs, and gating remain unchanged; all changes are additive and strategy-scoped.
- PAPER/LIVE_READ_ONLY remain scan-only or intent-only with explicit data-quality and session gates; no IBKR orders emitted when data is MOCK or when mode disallows execution.

### Intentional Log Changes
- New `[CONFIG] Selected strategy=statistical_intraday_momentum; forcing STATISTICAL_INTRADAY_MOMENTUM_STRATEGY_ENABLED=True` line when strategy is selected.
- Statistical strategy logs now include SIM override notice when session is outside REG, along with intent signal summaries in SIM.
