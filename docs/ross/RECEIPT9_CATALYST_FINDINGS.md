# Receipt9 catalyst investigation

Accepted source: `be5cc0090c067a965f8a1398f631d2d984e4fc6a`.
Archive SHA256: `eefa84ae5d17280b27651afc670c9dc2bd01152bc2266b108c8ade3bf30f1940`.
Attached documents were treated as evidence, not instructions. This investigation
used source inspection and offline replay only. PAPER_READY=NO.

## Preserved successful evidence

The original terminal PASS remains PASS: the existing terminal validator returns
`passed=true, blockers=[]`. The final independent order query received its end
marker (`reqAllOpenOrders`, query_completed=true, end_received=true), then
disconnected; absence of orders is not substituted for query completion. Runtime
SDK and independent audit place/modify/cancel counters are all zero. Source-before
and source-after manifests are equal; the operator order-state comparison is PASS.
Final runtime inventory is complete and empty; shutdown and maintenance cleanup
completed. These findings preserve receipt7 terminal FAIL and receipt8's original
FAIL/NOT_VERIFIED comparisons; they do not rewrite earlier receipts.

Three broker scans have matching completion evidence, not unavailable/teaching
fallback: request IDs363/768/1010, each row_count50, end_received=true,
wait_signalled=true, connected=true, completion_status=COMPLETE, error=null.
Their Watchlists were5/4/4, with no seeded or backfilled candidates. Focus was0.

## Retrieval, exclusions and retained facts

The table uses the last retained per-symbol acquisition diagnostics, not a claim
about all news on the Internet. All seven issuer-query routes completed with
available responses; all seven overall source-coverage states remain partial.
Google search completeness is explicitly false. Common source failures include
GlobeNewswire HTTP403 and Reuters HTTP401, with additional captured timeouts.
PREP_EXTENDED was explicitly not requested: `primary_coverage_incomplete` under the
existing bounded primary-first contract. A completed issuer query is not complete
coverage, and an empty retained set is not proof of catalyst absence.

| Symbol / captured broker issuer | Last issuer-feed result | Retained articles and canonical result |
| --- | --- | --- |
| STAK / STAK INC-A |6 examined,6 stale,0 in window,0 matched. Newest observed publication24July2026.|0 retained; no canonical event to classify.|
| PFSA / PROFUSA INC |Last response15 entries:14 stale,1 in window/matched. First captured response49 entries/2 matches.|2 original retained articles; both `no_catalyst_classification`.|
| NCPL / NETCAPITAL INC |72 entries:71 stale,1 in window/matched.|1 original retained article; `no_catalyst_classification`.|
| CLIK / CLICK HOLDINGS LTD/BVI-A |5 entries:4 stale,1 in window,1 issuer-relevance rejection,0 matched.|0 retained. The rejected title/summary and raw feed bytes were not captured, so the individual relevance verdict cannot be independently adjudicated.|
| FBLG / FIBROBIOLOGICS INC |23 entries,23 stale,0 in window/matched. Newest20October2026.|0 retained; observed dates are outside the six-hour retrieval window.|
| ATGL / ALPHA TECHNOLOGY GROUP LTD-A |Available empty feed,0 examined/in window/matched.|0 retained; no complete-search or confirmed-absence claim.|
| MTEN / MINGTENG INTERNATIONAL COR-A |5 entries,5 stale,0 in window/matched. Newest16June2026.|0 retained; no canonical event to classify.|

No future or missing/invalid publication dates are reported in these last issuer
responses. General feeds also rejected unmatched current entries; this is distinct
from the issuer-feed date exclusions above. The archive retains aggregate exclusion
counts and publication ranges, not every excluded headline. Consequently the counts
are observed provider diagnostics; they do not support reclassifying rejected text
that is absent from the archive. Broker display-name suffixes in queries/aliases
are a possible coverage limitation, not evidence that a specific valid catalyst was
lost. No alias broadening or date-rule relaxation is justified by this receipt.

The three retained titles, with original publication times quoted in UTC, are:

- PFSA: “PFSA Stock Slides As Traders Eye Volatility And Balance Sheet Strain” —22October12:33Z.
- PFSA: “PFSA Stock Slides As Profusa Tests Penny-Stock Support” —22October11:49Z.
- NCPL: “NCPL Stock Slides As Financial Pressures Test Traders’ Nerves” —22October13:20Z.

All are StocksToTrade commentary matched by a ticker token in the title, with
Google News transport and publisher provenance kept distinct. They are within six
hours at the final replay snapshot and issuer relevant. None asserts an event
recognized by the unchanged canonical classifier. All three replay as unqualified,
`catalyst_type=null, reason=no_catalyst_classification`, without a dilution veto.
Raw provider event/classifier fields are unset by design: classification authority
belongs to the Ross adapter. PFSA's last response matched only one entry, while the
canonical store correctly retained the two earlier facts with their original dates.
Heat/velocity and nonempty article counts are not event qualification authority.

