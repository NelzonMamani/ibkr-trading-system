"""IBKR utilities, with guard imports deferred until first use."""

__all__ = ["assert_read_only_allows", "validate_read_only_guard"]


def __getattr__(name):
    if name in __all__:
        from src.ibkr import read_only_guard
        return getattr(read_only_guard, name)
    raise AttributeError(name)
