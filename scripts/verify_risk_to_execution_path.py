from pathlib import Path
import sys
if __package__ in {None, ""}:
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

from src.models.data_models import TradeIntent
from src.risk.risk_engine import RiskEngine
from src.execution.execution_engine import ExecutionEngine
intent=TradeIntent(symbol='ROSSX',direction='LONG',strategy_name='RossMomentumStrategy',confidence=0.9,rationale='fixture',trader_type='MOMENTUM',decision_id='d1')
r=RiskEngine().evaluate_trade_intent(intent)
e=ExecutionEngine().execute_trade(r)
print('risk_input',intent.symbol,intent.direction)
print('risk_verdict',r.allowed,r.reason_code,r.risk_reasons)
print('execution_eligibility',e.status,e.rationale)
