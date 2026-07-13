# PR1046 IBKR Market-Data Diagnostic

PR1046 is a diagnostics/runbook change for the remaining real READ_ONLY observation blocker identified after PR1045. The bounded PR1040 adapter can fail closed, but the observed runtime evidence showed IBKR market data was unusable before Focus M pattern evaluation:

- `classification=INSUFFICIENT_EVIDENCE`
- `paper_ready=NO`
- `paper_readiness_gate=FAIL`
- `zero_broker_order_mutations=true`
- `read_only_full_strategy_observation_captured=false`
- `candidate_count=50`
- `watchlist_k_count=15`
- `focus_m_count=0`
- `dominant_drop_reason=DROP_MISSING_PRICE`
- `market_data_observation_diagnostics.outcome=REAL_MARKET_DATA_UNUSABLE`

The IBKR failures to diagnose are:

- `10089`: requested market data requires an additional subscription for API access.
- `10167`: requested market data is not subscribed; IBKR may display delayed market data.
- Raw quote fields such as `last`, `close`, `volume`, `bid`, and `ask` may remain `None`, causing scanner drops such as `DATA_QUALITY_FAIL_SNAPSHOT` and `DROP_MISSING_PRICE`.

## Safety Scope

PR1046 does not enable PAPER or LIVE trading. It does not submit, cancel, modify, preview, or stage orders. It does not touch execution order paths, relax Ross gates, alter thresholds, use manual focus, use synthetic trade intents, create fake quote data, create fake Focus M rows, or create fake pattern inputs.

The expected certification posture remains:

- `PAPER_READY=NO`
- `PAPER_READINESS_GATE=FAIL`

## Classifications

The PR1046 diagnostic block can classify IBKR market-data evidence as:

- `MARKET_DATA_SUBSCRIPTION_REQUIRED`: IBKR error `10089` or equivalent additional-subscription evidence was observed.
- `MARKET_DATA_NOT_SUBSCRIBED`: IBKR error `10167` or equivalent not-subscribed evidence was observed.
- `DELAYED_DATA_AVAILABLE_BUT_UNUSABLE`: IBKR delayed-data evidence was observed, but required quote fields were still missing or non-positive.
- `SNAPSHOT_TIMEOUT`: snapshot timeout or `DATA_QUALITY_FAIL_SNAPSHOT` evidence was observed.
- `SNAPSHOT_FIELDS_MISSING`: scanner rows exist, but one or more required quote fields are missing or non-positive.
- `MARKET_DATA_USABLE`: at least one scanner row has usable `last`, `close`, `volume`, `bid`, and `ask` fields and no known IBKR market-data error is present.
- `MARKET_DATA_DIAGNOSTIC_UNKNOWN`: the available evidence does not match a known IBKR market-data failure or usable quote pattern.

Storage proof alone is never enough for READ_ONLY observation validity. Market-data usability only means the quote evidence is usable enough to continue through the existing scanner/Ross gates.

## Observation Output

The PR1040/PR1045 observation JSON now includes an IBKR-specific nested block under `market_data_observation_diagnostics`:

```json
{
  "market_data_observation_diagnostics": {
    "outcome": "REAL_MARKET_DATA_UNUSABLE",
    "ibkr_market_data_diagnostic": {
      "provider": "IBKR",
      "classification": "MARKET_DATA_SUBSCRIPTION_REQUIRED",
      "observed_error_codes": [10089],
      "ibkr_market_data_error_event_count": 1,
      "ibkr_market_data_error_events": [
        {
          "code": 10089,
          "message": "Requested market data requires additional subscription for API",
          "symbol": "MISS1",
          "source": "IBKR_ERROR_EVENT",
          "raw_event": {
            "code": 10089,
            "message": "Requested market data requires additional subscription for API",
            "symbol": "MISS1"
          }
        }
      ],
      "paper_ready": "NO",
      "paper_readiness_gate": "FAIL"
    }
  }
}
```

The nested block records observed error codes/messages, persisted IBKR market-data error events, required quote-field aliases, missing fields by symbol, symbols with complete quote fields, drop-reason counts, requested market-data type, scanner mode, READ_ONLY runtime status, likely causes, and operator next steps.

`ibkr_market_data_error_events` preserves normalized event fields plus a JSON-safe `raw_event` copy of the source event or legacy diagnostic summary. Older artifacts with only summarized `observed_error_codes`, `observed_error_messages`, and `symbols_by_error_code` can be reprocessed by the probe to produce the persisted event list.

## Diagnostics Probe

The optional probe classifies already-captured evidence. It does not connect to IBKR or mutate broker state.

```powershell
python scripts/certification/pr1046_ibkr_market_data_diagnostic_probe.py `
  --scanner-payload artifacts/certification/pr1040/real_runtime_observation/scanner_payload.json `
  --output artifacts/certification/pr1046/ibkr_market_data_diagnostic.json `
  --operator OPERATOR_ID
```

For an existing PR1040/PR1045 observation input:

```powershell
python scripts/certification/pr1046_ibkr_market_data_diagnostic_probe.py `
  --observation-input artifacts/certification/pr1040/real_runtime_observation/real_runtime_observation.json `
  --output artifacts/certification/pr1046/ibkr_market_data_diagnostic.json `
  --operator OPERATOR_ID
```

## Operator Runbook

1. Confirm TWS/Gateway is connected for the same account used by the READ_ONLY adapter.
2. Confirm API access is enabled in TWS/Gateway.
3. Confirm the IBKR account has exchange/API market-data subscriptions for the requested symbols and security types.
4. Check the TWS/Gateway market-data type setting. Delayed data must not be used as PAPER readiness proof.
5. Re-run the bounded READ_ONLY adapter after correcting market-data configuration.
6. Validate the observation input with the PR1039 producer.
7. Keep `PAPER_READY=NO` and `PAPER_READINESS_GATE=FAIL` until full observation evidence and human review pass.
