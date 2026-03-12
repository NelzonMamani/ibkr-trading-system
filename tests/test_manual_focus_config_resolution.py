from src.core.orchestrator import MANUAL_FOCUS_PATH


def test_manual_focus_config_path_exists():
    assert MANUAL_FOCUS_PATH.exists()
