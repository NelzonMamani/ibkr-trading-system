"""Validation helpers used by doctor/bootstrap diagnostics."""
from __future__ import annotations

import importlib
from typing import Iterable, List


def validate_imports(modules: Iterable[str]) -> List[str]:
    failures: List[str] = []
    for module in modules:
        try:
            importlib.import_module(module)
        except Exception as exc:
            failures.append(f"{module}: {exc}")
    return failures
