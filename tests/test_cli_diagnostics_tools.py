from __future__ import annotations

import importlib


def test_diagnostics_modules_import() -> None:
    assert importlib.import_module("src.cli.ibkr_scanner_diagnostics") is not None
    assert importlib.import_module("src.cli.test_trade_pipeline") is not None
    assert importlib.import_module("src.cli.live_readiness_check") is not None


def test_scanner_cli_arg_parsing() -> None:
    module = importlib.import_module("src.cli.ibkr_scanner_diagnostics")
    args = module.parse_args(["--dry-run"])
    assert args.dry_run is True


def test_trade_pipeline_cli_arg_parsing() -> None:
    module = importlib.import_module("src.cli.test_trade_pipeline")
    args = module.parse_args(["--symbol", "AAPL", "--execute-live", "--dry-run"])
    assert args.symbol == "AAPL"
    assert args.execute_live is True
    assert args.dry_run is True


def test_live_readiness_cli_arg_parsing() -> None:
    module = importlib.import_module("src.cli.live_readiness_check")
    args = module.parse_args(["--symbol", "AAPL", "--dry-run"])
    assert args.symbol == "AAPL"
    assert args.dry_run is True


def test_cli_entrypoints_run_without_crash() -> None:
    scanner = importlib.import_module("src.cli.ibkr_scanner_diagnostics")
    pipeline = importlib.import_module("src.cli.test_trade_pipeline")
    readiness = importlib.import_module("src.cli.live_readiness_check")

    assert scanner.main(["--dry-run"]) == 0
    assert pipeline.main(["--symbol", "AAPL", "--dry-run"]) == 0
    assert readiness.main(["--dry-run"]) == 0
