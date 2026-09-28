# W03 saved live coverage analysis

This is offline analysis of the single saved W03 provider batch, not another retrieval or evidence insertion. All 21 body hashes verify against `live_capture_index.json`; the canonical date, summary and issuer-matching helper hashes match the live runtime. The matrix preserves original publication/updated values, UTC timestamps, source hashes, per-source measurements and cleanup observations. No provider repeat or health probe was made.

The batch began at **2026-09-28 22:08:37.432754 UTC** and its result completed at **22:08:55.433188 UTC**. Eighteen HTTP 200 responses were recognized feeds. Their 429 returned entries contain 259 publications inside 24 hours and 170 older entries; none has a missing or future timestamp. Counts are unchanged when anchored at batch start or completion. These are source-entry counts, not unique articles. Canonical accepted matches are **IRON 0, MSFT 0, LFCR 0**; the live result truthfully reports partial coverage, not completed universal absence.

## Issuer findings

**IRON: current feed coverage.** The separately verified [publisher article](https://www.globenewswire.com/news-release/2026/09/28/3370223/673/en/disc-medicine-investor-news-if-you-have-suffered-losses-in-disc-medicine-inc-nasdaq-iron-you-are-encouraged-to-contact-the-rosen-law-firm-about-your-rights.html) has original publication **2026-09-28 19:02:00 UTC**. The saved verification reports HTTP 200 and agreement between the original, visible and structured timestamp selectors. It is inside the requested window, but its exact URL is absent from all captured feed entries. GlobeNewswire Finance returned 20 entries dated **21:29–22:06 UTC**; Technology returned 20 dated **16:00–21:53 UTC**. Both parsed successfully, with no deadline exhaustion. Finance's returned list contains only publications newer than the target. The observed limitation is rolling-feed coverage; a 24-hour filter cannot retrieve an article absent from the response. Publisher verification does not prove service discovery, and the earlier W02 fixture is historical evidence, not W03 live discovery.

**MSFT: existing issuer-identity guard.** Business Insider contains [Microsoft's Copilot chief opens up about the AI future he fears most](https://www.businessinsider.com/microsoft-copilot-chief-ai-future-worries-about-2026-9). Its original feed publication is **2026-09-28 18:24:12 UTC**, while its updated value is **18:36:15 UTC**. The canonical helper uses the original publication. The same bytes also arrived through Markets Insider. With the actual supplied identity, `Microsoft Corporation` loses its legal suffix and becomes the single word `MICROSOFT`; `Microsoft` is likewise one word. The existing matcher rejects both as company aliases, leaving no effective company alias and no explicit MSFT security notation in this entry. This is deliberate existing identity policy, not freshness rejection, a timing failure, or live issuer discovery. Other incidental Microsoft mentions are recorded separately and are not promoted to issuer evidence.

**LFCR: no observed issuer coverage.** The accepted company alias is `LIFECORE BIOMEDICAL`. No canonical match or Lifecore text observation appears in the saved feeds. This bounded sample does not establish that the issuer had no news.

## Timing and access

Provider retrieval elapsed **17.973s**, canonical service **18.000s**, and helper total including cleanup **18.093s**, within the 30s research retrieval budget. All 21 sources were attempted once; none was skipped for budget, no request timeout was observed, and neither tier exhausted its deadline. All 21 owned calls completed, every observed response closed, and zero owned workers remained alive. The capture is complete at the saved snapshot. Reuters returned **401**, France24 **403**, and VentureBeat **429**. Their parse timing remains unknown, not zero. MarketWatch's 6.227s HTTP call exceeded the nominal 5s scalar timeout without a timeout exception; scalar connect/read waits are not a total elapsed-call deadline.

## Precise remaining decisions

- Decide whether issuer-specific/archive coverage is needed for articles absent from rolling broad feeds. Preserve the current source lists until that separate coverage decision; no provider redesign follows from this sample.
- Decide whether verified single-word issuer identities deserve an explicit disambiguation mechanism. Preserve the current matching guard until that policy is reviewed; do not weaken ticker-word rejection to force this MSFT result.
- Review authorized access/entitlement handling for Reuters 401, France24 403 and VentureBeat 429. This report authorizes no retry or bypass.
- Review source quality: CNN's newest saved publication is **2017-02-13**, Dow Jones' **2025-01-27**, and Forbes Finance returned a recognized empty feed. Business Insider and Markets Insider had identical body hashes, so their counts are not independent corroboration.

The supported interface and its offline contracts can be accepted independently of these live coverage limits. This capture supplies no live accepted issuer article and no trading-readiness evidence.

PAPER_READY=NO

PAPER_READINESS_GATE=FAIL
