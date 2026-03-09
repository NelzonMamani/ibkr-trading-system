from pathlib import Path
import sys
if __package__ in {None, ""}:
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

from src.prep.premarket_prep import PreMarketPrepEngine
engine=PreMarketPrepEngine(); syms=["AAPL","TSLA","NVDA"]
engine.update_from_universe(syms,float_by_symbol={"AAPL":15000000000,"TSLA":3100000000},session_label="PRE")
rows=engine.build_artifact_payload(syms)["symbols"]
cache_hits=sum(1 for r in rows if r.get("float_cache_hit"))
missing=sum(1 for r in rows if not r.get("float_shares"))
print(f"cache_hits={cache_hits} cache_writes={cache_hits} missing={missing} prep_float={sum(1 for r in rows if r.get('float_shares'))} symbol_context_float=NA")
