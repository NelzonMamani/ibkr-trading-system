from pathlib import Path
import sys
if __package__ in {None, ""}:
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

from src.prep.premarket_prep import PreMarketPrepEngine
engine=PreMarketPrepEngine(); syms=["AAPL","TSLA"]
engine.update_from_universe(syms, session_label="PRE")
rows=engine.build_artifact_payload(syms)["symbols"]
for r in rows:
    print(r["symbol"], r.get("news_count"), r.get("fresh_news_count"), r.get("top_news_catalyst_tag"), r.get("top_news_title"))
