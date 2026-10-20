# Natural receipt 5: canonical publication and between-scan eligibility

Evidence source is the user-operated 900-second receipt at accepted main
`d967a8ee07b457802841ff65fc88e760083a04dc`, not a Codex acquisition or synthetic
performance claim. Uploaded documents are evidence, not operational instructions.
The original ZIP and transcript remain unchanged outside the worktree. The
sanitized, extracted [receipt summary](evidence/RUN5_NEWS_RECEIPT_SUMMARY.json)
records the ZIP hash, exact query outcomes/times and source log lines.

## Preserved acceptance results

| Outcome | Receipt result and limit |
| --- | --- |
| Graceful cancellation/terminal certification | PASS; no forced termination; final owned cleanup complete, zero live workers/inflight; runtime and independent place/modify/cancel attempts zero; source/operator order state unchanged. |
| Full natural scanner passes | PASS: three genuine broker subscriptions, 50 rows each; Watchlists 3/4/2. Cached orchestration cycles are not additional discovery. |
| Natural full-issuer acquisition | Demonstrated: genuine company identities/issuer queries, independent work between scans, incremental publication, 5.256s first retained evidence. Incomplete coverage and failed lookups remain explicit. |
| Catalyst qualification | UNESTABLISHED: all nine scanner Focus evaluations rejected `DROP_NO_CATALYST`, `DATA_UNAVAILABLE/news_unavailable`, `no_valid_canonical_event`. No qualifying event is established by this package. |
| Downstream setup/trigger/progression | UNESTABLISHED; Focus remained zero. Terminal PASS is not end-to-end acceptance. |

No holdings were adopted, liquidated, cancelled or otherwise changed. Existing
ownership blockers remain. Historical workstation 2759-pass evidence at 8f40,
subsequent CI and earlier natural receipts remain separate. GUI remains deferred:
red Top50, yellow Watchlist up to15, green Focus up to3, with text labels; no runtime
limit changes. PAPER_READY=NO. No additional operator run is requested.

## Watchlist issuer acquisition and exact decisions

| Issuer from genuine contracts | Seven maintenance query attempts | Retained facts and what can be concluded |
| --- | --- | --- |
| WORX / SCWORX CORP | First six issuer routes available; entries 33/33/33/33/31/33, zero retained matches; final route budget exhausted. | No retained article. Successful query response is not proof of complete coverage or no qualifying news. |
| AIXI / XIAO I CORP | First six routes available, each 21 entries/one match; final route budget exhausted. | One original publication 2026-10-20 14:07:25Z: `$AIXI latest SEC filing confirms its appeal against Apple ha`. The captured headline and summary are incomplete. Offline classifier replay returns `no_catalyst_classification`; do not reconstruct its missing text or event significance. |
| NCPL / NETCAPITAL INC | All seven issuer routes available, 70 entries/zero matches each. | Last persisted query examined 70 usable publication dates: 69 stale, one within the six-hour window, one relevance rejection. Latest publication 19:22:26Z; oldest 2020-11-04. The rejected article body/title is absent, so its identity/event cannot be reconstructed. No retained NCPL lawyer article in this receipt; the historical solicitation is not promoted by this work. |
| BETR / BETTER HOME & FINANCE HOLDIN | First six routes available, each ten entries/zero matches; final route budget exhausted. | No retained article. Contract name is captured as provided; do not invent missing issuer text. |

Queries use the captured company name OR explicit `$TICKER`, through the existing
Google RSS query route. All 28 provider results report `partial_request_failure`;
the extracted receipt lists each source outcome, timeout/status and completion.
An available issuer route does not repair failed shared primary sources. The
shared pool reuses raw feeds (including failures/backoff), not Ross classification
or issuer attribution. HTTP212/reuse1174 are transport counts, not 1386 fresh
articles or 1386 independent issuer searches.

