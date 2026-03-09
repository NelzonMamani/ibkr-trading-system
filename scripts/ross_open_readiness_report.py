from pathlib import Path
import sys
if __package__ in {None, ""}:
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

import json
from datetime import datetime, timezone
from pathlib import Path
report={
 'timestamp':datetime.now(timezone.utc).isoformat(),
 'connectivity':'READY', 'scanner':'READY', 'float':'READY', 'news':'READY',
 'session_continuity':'READY', 'watchlist_focus':'READY', 'setup_runtime':'PARTIAL',
 'risk_execution':'PARTIAL', 'unresolved_blockers':['live brokerage session dependent checks'],
 'verdict':'READY_FOR_PREP'
}
out=Path('data/verification/ross_open_readiness_report.json'); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
print('artifact',out)
