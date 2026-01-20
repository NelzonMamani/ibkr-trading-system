"""
Minimal, read-only configuration dump for runtime verification.
"""

from __future__ import annotations

from src.config.config_resolver import get_config


def _print_value(label: str, value) -> None:
    print(f"{label}: {value}")


def main() -> None:
    """Print resolved config highlights for audit/verification."""
    _print_value("resolved_run_mode", get_config("RUN_MODE_EFFECTIVE"))
    _print_value("execution_enabled", get_config("EXECUTION_ENABLED_EFFECTIVE"))
    _print_value("live_micro_required_quantity", get_config("LIVE_MICRO_REQUIRED_QUANTITY"))
    _print_value("live_micro_max_concurrent_trades", get_config("LIVE_MICRO_MAX_CONCURRENT_TRADES"))
    _print_value("paper_max_concurrent_trades", get_config("PAPER_MAX_CONCURRENT_TRADES"))
    _print_value("live_micro_daily_max_loss", get_config("LIVE_MICRO_DAILY_MAX_LOSS"))
    _print_value("daily_loss_warning_limit", get_config("DAILY_LOSS_WARNING_LIMIT"))
    _print_value("daily_loss_hard_limit", get_config("DAILY_LOSS_HARD_LIMIT"))
    _print_value("ibkr_max_symbols_per_cycle", get_config("IBKR_MAX_SYMBOLS_PER_CYCLE"))
    _print_value("live_micro_max_symbols_per_cycle", get_config("LIVE_MICRO_MAX_SYMBOLS_PER_CYCLE"))
    _print_value("scanner_top_gainers_count", get_config("SCANNER_TOP_GAINERS_COUNT"))
    _print_value("scanner_teaching_symbol_cap", get_config("SCANNER_TEACHING_SYMBOL_CAP"))
    _print_value("scanner_watchlist_limit", get_config("SCANNER_WATCHLIST_LIMIT"))
    _print_value("active_sessions", get_config("ACTIVE_SESSIONS"))


if __name__ == "__main__":
    main()