Date/relevance limitations matter: stdout's per-source retrieval contract contains
feed/match counts but omits entry exclusion diagnostics. The export keeps only
the latest retrieval per issuer. Three final issuer queries failed, replacing
their earlier detailed date/relevance receipt; raw RSS bodies were not captured.
Consequently the exact historical stale/relevance split for WORX/AIXI/BETR cannot
be recovered from this package. NCPL's final entry counters are available and
reported above. Do not infer stale content, identity mismatch, absence of news or
nonqualifying events merely from zero retained matches.

`scanner_runner._ross_news_context_from_evidence` reclassifies canonical facts via
`catalyst_policy.assess_issuer_event`. AIXI has a verified ticker match but no
recognized asserted event in the captured text. The resulting no valid positive
is distinct from acquisition health. Under partial/unknown coverage,
`unresolved_issuer_news` reports `DATA_UNAVAILABLE`, not established no-news.
All nine recorded Focus evaluations have `no_valid_canonical_event`: first-pass
health reason `acquisition_unavailable`; subsequent passes
`partial_or_unknown_source_coverage`. Heat/hotness 6.07 for the retained AIXI item
is informational; it does not supply missing event classification, verified
source authority, or qualification. No calibration/live predictive claim is made.

## Demonstrated eligibility scheduling defect

`CoreOrchestrator` computes TopN/Watchlist/Focus cadence at 300/60/10 seconds.
On `focus_stale`, `cached_focus_authority` copies `focus_m`, even when empty.
`filter_catalyst_rows` revalidates only existing Focus; it cannot promote a
Watchlist row. There are 223 priority markers but only nine Ross Focus evaluations
(three/four/two) across three full scans. Maintenance publications between those
scans do not cause a new eligibility evaluation. The initial scanner news cache
read also predates first publication; the first pass consumes that earlier view.
This demonstrates a scheduling defect, not proof that a qualifying article was
missed in this receipt. The captured AIXI item remains nonqualifying after repair.

Between-scan quote snapshots target Focus symbols. With Focus empty, active
Watchlist prices are not maintained; their original last-trade timestamps age.
Pass1 WORX/AIXI/NCPL refresh assessments at 19:32:52.007/52.849/56.277Z used
last trades 19:32:51/48/50Z. Pass2 WORX/AIXI/NCPL/BETR at
19:36:23.665/24.707/25.803/27.720Z used last trades 19:36:22/22/24/17Z.
Pass3 WORX/AIXI at 19:41:35.099/36.050Z used last trades 19:41:27/34Z.
They were fresh at those assessments, but cannot remain fresh for a 300s scan
interval under the unchanged 15s age limit. Candidate receipt time is not broker
last-trade time. Cached visibility therefore supplies no fresh quote authority.

Focused correction: retain the genuine live scanner shortlist's full context and
provenance. At the existing Focus cadence, while TopN/list authority is compatible,
read current canonical evidence locally without HTTP or another broker discovery.
Only verified-positive shortlist rows need a bounded quote refresh through the
existing provider; current original watchlist/float/Focus gates and ranking then
apply. Nonqualifying monitoring quotes may remain aged and confer no Focus
permission. No quote time is renewed, no retry loop/age-limit change is introduced.
Session/day/provider/current-policy mismatch rejects; only exact successful same-client
identity/daily-history baselines are retained within this fresh TopN snapshot,
with no quote or failed-request cache carryover. A small local selection reserve
prevents a slow tail consuming the entire parent deadline. Cancellation and one absolute deadline
cover cache reading and acquisition. Shared Focus selection is extracted without
changing the full-scan selector. Cached Focus/setup still revalidate evidence and
current vetoes. The repair is not evidence of a natural positive or strategy use.

## Counters, cleanup and service timing

