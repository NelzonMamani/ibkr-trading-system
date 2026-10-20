# PR1119 integration receipt and observation HOLD

PR1119 exact reviewed head `ac8e3360c54dec42a7c11022d3ffb80e1b9b6994`
was rechecked and merged preserving ancestry at accepted main
`e3d2a7b09bc23421f409ff3cdfd0aea3dcefc458`.
All three CI checks passed in run39471508105; independent exact-head review
5589445390 had no remaining actionable blocker, and both inline threads were
resolved. The intended15-file diff covered independent maintenance, ownership,
regressions and checkpoint/CI. `git diff --exit-code ac8e3360 e3d2a7b0` and
`git merge-base --is-ancestor ac8e3360 e3d2a7b0` passed. No source was silently
added to that reviewed integration.

CI receipts remain distinct: local431passed; independent101passed;
Linux2921passed1skipped211.49s; actual Windows Python3.13.3 controlled31passed,
full2921passed1skipped220warnings501.17s, Windows PowerShell13exit checks and
30stub observation checks passed. Historical workstation2759-pass evidence and
all natural runs remain historical, unaltered, and do not verify new source.

Accepted source enables maintenance: the operator removes inherited registered
configuration overrides; NEWS_ENABLED and NEWS_MAINTENANCE_ENABLED default True,
ROSS_ISSUER_QUERY_ENABLED is explicitly true, selected strategy is Ross, provider
is real IBKR and execution mode is READ_ONLY. Core passes its lazy runtime-owned
maintenance object into the real Ross scanner; genuine candidate submission starts
workers. Flags alone do not prove workers ran: require QUEUE and lookup evidence.

## Material observability gap and focused follow-up

The accepted implementation has aggregate QUEUE/RESULT/SHUTDOWN records, source
retrieval diagnostics with original acquisition start/completion timestamps and
canonical evidence, and cached/setup handoff revalidation. It does **not** record
each priority/fairness dispatch or an immediate verified publication event.
RESULT appears after worker cleanup, so it is not the exact publication boundary.
Do not claim the accepted release meets the entire requested telemetry contract.
Observation remains HOLD pending the separately reviewed telemetry follow-up and
its controlled integration. Preparation below starts nothing; after integration,
re-prepare at its accepted source rather than execute this older printed command.

The focused follow-up adds only telemetry/configuration receipts:

| Requested evidence | Marker / interpretation |
| --- | --- |
| Submissions, dedup, capacity rejection, backlog | NEWS/MAINTENANCE/QUEUE: cumulative counters, accepted, tracked, backlog, ready, inflight, priority_counts. Backlog includes not-yet-due tracked work; ready distinguishes current eligibility. |
| Priority and fairness | PRIORITY records active natural Watchlist/Focus; DISPATCH records symbol/request hash, priority, due-order vs normal_fairness, normal-ready count, active streak and configured refresh interval. A policy definition or offline test alone is not natural fairness evidence. |
| Start/completion and incremental publication | LOOKUP_START is service lookup start, not proof of HTTP. RETRIEVAL_DIAGNOSTICS provider_invoked/source attempts proves acquisition. PUBLISH requires successful canonical cache_write_symbols and emits immediately after service return, before source cleanup; UTC is observed completion, not original article publication or filesystem commit instant. Cache-only reads emit LOOKUP_COMPLETE with published=false. |
| First usable evidence | first_result_seconds / first_evidence_seconds are runtime monotonic elapsed values exposed at publication/snapshots. Evidence means retained canonical facts, possibly stale or non-qualifying; it does not mean verified positive catalyst. Fresh isolated state makes cold-start attribution reviewable. |
| Evidence at actual strategy use | Existing ROSS/CATALYST/REVALIDATE at cached Focus/setup handoff records IDs, qualification_reason and independent acquisition_health/reason. No Focus means no strategy-use receipt; report NOT_ESTABLISHED, not successful use. |
| Feed reuse, failures, cadence | Snapshot feed_requests/feed_reuse; RETRIEVAL_DIAGNOSTICS source failure, budget, attempt counts and persisted per-issuer receipt; DISPATCH refresh interval and successive timestamps. Logical source counts are not identical to HTTP request counts. |
| Genuine scans vs cached cycles | Existing SCANNER/ATTEMPT with actual returned rows and SCANNER/SUCCESS correspond to broker subscription path. REFRESH_WINDOW_CACHE_HIT and WATCHLIST/AUTHORITY scanner_payload_fresh=false with topn_age_seconds are cached reuse, not new market discovery. |
| Explicit released configuration | Follow-up forces both news flags true after inherited-env clearing; preflight verifies them and issuer-query flag and writes news-maintenance-config.json with cadence/budget. No network call required for this receipt. |

