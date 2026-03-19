from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.config.config_resolver import set_config_overrides
from src.config.runtime_config import get_ibkr_api_write_allowed, get_ibkr_readonly_enabled


def main() -> None:
    scenarios = [
        ("LIVE_WRITABLE", {"RUN_MODE": "LIVE", "EXECUTION_ENABLED": True, "IBKR_READONLY_ENABLED": False, "IBKR_API_WRITE_ALLOWED": True}, False),
        ("LIVE_READONLY", {"RUN_MODE": "LIVE", "EXECUTION_ENABLED": False, "IBKR_READONLY_ENABLED": True, "IBKR_API_WRITE_ALLOWED": False}, True),
        ("PAPER", {"RUN_MODE": "PAPER", "IBKR_READONLY_ENABLED": False, "IBKR_API_WRITE_ALLOWED": True}, False),
        ("READ_ONLY", {"RUN_MODE": "READ_ONLY", "IBKR_READONLY_ENABLED": False, "IBKR_API_WRITE_ALLOWED": True}, True),
        ("SIM", {"RUN_MODE": "SIM", "IBKR_READONLY_ENABLED": False, "IBKR_API_WRITE_ALLOWED": True}, True),
    ]
    try:
        for label, overrides, expected_readonly in scenarios:
            set_config_overrides(overrides)
            actual = get_ibkr_readonly_enabled()
            assert actual is expected_readonly, (label, actual, expected_readonly)
            print(
                f"{label}: readonly={actual} api_write_allowed={get_ibkr_api_write_allowed()} overrides={overrides}"
            )
    finally:
        set_config_overrides(None)
    print("verify_live_write_vs_readonly_authority: PASS")


if __name__ == "__main__":
    main()