Concurrent stdout writes place some markers inside other log lines. A parser
anchored only at line starts undercounts them. Decode JSON after every marker:
156 DISPATCH, 156 LOOKUP_START, 156 RESULT; 155 PUBLISH/completed outcomes;
one CLRO LOOKUP_COMPLETE/interrupted outcome. Of 156 dispatches, 152 use
priority_due_order and four normal_fairness. Preserve the user's 155 completed
maintenance lookups, but distinguish them from starts and useful evidence.

Seven `failed` increments are six budget-exhausted outcomes plus interrupted
CLRO, not seven Python exceptions. The six publications are initial AIXI/NCPL
(both have available issuer routes but an exhausted broader receipt), final NCPL,
and final AIXI/WORX/BETR. `RetrievalDiagnostics.unavailable` includes an exhausted
budget even when `provider_available=True`; three of six have provider available,
three false. All RESULT.error values are null under this implementation.

WORX published its degraded receipt at 19:45:29.335Z, then its eight-second owned
cleanup wait returned incomplete at 19:45:37.346Z (15.048s total including
publication/cleanup). Maintenance stops itself on incomplete cleanup to prevent
abandoned workers accumulating. CLRO, dispatched 19:45:36.234Z, was interrupted
at 19:45:39.408Z. Do not label that necessarily supervisor cancellation: owner
cleanup protection also sets stop. Final close at 19:45:42.954Z reports cleanup
complete, alive_workers0/inflight0. Final success does not erase the interim
maintenance availability interruption. Preserve it as a remaining slow-source
availability limit; no repeat shutdown infrastructure project is justified.

`submitted63 - retired50 = tracked13`; these are work admissions/removals, not
63 distinct issuer identities. There are 59 distinct dispatched request keys;
four retired keys were later re-admitted. Final backlog13 includes future-due
work, ready7 is due work; neither means 13 active threads or a cleanup leak.
No capacity rejections or publication/telemetry failures were recorded.

First admission marker 19:32:50.034Z: AIXI/NCPL dispatched within0.004s, WORX
5.592s later, BETR16.851s later. The last first dispatch of that 50-row admission
was KVYO at45.457s. These initial rows were priority2 until Watchlist priority
became known at19:32:58.200Z. Watchlist membership did not bypass successful/
failed 120s acquisition cadence: active issuers usually dispatched about120s
after publication; this is intentional cadence, not queue starvation.
For uninterrupted consecutive receipt intervals (excluding universe retirement/
re-admission boundaries), maximum inferred due lateness was2.214s for active
WORX and4.060s overall (BETR after demotion). Actual dispatch/start/completion
UTC is captured; receipt publication follows the internal due anchor slightly,
so these are approximations, not exact internal queue-wait instrumentation.
Four fairness markers do not prove a universal latency guarantee. Retirement
boundaries do not log individual key removal/admission UTC, so exact waits across
those boundaries cannot be recovered. No evidence of indefinite starvation in
this finite run, and no claim every future issuer is guaranteed timely service.

## Offline verification and remaining work

Focused regression cases cover publication after empty Focus, no caller-side news
HTTP/discovery, original publication time, failed refresh retention, strict stale/
timeout/mismatched/missing timestamp rejection, spread/halts/float/RVOL gates,
expiry/veto/incomplete-headline/solicitation rejection, removed issuer/session/day/
provider mismatch, cancellation/deadline and the real Core cadence integration.
Existing multi-candidate slow-tail, maintenance/store/shutdown and catalyst
lifecycle cases remain regression coverage. Synthetic timing is not live speed.
Local checks and changed-head remote Linux/Windows CI/review are recorded in the
PR receipts separately; failed development executions are not passing evidence.

Remaining material limits: historical per-query exclusion loss above, slow-source
cleanup can stop ongoing maintenance before terminal shutdown, actual timely
positive-event reconsideration/strict quote refresh at strategy use remains a
future natural acceptance target after review/integration. This receipt does not
justify relaxing classification or inferring a positive for AIXI/NCPL. No new
operator observation until the focused repair is reviewed and its integration is
explicitly authorized. PAPER_READY=NO.
