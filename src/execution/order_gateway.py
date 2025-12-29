import hashlib
from enum import Enum


class GatewayDecision(str, Enum):
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    SOFT_REJECT = "SOFT_REJECT"


class OrderGateway:
    """Deterministic gateway that models broker/route acceptance behavior."""

    @staticmethod
    def _decision_components(
        symbol: str, tick: int, trader_type: str, attempt_number: int
    ):
        key = f"{symbol}|{tick}|{trader_type}|{attempt_number}|GATEWAY"
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        mapped = int(digest[:8], 16)
        r_value = mapped % 10
        return key, r_value

    def decide(
        self, symbol: str, tick: int, trader_type: str, attempt_number: int
    ) -> GatewayDecision:
        """
        Deterministic decision derived solely from the provided inputs.

        Mapping:
        - r in {0}: hard reject
        - r in {1, 2}: soft reject
        - r in {3..9}: accept
        """

        _, r_value = self._decision_components(symbol, tick, trader_type, attempt_number)
        if r_value == 0:
            return GatewayDecision.REJECT
        if r_value in {1, 2}:
            return GatewayDecision.SOFT_REJECT
        return GatewayDecision.ACCEPT

    def decide_with_trace(
        self, symbol: str, tick: int, trader_type: str, attempt_number: int
    ):
        decision_key, r_value = self._decision_components(
            symbol, tick, trader_type, attempt_number
        )
        return (
            self.decide(symbol, tick, trader_type, attempt_number),
            decision_key,
            r_value,
        )
