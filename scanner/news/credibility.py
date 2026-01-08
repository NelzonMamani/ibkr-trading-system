from typing import Dict

DOMAIN_CREDIBILITY: Dict[str, float] = {
    "reuters.com": 0.95,
    "bloomberg.com": 0.92,
    "wsj.com": 0.9,
    "ft.com": 0.9,
    "cnbc.com": 0.85,
    "marketwatch.com": 0.8,
    "finance.yahoo.com": 0.78,
    "seekingalpha.com": 0.75,
    "benzinga.com": 0.7,
    "thestreet.com": 0.7,
    "globenewswire.com": 0.68,
    "prnewswire.com": 0.66,
    "businesswire.com": 0.66,
}


def credibility_score(domain: str) -> float:
    if not domain:
        return 0.6
    domain = domain.lower()
    if domain in DOMAIN_CREDIBILITY:
        return DOMAIN_CREDIBILITY[domain]
    for key, value in DOMAIN_CREDIBILITY.items():
        if domain.endswith(key):
            return value
    return 0.6
