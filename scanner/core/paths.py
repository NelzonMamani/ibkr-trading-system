from pathlib import Path


def get_scanner_root() -> Path:
    return Path(__file__).resolve().parents[1]


def get_verified_rss_path() -> Path:
    scanner_root = get_scanner_root()
    candidate = scanner_root / "verified_rss.txt"
    if candidate.exists():
        return candidate
    # fallback: if running from scanner/ directory directly
    alt = Path.cwd() / "verified_rss.txt"
    if alt.exists():
        return alt
    return candidate
