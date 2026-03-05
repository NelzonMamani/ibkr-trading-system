"""P01 capital deployment verification for Ross Momentum."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.strategies.ross_momentum.strategy_policy import RossMomentumPolicy


def main() -> int:
    available_funds = 21000
    policy = RossMomentumPolicy()
    max_position_allowed = int(
        available_funds * policy.capital_deployment.max_position_fraction_of_account
    )
    is_full_funds_enabled = (
        policy.capital_deployment.use_full_available_funds
        and policy.capital_deployment.capital_source == "AVAILABLE_FUNDS"
        and policy.capital_deployment.max_simultaneous_positions == 1
        and policy.risk_model.allow_full_capital_deployment
    )
    passed = is_full_funds_enabled and max_position_allowed <= available_funds

    payload = {
        "available_funds": available_funds,
        "max_position_allowed": max_position_allowed,
        "pass": passed,
    }

    output_path = Path(
        "AUDIT_EVIDENCE/p01_capital_deployment/capital_deployment_check.json"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2))

    print(json.dumps(payload))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
