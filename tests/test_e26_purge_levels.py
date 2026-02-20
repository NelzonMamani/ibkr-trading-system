from __future__ import annotations

from pathlib import Path

from src.runtime.bootstrap import bootstrap_runtime
from src.runtime.regen import _purge


def test_e26_purge_level_semantics(monkeypatch, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    logs_dir = tmp_path / "logs"
    output_dir = tmp_path / "output"
    sqlite_path = data_dir / "ibkr_system.db"

    monkeypatch.setenv("IBKR_OS_DATA_DIR", str(data_dir))
    monkeypatch.setenv("IBKR_OS_LOG_DIR", str(logs_dir))
    monkeypatch.setenv("IBKR_OS_OUTPUT_DIR", str(output_dir))
    monkeypatch.setenv("PERSISTENCE_SQLITE_PATH", str(sqlite_path))

    bootstrap_runtime()
    logs_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    (logs_dir / "runtime.log").write_text("x", encoding="utf-8")
    (output_dir / "report.txt").write_text("x", encoding="utf-8")

    _purge("LIGHT")
    assert sqlite_path.exists()
    assert not any(logs_dir.iterdir())
    assert not any(output_dir.iterdir())

    (logs_dir / "runtime.log").write_text("x", encoding="utf-8")
    (output_dir / "report.txt").write_text("x", encoding="utf-8")
    _purge("HARD")
    assert not sqlite_path.exists()
    assert not any(logs_dir.iterdir())
    assert not any(output_dir.iterdir())
