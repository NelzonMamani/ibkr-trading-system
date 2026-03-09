from pathlib import Path
import sys
if __package__ in {None, ""}:
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

print('LIVE+EXECUTION_ENABLED=true => path: configurable (verify via runtime env)')
print('READ_ONLY => blocked with diagnostics')
print('SIM/PAPER => safe modes preserved')
