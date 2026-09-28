"""Shared issuer revalidation for fresh and persisted news evidence."""
from src.news.news_fetcher import symbol_relevance_match
from src.news.news_intelligence_contract import NewsBatchResult, NewsEvidence


def evidence_issuer_relevance_verified(
    symbol: str, item: NewsEvidence, result: NewsBatchResult
) -> bool:
    # Recheck text-derived RSS evidence at every consumer boundary, including
    # persisted entries written before the matcher was hardened. A cached
    # ticker_token/classification field is not proof of issuer identity.
    if item.provider not in {"rss_batch", "prep_cache", "legacy_news_provider_cache"} and item.match_type not in {
        "ticker_token", "company_name", "prep_context"
    }:
        return True
    candidate = next((row for row in result.candidates if row.normalized_symbol == symbol), None)
    metadata = dict(candidate.metadata) if candidate is not None else {}
    metadata["company_name"] = (
        item.company_name
        or (candidate.company_name if candidate is not None else None)
        or metadata.get("company_name")
    )
    metadata["aliases"] = (
        metadata.get("aliases") or (),
        metadata.get("company_aliases") or (),
        metadata.get("issuer_aliases") or (),
        tuple(item.aliases),
        tuple(candidate.aliases) if candidate is not None else (),
    )
    return symbol_relevance_match(
        symbol, title=str(item.headline or ""), summary=str(item.summary or ""), metadata=metadata
    ) is not None
