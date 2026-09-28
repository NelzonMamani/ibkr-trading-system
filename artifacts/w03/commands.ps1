# Recorded W03 invocations. The single live session is already complete; do not rerun its provider call as part of closure.
$newsPython = 'C:\tmp\pr1091-cert-env-20260923\Scripts\python.exe'
$newsRepo = 'C:\Users\nelzo\.codex\worktrees\w01-consolidation\ibkr-trading-system'
Set-Location -LiteralPath $newsRepo

# Executed affected test supervisor; full command/module list in affected_status.json.
& $newsPython .\artifacts\w03\run_affected.py

# Executed ONCE in the bounded live session. Dedicated request/cache/prep paths are recorded in live_batch.json.
& $newsPython .\scripts\diagnostics\w03_news_acceptance.py

# Executed supported single-symbol command; zero sources attempted, no provider call.
& $newsPython .\scripts\verify_news_discovery.py --candidates-file .\output\w03\live\single_candidate.json --lookback-hours 24 --cache-mode only --cache-file .\output\w03\live\news_cache.json --prep-file .\output\w03\live\empty_prep.json --budget-seconds 30 --request-timeout-seconds 5 --cleanup-seconds 10 --json-output .\artifacts\w03\cached_single.json --format json 1> .\artifacts\w03\cached_single_stdout.json 2> .\artifacts\w03\cached_single_stderr.log

# Executed one stable local full suite, with compileall and connection guard.
& $newsPython .\artifacts\w03\run_final_suite.py

# Usage examples, NOT additional W03 live provider calls:
# One ticker with issuer identity.
# & $newsPython .\scripts\verify_news_discovery.py IRON --company-name 'Disc Medicine, Inc.' --alias 'Disc Medicine' --lookback-hours 24 --budget-seconds 30 --request-timeout-seconds 5 --cache-mode refresh --cache-file .\output\news_lookup\news_cache.json
# List of tickers; use --candidates-file for batch issuer identities.
# & $newsPython .\scripts\verify_news_discovery.py IRON MSFT LFCR --lookback-hours 24 --budget-seconds 30 --request-timeout-seconds 5 --cache-mode use --cache-file .\output\news_lookup\news_cache.json --format json
