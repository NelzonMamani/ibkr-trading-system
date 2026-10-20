"""Report actual empty strategy boundary without fabricating Watchlist absence."""
import pytest


@pytest.mark.parametrize('watchlist,focus,reason', [([],[],'EMPTY_WATCHLIST'),
    (['WORX','AIXI'],[],'NO_FOCUS_CANDIDATES'),(['WORX'],['WORX'],'NO_STRATEGY_INPUTS')])
def test_strategy_skip_names_actual_empty_boundary(capsys, watchlist, focus, reason):
    from src.core.orchestrator import _report_strategy_input_skip
    _report_strategy_input_skip(watchlist, focus)
    out = capsys.readouterr().out
    assert f'reason={reason}' in out
    assert f'watchlist_count={len(watchlist)}' in out
    assert f'focus_count={len(focus)}' in out
    assert 'empty watchlist' not in out
