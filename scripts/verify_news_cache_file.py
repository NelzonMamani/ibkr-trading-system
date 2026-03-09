from pathlib import Path
import sys
if __package__ in {None, ""}:
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

import json
from src.data.news.news_provider import NewsProvider
p=NewsProvider(); data=json.loads(p.cache_file.read_text()) if p.cache_file.exists() else {"symbols":{}}
print("cache_file",p.cache_file)
print("symbols",len(data.get("symbols",{})))
for s,v in list((data.get("symbols") or {}).items())[:5]:
    fresh=sum(1 for x in v.get("news_context",[]) if x.get("freshness")=="fresh")
    stale=sum(1 for x in v.get("news_context",[]) if x.get("freshness")!="fresh")
    print(s,v.get("fetched_at"),fresh,stale)
