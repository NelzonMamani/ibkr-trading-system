from src.strategies.ross_momentum.patterns.pattern_types import PatternResult

__all__ = ["RossPatternRegistry", "PatternResult"]


def __getattr__(name: str):
    if name == "RossPatternRegistry":
        from src.strategies.ross_momentum.patterns.pattern_registry import RossPatternRegistry

        return RossPatternRegistry
    raise AttributeError(name)
