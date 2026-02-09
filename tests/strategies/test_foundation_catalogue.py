from src.strategies.common import foundation


def test_foundation_lists_include_required_items():
    assert "SF_GAP_AND_GO" in foundation.SETUP_FAMILIES
    assert "11_XL_LIQUIDITY_SWEEP_RECLAIM" in foundation.EXECUTION_TRIGGERS
    assert "C_TREND_ALIGNMENT" in foundation.CONDITIONS
    assert "K_DATA_QUALITY_CONFIRM" in foundation.CONFIRMATIONS


def test_translation_report_flags_unknown_components():
    report = foundation.build_translation_report(
        strategy_id="test",
        foundation_version=foundation.FOUNDATION_VERSION,
        setup_families=["SF_GAP_AND_GO", "UNKNOWN"],
    )
    assert report.compatible is True
    assert "UNKNOWN" in report.extra_components


def test_symbol_context_hydration_is_complete():
    context = foundation.hydrate_symbol_context("AAPL", has_news=True)
    assert context.hydration_complete is True
    assert context.has_news is True
