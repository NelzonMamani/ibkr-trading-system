from __future__ import annotations

from pathlib import Path

from src.runtime.bootstrap import bootstrap_runtime


def test_e26_bootstrap_recreates_runtime_dirs_and_db(monkeypatch, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    logs_dir = tmp_path / "logs"
    output_dir = tmp_path / "output"

    monkeypatch.setenv("IBKR_OS_DATA_DIR", str(data_dir))
    monkeypatch.setenv("IBKR_OS_LOG_DIR", str(logs_dir))
    monkeypatch.setenv("IBKR_OS_OUTPUT_DIR", str(output_dir))
    monkeypatch.setenv("PERSISTENCE_SQLITE_PATH", str(data_dir / "ibkr_system.db"))

    result = bootstrap_runtime()

    assert Path(result["data_dir"]).exists()
    assert Path(result["logs_dir"]).exists()
    assert Path(result["output_dir"]).exists()
    assert Path(result["sqlite_path"]).exists()
