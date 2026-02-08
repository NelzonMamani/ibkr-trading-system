# SOURCES OF TRUTH AND MODE RELATIVITY

## Core rule
Data truth is mode-relative, not absolute.

- LIVE may use IBKR real-time or frozen snapshots depending on market state and subscriptions.
- READ_ONLY may observe live feeds but must not execute orders.
- PAPER may use delayed/simulated feeds and order fills may be simulated or broker-provided.
- SIM may use historical bars, replay, or synthetic data.

M10 never asserts “data is wrong”. It asserts:
- what source was used
- what the system believed at the time
- what limitations apply

## Canonical source registry fields (minimum)
- source_id: e.g. IBKR_SNAPSHOT, IBKR_STREAM, HIST_BARS, CACHE_DB, FALLBACK_PROVIDER
- source_class: PRIMARY | DERIVED | CACHED | FALLBACK | SYNTHETIC
- expected_latency: REALTIME | DELAYED | UNKNOWN
- availability_constraints: subscriptions, trading hours, rate limits, outages

END
