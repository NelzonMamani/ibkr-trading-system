import re
from typing import Optional


def normalize_title(text: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", " ", text or "")
    return re.sub(r"\s+", " ", cleaned).strip().lower()


def symbol_match(text: Optional[str], symbol: str) -> bool:
    if not text or not symbol:
        return False
    escaped = re.escape(symbol)
    pattern = re.compile(rf"(?<![A-Z0-9])\$?{escaped}(?![A-Z0-9])", re.IGNORECASE)
    return bool(pattern.search(text))
