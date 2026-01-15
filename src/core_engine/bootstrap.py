"""Bootstrap utilities for core engine diagnostics."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional

from src.config.config_resolver import resolve_config, set_config_overrides
from src.utils.validation import validate_imports


@dataclass(frozen=True)
class BootstrapStatus:
    imports_ok: bool
    config_ok: bool
    import_failures: List[str]
    config_error: Optional[str]


def apply_doctor_overrides() -> None:
    """Force a safe READONLY configuration for doctor checks."""
    set_config_overrides(
        {
            "RUN_MODE": "LIVE_READ_ONLY",
            "EXECUTION_ENABLED": False,
            "IBKR_API_WRITE_ALLOWED": False,
            "IBKR_READONLY_ENABLED": True,
        }
    )


def run_bootstrap_checks(modules: Iterable[str]) -> BootstrapStatus:
    import_failures = validate_imports(modules)
    imports_ok = not import_failures

    config_error = None
    config_ok = True
    try:
        resolve_config()
    except Exception as exc:
        config_ok = False
        config_error = str(exc)

    return BootstrapStatus(
        imports_ok=imports_ok,
        config_ok=config_ok,
        import_failures=import_failures,
        config_error=config_error,
    )
