"""Authoritative execution ledger exceptions and helpers."""


class ExecutionIntegrityError(RuntimeError):
    """Raised when broker callback data violates fill integrity constraints."""

