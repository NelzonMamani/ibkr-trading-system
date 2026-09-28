"""Inspect the canonical cache using the same revalidation as runtime consumers."""
from pathlib import Path
import sys
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json
from src.news.evidence_store import CanonicalNewsEvidenceStore, NEWS_INTELLIGENCE_CACHE_NAMESPACE
from src.news.news_intelligence_contract import NewsCandidate

store = CanonicalNewsEvidenceStore()
payload = json.loads(store.cache_path.read_text()) if store.cache_path.exists() else {}
symbols = set(payload.get("symbols", {})) | set(payload.get(NEWS_INTELLIGENCE_CACHE_NAMESPACE, {}).get("symbols", {}))
result = store.read([NewsCandidate(symbol) for symbol in sorted(symbols)], include_prep=False)
print("cache_file", store.cache_path)
print("symbols", len(symbols))
for symbol, summary in list(result.summaries_by_symbol.items())[:5]:
    print(symbol, summary.evidence_count, summary.fresh_evidence_count, summary.retrieval_status)
