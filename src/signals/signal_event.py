"""Signal event contract for deterministic teaching signals."""

from dataclasses import dataclass
from typing import Optional

from signals.signal_types import SignalType


@dataclass(frozen=True)
class SignalEvent:
    symbol: str
    signal_type: SignalType
    strength: float
    tick: int
    source: str = "SignalEngineV1"
    rationale: str = ""
    gap_percent: Optional[float] = None
    rvol: Optional[float] = None
    float_millions: Optional[float] = None

    def as_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "signal_type": self.signal_type.value,
            "strength": self.strength,
            "tick": self.tick,
            "source": self.source,
            "rationale": self.rationale,
            "gap_percent": self.gap_percent,
            "rvol": self.rvol,
            "float_millions": self.float_millions,
        }
