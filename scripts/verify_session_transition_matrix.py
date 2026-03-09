from pathlib import Path
import sys
if __package__ in {None, ""}:
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

from src.prep.premarket_prep import PreMarketPrepEngine
e=PreMarketPrepEngine(); syms=["AAPL","TSLA"]
for frm,to in [("CLOSED","WEEKEND"),("WEEKEND","OVN"),("OVN","PRE"),("PRE","RTH"),("RTH","AH")]:
    e.update_from_universe(syms,session_label=frm)
    e.update_from_universe([],session_label=to,reason=f"{frm}_TO_{to}")
    rows=e.build_artifact_payload(syms)["symbols"]
    print(frm,to,[ (r['symbol'],r.get('context_status'),r.get('last_transition_reason')) for r in rows])
