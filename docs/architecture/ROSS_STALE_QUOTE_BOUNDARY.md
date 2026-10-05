# Ross stale quote consumer boundary

The Ross algorithm's stock-selection hard gates exclude stale data (`P01_ROSS_MOMENTUM/GOVERNANCE/ALGORITHM.md`, section 2). The broker adapter already computes `MD_STALE` from the broker last-trade timestamp and configured age limit. Requested/returned data type, market time and receipt time remain separate facts.

The first reproduced consumer defect after W04 is that `_evaluate_watchlist_gates`, `_evaluate_focus_gates` and the premarket fallback accepted otherwise qualifying contexts carrying `MD_STALE`. The shared scanner guard now returns `DROP_STALE_MARKET_DATA` and clears selection/execution eligibility. It consumes the existing provider decision without adding a freshness threshold, resetting timestamps or inferring freshness from receipt time. Historical continuity context does not establish current Focus authority.

The saved natural scanner observation on 2026-09-28 at about 17:30 UTC contains KNRX in Watchlist with `MD_STALE`; Focus was empty because both KNRX and LFCR lacked confirmed catalyst evidence. This historical record is not a current-code live certification. Its exported rows omit session RVOL provenance, so a direct replay cannot reconstruct the original full gate decision. The later independent quote/bar probe completed at 17:33:44 UTC: it reported LIVE returns, separate market/receipt timestamps and genuine unaggregated 10-second, 1-minute and 5-minute IBKR TRADES bars. It was not a second natural scanner/Focus observation. No W04 research article is substituted for Ross evidence.

The same guard also excludes stale contexts from premarket Top-N underflow and prep reseeding; an explicit mock fallback cannot reintroduce them either. Four additional review regressions cover prep ledger invalidation and actual PRE scanner admission, with stale/fresh controls.

Four initial offline cases isolate the consumer boundary. Before repair, three stale rejection cases fail and the non-stale/catalyst control passes. After repair, 210 directly affected tests pass across stale gating, scanner/Focus selection, broker snapshot/provenance, watchlist continuity, genuine timeframe acquisition and canonical news consumers. External/broker sockets are blocked by the existing W02 offline guard. The full local baseline was not repeated; the PR's normal CI provides the full gate.

Price, gap/percentage change, RVOL, float and mandatory fail-closed catalyst remain unchanged; absolute volume stays separate from RVOL. Risk, execution and recovery implementations are unchanged. Massive is not activated in Ross. The next unresolved natural Ross stage remains Watchlist-to-Focus catalyst qualification: the latest natural scanner record has `DATA_UNAVAILABLE`/budget exhaustion, not confirmed absence. Positive current-code natural evidence is still missing.

Private task logs and credential/provider handoff remain under `output/w04/2026-10-05/next-check-163150/`; no credentials or licensed payloads belong in the PR.

PAPER_READY=NO
PAPER_READINESS_GATE=FAIL

Registered Ross selection receives only non-stale metrics, including the weekend session normalization path. Stale metrics remain in diagnostic output. The production selector regression uses a synthetic qualifying canonical catalyst result (no provider calls) and proves rejection with and without prep; the existing unavailable-catalyst control remains fail-closed. Before the selector repair: 2 failed / 2 passed.

Prep-only synthesized contexts preserve persisted quality flags before admission checks. A current fresh context retains its own quality authority instead of inheriting obsolete prep flags. Regressions prove stale prep exclusion, non-stale flag preservation, unchanged input artifacts and fresh-current precedence.
