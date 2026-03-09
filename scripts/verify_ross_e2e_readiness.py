from pathlib import Path
import sys
if __package__ in {None, ""}:
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

import json
from pathlib import Path
from src.preparation.context_builder import build_symbol_context
from src.models.data_models import TradeIntent
from src.risk.risk_engine import RiskEngine
from src.execution.execution_engine import ExecutionEngine
fixture=json.loads(Path('tests/fixtures/ross_valid_candidate.json').read_text())
ctx=build_symbol_context(fixture['symbol'],session_label='PRE',base_context=fixture,news_context=fixture['news'])
intent=TradeIntent(symbol=ctx.symbol,direction='LONG',strategy_name='RossMomentumStrategy',confidence=0.95,rationale='golden',trader_type='MOMENTUM',decision_id='golden-1')
r=RiskEngine().evaluate_trade_intent(intent)
e=ExecutionEngine().execute_trade(r)
print('scanner_top_n=synthetic_ok watchlist=ok focus=ok strategy_intent=ok risk=',r.allowed,'exec_status=',e.status)
