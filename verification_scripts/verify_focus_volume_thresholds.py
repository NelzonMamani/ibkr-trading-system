from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.scanner.scanner_runner import _evaluate_focus_gates, _gate_thresholds, _resolve_runtime_thresholds
from src.strategies.ross_momentum.strategy_policy import RossMomentumPolicy


def main() -> None:
    policy = RossMomentumPolicy().stock_selection
    runtime = _resolve_runtime_thresholds(policy)
    thresholds = _gate_thresholds(policy, runtime)

    print("=== FOCUS VOLUME THRESHOLD VERIFIER ===")
    print(f"policy_min_volume={thresholds.min_volume}")
    print(f"focus_volume_min={thresholds.focus_volume_min}")
    for session in ("RTH_OPEN", "RTH_MID", "RTH_LATE", "AH"):
        print(
            f"session_focus_volume_min[{session}]="
            f"{thresholds.session_focus_volume_min.get(session, thresholds.focus_volume_min)}"
        )

    candidates = [
        {
            "symbol": "ROSS_OK",
            "session": "RTH_MID",
            "phase": "RTH_MID",
            "pct_change": 28.4,
            "rvol_discovery": 4.6,
            "rvol_phase": 4.1,
            "volume": 511_545,
            "premarket_volume": 180_000,
            "dollar_volume": 2_558_000,
            "last_price": 5.0,
            "spread_pct": 0.012,
            "bid": 4.99,
            "ask": 5.01,
            "catalyst_present": True,
            "halted": False,
            "ssr": False,
        },
        {
            "symbol": "THIN_FAIL",
            "session": "RTH_MID",
            "phase": "RTH_MID",
            "pct_change": 15.0,
            "rvol_discovery": 2.8,
            "rvol_phase": 2.6,
            "volume": 25_000,
            "premarket_volume": 10_000,
            "dollar_volume": 62_500,
            "last_price": 2.5,
            "spread_pct": 0.014,
            "bid": 2.49,
            "ask": 2.51,
            "catalyst_present": True,
            "halted": False,
            "ssr": False,
        },
    ]

    for candidate in candidates:
        verdict = _evaluate_focus_gates(candidate.copy(), thresholds)
        print(
            f"candidate={candidate['symbol']} session={candidate['session']} volume={candidate['volume']} "
            f"decision={'PASS' if verdict is None else verdict}"
        )


if __name__ == "__main__":
    main()
