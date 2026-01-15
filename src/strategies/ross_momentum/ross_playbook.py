"""Ross Momentum playbook configuration (Phase 1)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RossPlaybook:
    min_confidence: float = 0.6
    allow_after_hours: bool = False


DEFAULT_PLAYBOOK = RossPlaybook()