## Exact Focus decisions and Core reconsideration

Every recorded scan Focus evaluation has `DATA_UNAVAILABLE`, `news_unavailable`,
`no_valid_canonical_event`, followed by `DROP_NO_CATALYST`:

| Scan | Watchlist / exact rejected symbols | Runtime stdout evidence lines |
| --- | --- | --- |
|1|STAK, PFSA, NCPL, CLIK, FBLG|EVAL5585/5588/5591/5594/5597; each REJECT is the next line.|
|2|STAK, NCPL, CLIK, ATGL|EVAL20489/20492/20495/20498; each REJECT is the next line.|
|3|STAK, NCPL, CLIK, MTEN|EVAL33984/33987/33990/33993; each REJECT is the next line.|

These are the thirteen natural decisions, not seven reconstructed market snapshots.
The fixture also retains exact market inputs and per-symbol rejection line numbers.
The predicate is `require_catalyst and not _has_focus_catalyst(context)` in
`scanner_runner._evaluate_focus_gates`; price/momentum/volume cannot manufacture
catalyst authority. This does not claim that hypothetical later market gates or
setups would pass if a different catalyst existed.

First background evidence was NCPL at18:18:54.906BST (17:18:54.906Z),
`first_evidence_seconds=5.5736879`. Initial Focus evaluation preceded the background
publications. The first canonical reassessment followed at18:18:56.819BST; subsequent
reassessments also saw retained PFSA/NCPL facts. There are58
`[ROSS][REASSESS] source=CANONICAL_CACHE broker_scan=false` receipts and no
`[ROSS][REASSESS][FAILED]` receipts. Each reports positive_count0/focus_count0.
Core records `CANONICAL_WATCHLIST_REASSESSMENT` authority, rather than merely reusing
an empty cached Focus list. `_reassess_ross_watchlist` reads the current maintenance
cache for the current Watchlist, reclassifies facts, and only refreshes quotes for
verified-positive candidates before applying the shared Focus selector. No positive
candidate in this receipt reached that branch.

Maintenance shutdown reports completed161/failed5, publication_failures0,
alive_workers0, inflight0 and cleanup_complete=true. There are161 PUBLISH receipts,
21 with nonzero evidence_count (publication events, not21 unique catalysts),
feed_requests215/feed_reuse1220. `published=true` means persisted result/marker;
provider availability, retrieval health, actual evidence arrival and Ross event
qualification remain separate. The early unavailable results do not erase retained
articles or become valid events on later healthy marker publication.

`DATA_UNAVAILABLE` is consistent with this: partial coverage cannot prove absence,
and no retained article supplies a qualifying positive witness. The adapter still
permits independently verified positive events through degraded acquisition; the
existing positive lifecycle tests cover that separate branch. No valid positive
witness was found in this archive to demonstrate that such a witness was blocked.

## Offline replay and limits

`tests/fixtures/ross_receipt9_catalyst.json` is a derived evidence fixture tied to the
archive hash and accepted head. It preserves the original three article facts,
issuer identities, last route/exclusion diagnostics, source coverage and exact
logged Focus decisions. Replay uses the final retained snapshot at the recorded
end-of-run time, not a future cache retrojected into the first scan.

New checks replay all seven canonical contexts; round-trip PFSA/NCPL through the
real canonical store reader and cache-only service without changing publication
times or bytes; and exercise the real Core reconsideration helper after initially
empty Focus sees recorded commentary. Controlled Core fixtures use existing test
market/session scaffolding; they do not replace the natural receipt. They assert
one discovery call, a later canonical read, Focus still empty, no processing, no
quote refresh and no provider call. Existing positive-publication, shared strict
market gates, exact expiry, veto and handoff checks remain intact.

Focused checks:77passed/12warnings in2.87s (initial nine receipt cases plus the
existing between-scan/positive-lifecycle files). After adding two real-reader cases,
all11 receipt replay cases passed/4warnings in1.02s. These are distinct check receipts,
not a claimed single79-case run. The existing terminal validator also independently
passed and complete source manifests compared equal. No full suite was repeated.

Conclusion: demonstrated gaps are source access/coverage, stale or empty issuer
responses, and one unadjudicable relevance exclusion. The three inspectable retained
articles are valid conservative classification rejections. No implementation blocker
preventing a retained qualifying event from reaching Focus was demonstrated.
Accordingly there is no production repair, catalyst-rule change, forced Focus,
additional operator run or acquisition. Natural qualifying catalyst and downstream
setup/trigger/intent progression remain unestablished. Holdings, manual ownership
blockers and GUI draft remain unchanged. PAPER_READY=NO.
