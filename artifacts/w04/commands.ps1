# W04 verification commands; no API calls without a locally configured key.
$newsPython = 'C:\tmp\pr1091-cert-env-20260923\Scripts\python.exe'
$newsRepo = 'C:\Users\nelzo\.codex\worktrees\w01-consolidation\ibkr-trading-system'
Set-Location -LiteralPath $newsRepo

# Run on the stable implementation; guard prevents provider/broker connections.
& $newsPython .\artifacts\w04\run_verification.py affected
# Run once locally after affected checks pass; later review repairs use affected checks and CI.
& $newsPython .\artifacts\w04\run_verification.py full

# These supported commands are captured with no key configured. They must make zero HTTP requests.
& $newsPython .\scripts\verify_news_discovery.py IRON --company-name 'Disc Medicine, Inc.' --alias 'Disc Medicine' --provider massive --published-after '2026-09-27T22:08:37.432754Z' --published-before '2026-09-28T22:08:37.432754Z' --cache-mode off --json-output .\artifacts\w04\missing_key_single.json --format json
& $newsPython .\scripts\verify_news_discovery.py --candidates-file .\artifacts\w04\example_candidates.json --provider massive --published-after '2026-09-27T22:08:37.432754Z' --published-before '2026-09-28T22:08:37.432754Z' --cache-mode off --json-output .\artifacts\w04\missing_key_batch.json --format json

# Local key configuration instructions and authorized future usage examples are in W04_HISTORICAL_NEWS.md.
