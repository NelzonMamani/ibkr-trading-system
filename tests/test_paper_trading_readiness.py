from src.config.config_resolver import set_config_overrides
from src.core.paper_trading_readiness import run_paper_trading_readiness_check


def test_paper_readiness_passes_without_live_connection_probe():
    set_config_overrides(None)
    report = run_paper_trading_readiness_check(
        ensure_connection=False,
    )
    assert report.is_pass is True
    assert any("EXECUTION_ENABLED_EFFECTIVE=True" in item for item in report.checks_passed)


def test_paper_readiness_fails_when_connection_probe_fails():
    set_config_overrides(None)

    def _probe():
        raise RuntimeError("no_tws")

    report = run_paper_trading_readiness_check(ensure_connection=True, connection_probe=_probe)
    assert report.is_pass is False
    assert any("connection probe failed" in item.lower() for item in report.failures)
