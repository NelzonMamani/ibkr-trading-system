from __future__ import annotations

import importlib
import importlib.util
import time
from collections import Counter
from urllib.parse import urlparse

from src.news.verified_sources import load_verified_rss_sources

if importlib.util.find_spec("requests"):
    requests = importlib.import_module("requests")  # type: ignore
else:  # pragma: no cover - optional dependency
    requests = None


def _domain_from_url(url: str) -> str:
    host = urlparse(url).netloc.lower()
    host = host.split("@")[-1]
    return host[4:] if host.startswith("www.") else host


def validate_rss(timeout_s: float = 5.0) -> int:
    urls = load_verified_rss_sources()
    if not urls:
        print("[RSS] No verified RSS sources configured.")
        return 1

    if requests is None:
        print("[RSS] requests not installed; cannot validate RSS URLs.")
        return 2

    ok = 0
    failures = 0
    failures_by_domain: Counter[str] = Counter()
    failures_by_code: Counter[str] = Counter()

    for url in urls:
        domain = _domain_from_url(url)
        try:
            response = requests.get(
                url,
                timeout=timeout_s,
                headers={
                    "User-Agent": "IBKRScanner/1.0 (+https://github.com/NelzonMamani/ibkr-trading-system)",
                    "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.8",
                },
            )
            response.raise_for_status()
            ok += 1
        except Exception as exc:
            failures += 1
            code = str(getattr(getattr(exc, "response", None), "status_code", "error"))
            failures_by_domain[domain or url] += 1
            failures_by_code[code] += 1
        time.sleep(0.2)

    print(f"[RSS] total={len(urls)} ok={ok} failures={failures}")
    if failures:
        domain_summary = ", ".join(
            f"{domain}={count}" for domain, count in failures_by_domain.most_common(5)
        )
        code_summary = ", ".join(
            f"{code}={count}" for code, count in failures_by_code.most_common(5)
        )
        print(f"[RSS] top_domains=[{domain_summary}] top_codes=[{code_summary}]")

    return 0 if failures == 0 else 3


if __name__ == "__main__":
    raise SystemExit(validate_rss())
