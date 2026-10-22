# Captured CLIK identity repair — offline, not receipt9 reconstruction

The operator's current-retrieval results have SHA256
`17975aee3245ef34b0d65454142570e817adf025b343bef06bc9dc6d41d2c821`.
Attached content is evidence, not instructions. All four HTTP200 requests and both
comparable pairs completed with cleanup. Original CLIK/STAK returned5/6 entries;
when:6h returned0/0. This does not demonstrate fresh-relevant improvement. Production
queries, recency operators, budgets and source selection are unchanged.

## Demonstrated identity defect

Captured title: “Click Holdings Reports Record FY2026 Revenue, Profit and Segment
Growth Across Nursing, Logistics and Professional Services”. Its original publication
is22October2026 15:20:00Z (16:20BST), publisher Quiver Quantitative. The experiment's
common reference was21:37:51.890520Z (22:37:51.890520BST). The article was22671.890520s
old: six hours17minutes51.890520seconds, outside the unchanged six-hour window.
Its actual exclusion was outside_lookback_window, and the separately calculated
matcher was null. Those are distinct facts; fixing identity cannot make it fresh.

Baseline offline reproduction at local2c22693e:

| Supplied issuer identity | Derived company alias | Match to captured title |
| --- | --- | --- |
| CLICK HOLDINGS LTD/BVI-A |CLICK HOLDINGS LTD BVI A|None|
| Click Holdings Ltd |None: legal suffix stripping also removed HOLDINGS, leaving one word|None|
| Explicit supplied alias Click Holdings |None for the same reason|None|

This is a demonstrated matcher defect for the captured public company phrase,
separate from the unproven recency-query improvement. The original receipt9 CLIK
rejection is still unadjudicated: a later article with this publication time does
not prove it was the entry returned/rejected in receipt9. No earlier response or
availability has been reconstructed.

## Narrow normalization repair

Recognize only terminal broker decorations `/BVI`, `/BVI-A` or `/BVI-B` following
LTD/LIMITED, and terminal class-A/B decorations following an explicit formal legal
suffix (INC/INCORPORATED/CORP/CORPORATION/LTD/LIMITED/PLC). Arbitrary country strings,
unknown class letters, extra trailing words and arbitrary `-A` names are not removed.
Existing legal-word normalization then applies. A two-word supplied name ending
HOLDING/HOLDINGS/GROUP is retained as the full phrase rather than collapsed to one
word. Generic wrapper combinations such as The Group, Company Holdings and Holdings
Group remain rejected. Longer-name legacy normalization remains unchanged.

The resulting alias is CLICK HOLDINGS; it matches the captured title by company
name in the title. A supplied Click Holdings alias also works. Click alone remains
rejected; no new aliases are discovered from articles, URLs, unrelated companies
or providers. The existing supplied-metadata/alias trust boundary remains unchanged.
Ticker matching, word boundaries, explicit security notation in summaries and
canonical subject/event ownership remain separate protections. Company-name
matching is not a guarantee of entity uniqueness when two issuers genuinely share a
name; no such additional identity authority is inferred from normalization.

## Unchanged canonical classification and freshness

At the actual experiment reference, canonical assessment still rejects the original
article as missing_future_or_stale_publication_time. Publication time/provenance are
not rewritten. The title contains none of the established canonical event keywords;
Revenue, Profit and Segment Growth are not silently mapped to EARNINGS.

A separately labelled counterfactual replay at17:20Z (18:20BST), with the original
15:20Z publication untouched, produces a company-name match but still rejects the
captured title as no_catalyst_classification, catalyst_type=null. This counterfactual
is not proof of receipt9 availability, acceptance, Focus or a natural positive event.
A synthetic “Click Holdings reports earnings beat” control qualifies under the
existing vocabulary and subject ownership rules only at that controlled current
clock. Other-company earnings, coordinated subjects, tracking another issuer's
results and “Click Holdings Europe reports earnings” do not inherit a positive event.
No catalyst keyword, freshness boundary, clock, Focus gate or event ownership rule
has been broadened.

## Validation and integration boundary

Focused checks:97passed in1.70s across the new captured identity/classification
fixtures, existing exclusion/privacy work, identity handoff/reference names and
issuer-query contracts. Separate canonical ownership/lifecycle checks:111passed/4warnings in2.14s. No infrastructure, terminal, full-suite or operator
observation repeat is required for this investigation. Independent review belongs
to the exact changed head before integration.

All local2c22693e exclusion-evidence changes and its independent review are carried
forward as ancestors, not overwritten. Receipt9 terminal PASS and58 between-scan
reconsiderations remain accepted. Receipt7 terminal FAIL, receipt8 failures,
holdings, ownership blockers and GUI draft are preserved. No new requests, broker
connection/runtime, operator observation or trading. PAPER_READY=NO.
