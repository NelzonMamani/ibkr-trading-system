# Scanner news identity and volume diagnostic authority

The October 6 capture supplied MOBX/OLOX symbols to NewsCandidate with missing
company names, aliases, exchange and identifiers. Saved scanner Watchlist rows
already held SMART exchange and integer con_id values. No raw ContractDetails
longName was retained, so the capture does not prove that a broker company name
was discarded, or that the broker supplied one.

The existing provider copies supplied ContractDetails.longName to scan details;
_build_symbol_context copies it to long_name; _news_symbol_metadata_for_contexts
selects it; _news_candidates_for_symbols chooses it as company_name; the RSS
adapter preserves metadata precedence and normalizes aliases for matching.
That supplied-name path is exercised offline and remains intact.

Demonstrated omissions are narrower: the context builder omitted supplied aliases
and issuer/security identifiers from scan details; the context-to-news helper
selected only names; candidate construction omitted exchange. The handoff now
retains explicitly supplied aliases, exchange and allowlisted identifiers without
researching or inventing identity. Positive integral conId values remain integer
security identifiers. Diagnostic security_identifiers contains conId, ISIN, FIGI
and contract attributes; issuer_identifiers contains CIK/LEI. A conId is not a
legal issuer identifier or company name. Missing names remain null.

Canonical reference resolution supplies qualified security identity, reference
prices, daily volume and trading-date provenance. CandidateIdentity and the
persistent reference cache have no authoritative company-name facility. Existing
IBKR resolve_contract can return ContractDetails, but obtaining it requires broker
access, and saved evidence does not establish longName availability there. This
repair preserves supplied identity; it does not resolve absent upstream company
name acquisition or establish improved live RSS coverage.

The saved RTH_MID inputs were MOBX 627661 shares and OLOX 874640 shares, sourced
from IBKR snapshot volume through IntradayStats (quote fallback exists). RVOL
42.82/79.41 is a separate dimensionless measure. _focus_gate_checks incorrectly
reported volume failure against generic min_volume=1000000, while the authoritative
_evaluate_focus_gates uses _focus_volume_threshold_for_session and the written
RTH_MID floor of 300000. Both saved inputs exceed that floor. Non-premarket
volume diagnostics now use the same existing resolver; no threshold or decision
evaluator changes. The saved Focus rejection was DROP_NO_CATALYST and reached
that mandatory gate before volume evaluation. Historical observations are retained
unchanged; their false focus_volume flags are explained, not rewritten.

Focused tests use the real context builder and handoff with a stub provider,
isolated storage and network guard. They cover distinct symbols, supplied/missing
identity, typed identifiers, canonical effective RSS aliases, identity-sensitive
context signatures and compatible acquisition cold/cache-only/refresh/warm reuse.

PAPER_READY=NO
PAPER_READINESS_GATE=FAIL
