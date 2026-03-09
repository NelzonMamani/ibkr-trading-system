from pathlib import Path
import sys
if __package__ in {None, ""}:
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
from src.scanner.scanner_runner import _candidate_from_context, GateThresholds
ctx={"symbol":"AAPL","session":"PRE","last_price":100,"prev_close":95,"pct_change":5,"rvol":3,"volume":100000,"float_shares":10000000}
news={"news_present":True,"catalyst_type":"earnings","news_count":2,"fresh_news_count":1,"stale_news_count":1,"top_news_catalyst_tag":"earnings"}
thresholds=GateThresholds(1,50,1,200,1,1,1000,1000,1000000000,5,10000,True,False,False,False,False)
c=_candidate_from_context(ctx,news,thresholds,drop_reason=None,timestamp_utc="now")
print(c.symbol,c.news_count,c.top_news_catalyst_tag,c.catalyst_summary)
