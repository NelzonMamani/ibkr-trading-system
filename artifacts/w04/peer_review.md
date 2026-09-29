# W04 canonical integration and peer-review checkpoint

Owned implementation: `news_intelligence_contract.py`, `news_intelligence_service.py`, `evidence_store.py`, `issuer_relevance.py`, and `test_w04_canonical_history.py`.

The canonical history tests passed 15 cases. The already-started bounded eight-module integration run passed 177 cases in 17.03 seconds. Its offline guard recorded no external/broker attempts and one permitted standard-library socketpair self-pipe. No provider requests or full-suite rerun were performed by this agent.

Historical requests use explicit, inclusive, aware UTC publication bounds. Filtering precedes the canonical evidence cap. Actual publication/acquisition timestamps and wall-clock age remain distinct. The existing bounded active-profile cache can evict articles outside a newly selected explicit window; it is not an archival multi-window store. RSS profile shape and nonhistorical behavior remain protected.

The helper/CLI draft review found no additional concrete blocker beyond the already assigned future-end validation. Explicit history filtering, rolling-window warm reuse, per-symbol provider details and article-versus-acquisition provenance align with the canonical integration.

Provider draft review identified one additional issue: default `NewsCandidate.company_name`/`aliases` overwrote otherwise valid metadata-only issuer identity. This was sent to the provider author with the existing RSS conditional metadata merge as the compatibility reference. The first repair used an unsupported `candidate_aliases` metadata key, leaving aliases-only candidates unmatched; that same-family correction was also sent to the author, with the supported nested `aliases` field as the merge seam. No matcher expansion was requested. Root's independently reported pagination, payload-validation, normalization-budget and diagnostics findings are tracked by the provider author.

Final independent read-only review is complete with no remaining concrete blocker. The alias merge now uses supported canonical keys; the helper and provider reject explicit future query ends. The review checked trusted cursor-only pagination, bearer authentication protected against `.netrc` substitution, sanitized errors, per-symbol coverage/page counts, normalization completed before deadline acceptance, pending/late results, and response-close lifecycle separation. The provider's recorded final four-module run passed 102 tests (46 provider cases and 56 accepted W02/W03 timing cases) in 2.68 seconds. This reviewer did not rerun them or modify provider/helper source.

The shared local-user quota ledger cannot observe other machines, OS users or unrelated applications using the account; this limitation is explicit, and HTTP 429 applies a shared local cooldown. No live provider coverage or trading certification follows from this review. Root owns the combined checks, full suite, live-access outcome, CI and final PR review.
