from __future__ import annotations

from pathlib import Path
import sys

if __package__ in {None, ""}:
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

from src.data.news.news_provider import NewsProvider


def main() -> None:
    provider = NewsProvider()
    symbols = ["AAPL", "TSLA", "NVDA", "PLTR", "AMD"]
    results = provider.get_news_batch(symbols)
    print("NEWS DISCOVERY TEST")
    for symbol in symbols:
        result = results[symbol]
        print(f"{symbol} headlines={len(result.news_context)} mode={result.source_mode} errors={len(result.diagnostics.get('errors', []))}")
        if result.news_context:
            top = result.news_context[0]
            print(f"  top={top.get('catalyst_tag')} freshness={top.get('freshness')} age_hours={top.get('age_hours')}")
    print(f"cache_file={provider.cache_file}")


if __name__ == "__main__":
    main()
