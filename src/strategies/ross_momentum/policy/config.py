from dataclasses import dataclass, field

from .entry_policy import EntryPolicy
from .execution_policy import ExecutionPolicy
from .filters_policy import FiltersPolicy
from .risk_policy import RiskPolicy
from .stop_policy import StopPolicy
from .target_policy import TargetPolicy
from .time_policy import TimePolicy
from .trailing_policy import TrailingPolicy


@dataclass(frozen=True)
class RossPolicyConfig:
    entry: EntryPolicy = field(default_factory=EntryPolicy)
    risk: RiskPolicy = field(default_factory=RiskPolicy)
    stop: StopPolicy = field(default_factory=StopPolicy)
    target: TargetPolicy = field(default_factory=TargetPolicy)
    trailing: TrailingPolicy = field(default_factory=TrailingPolicy)
    time: TimePolicy = field(default_factory=TimePolicy)
    execution: ExecutionPolicy = field(default_factory=ExecutionPolicy)
    filters: FiltersPolicy = field(default_factory=FiltersPolicy)


def get_default_ross_policy_config() -> RossPolicyConfig:
    return RossPolicyConfig()
