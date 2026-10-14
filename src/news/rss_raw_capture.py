"""Bounded opt-in HTTP evidence sidecars, never read by the canonical store."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

RAW_FEED_BYTES = 512 * 1024


class RawFeedLimitExceeded(ValueError):
    pass


class RawFeedCapture:
    def __init__(self, directory):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=False)
        self.evaluation_time_utc = None

    def save(self, url, body, *, complete, status, acquired_at, error=None):
        key = hashlib.sha256(url.encode()).hexdigest()
        raw = self.directory / (key + ".xml")
        raw.write_bytes(body)
        record = {"schema": "news.raw_rss.v1", "url": url, "body_file": raw.name,
                  "acquired_at": acquired_at, "recorded_at": datetime.now(timezone.utc).isoformat(),
                  "evaluation_time_utc": self.evaluation_time_utc,
                  "http_status": status, "bytes_captured": len(body), "byte_limit": RAW_FEED_BYTES,
                  "body_complete": complete, "sha256": hashlib.sha256(body).hexdigest(),
                  "error": error, "replay_requires_recorded_acquisition_time": True}
        manifest = self.directory / (key + ".json")
        temporary = self.directory / (key + ".writing")
        temporary.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        temporary.replace(manifest)
        return record
