from pathlib import Path
import sys
if __package__ in {None, ""}:
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

from src.data.news.news_provider import NewsProvider
symbols=["AAPL","TSLA","NVDA","PLTR","AMD"]
p=NewsProvider(); r=p.get_news_batch(symbols)
for s in symbols:
    n=r[s]; top=n.news_context[0] if n.news_context else {}
    print(f"{s} count={len(n.news_context)} fresh={sum(1 for x in n.news_context if x.get('freshness')=='fresh')} tag={top.get('catalyst_tag')} headline={top.get('title')}")
