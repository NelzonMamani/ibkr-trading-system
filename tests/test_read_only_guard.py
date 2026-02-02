from __future__ import annotations

from pathlib import Path
import sys

import pytest

repo_root = Path(__file__).resolve().parents[1]
sys.path.append(str(repo_root))
sys.path.append(str(repo_root / "src"))

from config.config_resolver import set_config_overrides
from ibkr.read_only_guard import assert_read_only_allows


@pytest.fixture(autouse=True)
def _reset_config_overrides():
    set_config_overrides({})
    yield
    set_config_overrides({})


def test_read_only_guard_blocks_when_readonly_enabled():
    set_config_overrides(
        {
            "RUN_MODE": "READ_ONLY",
        }
    )
    with pytest.raises(RuntimeError, match="IBKR read-only enabled"):
        assert_read_only_allows("PLACE_ORDER")
