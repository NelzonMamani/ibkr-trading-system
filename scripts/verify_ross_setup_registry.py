from pathlib import Path
import sys
if __package__ in {None, ""}:
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

from src.setup_engine.registry import CANONICAL_SETUP_REGISTRY
for k,v in sorted(CANONICAL_SETUP_REGISTRY.items()):
    print(k,v.status.value,v.pattern_cls.__name__)
print('core', [x for x in ['GAP_GO','ORB','MICRO_PULLBACK','FIRST_PULLBACK','HOD_BREAK','VWAP_PULLBACK'] if x in CANONICAL_SETUP_REGISTRY])