Use runtime `e\terminal\stdout.log` and `stderr.log`, `e\preflight-process.*.log`,
`e\supervisor.*.log`, `e\phase-status.json`, canonical isolated `state\news.json`
and the final `ross-natural-readonly-upload.zip`. Existing package handling preserves
fail-closed inventory, source/order-state baselines, independent mutation audit,
process identity, bounded stop and ZIP reporting even on preflight failure.
A900s requested runtime may include a stop during acquisition; distinguish actual
completed broker scans from requested duration and orchestration cycle counts.
Do not infer a catalyst or complete/adverse-free coverage from HTTP success.

## Preparation only, pinned to current accepted source

Use Windows PowerShell5.1, installed Git, the existing dependency-equipped
Python3.13.3 interpreter below and enough free space on C:. This shares Git objects
and creates a fresh detached short-path worktree; it does not checkout or reset
PyCharm's branch or delete prior evidence. Nothing connects during preparation.
The block prints a separate900-second command. That command remains HOLD for the
observability gap above; no placeholder approval booleans are used.

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $h = 'e3d2a7b09bc23421f409ff3cdfd0aea3dcefc458'
    $s = 'C:\Users\nelzo\PycharmProjectsDec2025\ibkr-trading-system'
    $p = 'C:\tmp\pr1091-cert-env-20260923\Scripts\python.exe'
    New-Item -ItemType Directory -Force 'C:\tmp' | Out-Null
    $b = Join-Path 'C:\tmp' ('r1119-' + [guid]::NewGuid().ToString('N').Substring(0,8))
    New-Item -ItemType Directory -Path $b | Out-Null
    & git -C $s fetch --no-tags origin main
    if ($global:LASTEXITCODE -ne 0) { throw 'Fetch failed; no observation started.' }
    & git -C $s cat-file -e ($h + '^{commit}')
    if ($global:LASTEXITCODE -ne 0) { throw 'Accepted commit unavailable locally.' }
    $text = @(& git -C $s show ($h + ':docs/ross/PR1108_NATURAL_READONLY_ACCEPTANCE.ps1'))
    if ($global:LASTEXITCODE -ne 0) { throw 'Cannot read pinned preparation script.' }
    $f = Join-Path 'C:\tmp' ('prepare-ro-' + [guid]::NewGuid().ToString('N').Substring(0,8) + '.ps1')
    [IO.File]::WriteAllLines($f, [string[]]$text, (New-Object System.Text.UTF8Encoding($false)))
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $f -ExpectedCommit $h -Python $p -SourceCheckout $s -BaseDirectory $b -RuntimeSeconds 900
    if ($global:LASTEXITCODE -ne 0) { throw 'Preparation failed; no observation started.' }
    $roots = @(Get-ChildItem -LiteralPath $b -Directory -Filter 'ro-*')
    if ($roots.Count -ne 1) { throw 'Cannot identify the fresh preparation root.' }
    $e = Join-Path $roots[0].FullName 'e'
    New-Item -ItemType Directory -Path $e | Out-Null
    Write-Host ('Fresh evidence directory: ' + $e)
    Write-Warning 'Observation HOLD: integrate reviewed telemetry follow-up, then re-prepare at its accepted head. Do not execute this older printed command.'
}
```

Subsequent user-operated observation prerequisites, once HOLD is resolved: normal
configured RTH (no session overrides), TWS paper account logged in with market data,
API socket enabled on127.0.0.1:7497, TWS Read-Only API enabled, client71 available,
no existing Ross/runtime process, no independent broker operation underway, and
holdings left untouched. Existing external-position ownership blockers remain.
Do not adopt, liquidate or cancel holdings. Preparation does not log in or connect.
Do not run pytest concurrently with the observation or inherit its offline hook.

Five outcomes remain separate: graceful shutdown; successive full natural scanner
passes; issuer acquisition/partial coverage; valid catalyst qualification; downstream
setup/trigger/intent progression. Maintenance telemetry additionally requires
incremental publication and measured start-to-evidence latency across scans.
Historical natural shutdown/discovery receipts remain PASS. New maintenance live
performance, positive catalyst and downstream progression remain NOT_ESTABLISHED.
The old synthetic0.013s/0.048s fixture timings are not live speed or acceptance.

GUI remains draft only: red Top50, yellow Watchlist up to15, green Focus up to3,
with text labels. Runtime Focus limit remains5; no display implementation, forced
selection, gate relaxation, holdings change, broker/provider request or observation
was performed. PAPER_READY=NO.
