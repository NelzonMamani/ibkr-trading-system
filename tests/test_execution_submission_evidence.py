"""Adversarial native-result submission evidence, no routing or broker access."""
import pytest
from src.execution.execution_engine import ExecutionEngine
from src.models.execution_result import ExecutionResult


@pytest.mark.parametrize("attempted,status,broker_id,expected",[
    (True,"Submitted",71,True),(True,"PreSubmitted",71,True),(True,"Filled",71,True),
    (False,"Submitted",71,False),(True,"Submitted",None,False),
    (True,"PendingSubmit",71,False),(True,"PendingCancel",71,False),
    (True,"REJECTED",71,False),(True,"SUBMISSION_UNKNOWN",71,False),
    (True,"SIMULATED",None,False),
])
def test_attempt_or_identifier_alone_cannot_manufacture_submission(attempted,status,broker_id,expected):
    result=ExecutionResult(symbol="SYNTH",trader_type="SYNTHETIC",attempted=attempted,
        status=status,rationale="synthetic native result",ibkr_order_id=broker_id)
    assert ExecutionEngine.submission_confirmed(result) is expected
