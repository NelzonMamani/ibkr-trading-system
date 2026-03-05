from __future__ import annotations

import json
from pathlib import Path
import sys

if __package__ in {None, ""}:
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

from src.scanner.providers.mock_provider import MockScannerProvider
from src.scanner.scanner_runner import run_scanner_cycle
from src.strategies.ross_momentum.strategy_policy import RossMomentumPolicy
from src.scanner.scanner_contract import scanner_request_from_policy
from src.prep.premarket_prep_artifact import write_premarket_prep_artifact


def main() -> int:
    out = Path("AUDIT_EVIDENCE/p01_premarket_prep/premarket_prep_watchlist.json")
    if out.exists():
        out.unlink()

    policy = RossMomentumPolicy().stock_selection
    request = scanner_request_from_policy(policy, strategy_name="ross_momentum", session_phase="PREMARKET")
    payload = run_scanner_cycle(
        mode="READ_ONLY",
        policy=policy,
        scanner_request=request,
        provider=MockScannerProvider(seed=7),
        disconnect_provider=False,
        forced_session_label="PRE",
    )
    write_premarket_prep_artifact(mode="READ_ONLY", session="PRE", scanner_payload=payload, watchlist_k=policy.watchlist_limit_k)

    if not out.exists():
        raise SystemExit("missing evidence JSON")
    evidence = json.loads(out.read_text(encoding="utf-8"))
    if int(evidence.get("prep_watchlist_k", 0)) <= 0:
        raise SystemExit("prep_watchlist_k must be > 0")
    float_cache = evidence.get("float_cache") or {}
    for key in ("hit", "miss", "unknown"):
        if key not in float_cache:
            raise SystemExit(f"missing float_cache.{key}")
    print("[OK] p01_premarket_prep_smoke")
    print(f"evidence={out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
