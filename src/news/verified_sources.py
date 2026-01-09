from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse


def _default_verified_path() -> Path:
    repo_root = Path(__file__).resolve().parents[2]
    root_path = repo_root / "verified_rss.txt"
    if root_path.exists():
        return root_path
    fallback = repo_root / "src" / "scanner" / "verified_rss.txt"
    return fallback


def _is_valid_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _dedupe(seq: Iterable[str]) -> list[str]:
    seen = set()
    out = []
    for item in seq:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def load_verified_rss_sources(path: str | None = None) -> list[str]:
    rss_path = Path(path) if path else _default_verified_path()
    urls: list[str] = []
    if not rss_path.exists():
        logging.warning("[NEWS] verified_rss.txt not found at %s", rss_path)
        return []
    for line in rss_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if not _is_valid_url(line):
            logging.warning("[NEWS] Skipping invalid RSS URL: %s", line)
            continue
        urls.append(line)
    urls = _dedupe(urls)
    logging.info("[NEWS] Loaded %d verified RSS sources from %s", len(urls), rss_path)
    return urls
