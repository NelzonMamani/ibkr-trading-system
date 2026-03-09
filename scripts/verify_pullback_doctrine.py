from pathlib import Path
import sys
if __package__ in {None, ""}:
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

tiers=[30,40,50]
for t in tiers:
    state='ideal' if t<=40 else 'caution'
    print(f"retracement={t}% state={state}")
print("bail_state_reachable=True intrabar_override_wired=partial")
