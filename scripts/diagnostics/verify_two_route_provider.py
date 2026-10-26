"""Exactly two shared provider candidates; no production source activation."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.diagnostics.rss_feed_diagnostic import DiagnosticProfile, RssFeedDiagnostic

PROFILE = DiagnosticProfile(
    name='ross_two_route_provider_verification',
    schema='ross.two_route_provider_verification.v1',
    production='e5c5ad60a99d0b2128a05ce5d3f418bf2b7e9a98',
    urls=('https://www.investing.com/rss/news.rss', 'https://www.forbes.com/business/feed2'),
    issuer_pairs=(('AZTR', 'AZITRA INC'), ('RENT', 'RENT THE RUNWAY INC-A'),
                  ('GCTK', 'GLUCOTRACK INC'), ('SPRC', 'SCISPARC LTD')),
    archive_name='ross-two-route-provider-shareable.zip',
)
DIAGNOSTIC = RssFeedDiagnostic(PROFILE)

if __name__ == '__main__':
    raise SystemExit(DIAGNOSTIC.main(__file__))
