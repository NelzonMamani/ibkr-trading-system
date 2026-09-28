# W03 saved source matrix

One live batch at 2026-09-28T22:08:37.432754+00:00; this matrix is offline analysis of its saved bytes. All 21 configured URLs were attempted once; 18 recognized feeds, 3 HTTP failures, 0 accepted issuer articles. No follow-up provider request or health probe was made.

Counts use the canonical publication/identity helpers and the 24h window. `F/S/U/M` = fresh/stale/future/missing; a dash means an HTTP failure rather than a recognized feed. Counts are per returned feed, not deduplicated articles. Full source hashes, original publication minima/maxima, per-entry timestamps/match results and completion instants are in [JSON](source_evidence_matrix.json) and [CSV](source_evidence_matrix.csv).

| Source | HTTP | Entries | F/S/U/M | HTTP s | Parse s | Outcome | Close | SHA256 prefix |
|---|---:|---:|---|---:|---:|---|---|---|
| [Benzinga](https://www.benzinga.com/feed) | 200 | 10 | 10/0/0/0 | 3.383 | 1.213 | available | closed | dc69872139b0 |
| [GlobeNewswire Finance](https://www.globenewswire.com/RssFeed?Category=Finance) | 200 | 20 | 20/0/0/0 | 2.920 | 0.107 | available | closed | e28f7f2d92b9 |
| [GlobeNewswire Technology](https://www.globenewswire.com/RssFeed/industry/9000-Technology/feedTitle/GlobeNewswire%20-%20Industry%20News%20on%20Technology) | 200 | 20 | 20/0/0/0 | 2.687 | 0.127 | available | closed | 6561a1ed28d5 |
| [Reuters](https://www.reuters.com/markets/rss) | 401 | - | - | 3.392 | unknown | HTTP_401 | closed | 8c9bc3560bce |
| [MarketWatch](https://www.marketwatch.com/rss/topstories) | 200 | 10 | 10/0/0/0 | 6.227 | 0.018 | available | closed | 9d73062bb7b4 |
| [Business Insider](https://feeds.businessinsider.com/custom/all) | 200 | 20 | 20/0/0/0 | 2.742 | 0.525 | available | closed | 93a3da1765ec |
| [Seeking Alpha](https://seekingalpha.com/feed) | 200 | 30 | 30/0/0/0 | 3.384 | 0.069 | available | closed | a8233305e68c |
| [CNN](http://rss.cnn.com/rss/edition_business.rss) | 200 | 20 | 0/20/0/0 | 0.283 | 0.043 | available | closed | 8dd47037c53e |
| [Dow Jones](https://feeds.a.dj.com/rss/RSSMarketsMain.xml) | 200 | 20 | 0/20/0/0 | 1.188 | 0.020 | available | closed | 02b06b556a26 |
| [Fortune](https://fortune.com/rss) | 200 | 10 | 6/4/0/0 | 1.683 | 0.235 | available | closed | be96210f4c1e |
| [Forbes Business](https://www.forbes.com/business/feed2) | 200 | 25 | 25/0/0/0 | 1.236 | 0.041 | available | closed | e163a82a8b9d |
| [Forbes Finance](https://www.forbes.com/finance/feed2) | 200 | 0 | 0/0/0/0 | 1.203 | 0.002 | available | closed | 32cd51784d6b |
| [BBC News](https://feeds.bbci.co.uk/news/rss.xml) | 200 | 33 | 29/4/0/0 | 2.130 | 0.068 | available | closed | d258347ece6c |
| [BBC Business](https://www.bbc.com/news/business/rss.xml) | 200 | 51 | 21/30/0/0 | 4.717 | 0.105 | available | closed | 11bf9ce85dcf |
| [Sky News](https://feeds.skynews.com/feeds/rss/world.xml) | 200 | 10 | 2/8/0/0 | 2.345 | 0.038 | available | closed | 69b2d35cf0b4 |
| [France24](https://www.france24.com/en/rss) | 403 | - | - | 2.302 | unknown | HTTP_403 | closed | 103554725d28 |
| [Markets Insider](https://markets.businessinsider.com/rss) | 200 | 20 | 20/0/0/0 | 4.983 | 0.296 | available | closed | 93a3da1765ec |
| [Investing.com](https://www.investing.com/rss/news.rss) | 200 | 10 | 10/0/0/0 | 2.467 | 0.019 | available | closed | bd8a400cf2c1 |
| [MarketBeat](https://www.marketbeat.com/feed) | 200 | 100 | 16/84/0/0 | 2.692 | 0.182 | available | closed | d9a322cb1d64 |
| [TechCrunch](https://techcrunch.com/rss) | 200 | 20 | 20/0/0/0 | 2.725 | 0.036 | available | closed | be23c8802834 |
| [VentureBeat](https://venturebeat.com/feed) | 429 | - | - | 2.532 | unknown | HTTP_429 | closed | d1fe60d9a85c |

Totals: 429 entries; 259 fresh, 170 stale, 0 future, 0 missing timestamps. Service elapsed 18.000s; helper total including cleanup 18.093s. No observed request timeout or budget exhaustion. All 21 requests completed, all responses closed, zero live owned workers after cleanup.

MarketWatch's 6.227s HTTP call did not raise a timeout: the scalar requests timeout applies to connection/read waits, not a total wall deadline. Source timing excludes separately observed response closure; unknown parse measurements remain null.

The exact verified IRON URL is absent from every captured feed. Fresh Microsoft brand text exists but the existing single-word alias guard rejects it. LFCR has no accepted match or Lifecore text observation. These are coverage/matching limitations, not proof that issuer news does not exist.

Business Insider and Markets Insider returned identical captured bytes (SHA256 `93a3da1765ec540896d6f96257ac4b39d5346f1c955c4722fb14fe413d30c165`); distinct configured URLs do not imply independent content. See [coverage analysis](live_coverage_analysis.md) for the issuer-specific findings and residual decisions.

PAPER_READY=NO
PAPER_READINESS_GATE=FAIL
