import io
import logging
import sys

from src import main as main_module
from src.ibkr import evidence_safety as privacy
from src.strategy import strategy_runner


def test_protected_console_keeps_optional_config_fallback_and_redaction(monkeypatch):
    # Reproduce redirected Windows output and the real startup ordering.
    buffers = {name: io.BytesIO() for name in ("stdout", "stderr")}
    streams = {
        name: io.TextIOWrapper(buffer, encoding="cp1252", errors="strict", newline="\n", write_through=True)
        for name, buffer in buffers.items()
    }
    original_streams = {name: getattr(sys, name) for name in streams}
    monkeypatch.setattr(privacy, "_tokens", set())
    token = "synthetic-account-alpha"
    privacy.register_account(token)
    monkeypatch.setattr(logging, "_logRecordFactory", logging.getLogRecordFactory())
    for name in ("ibapi", "ib_insync"):
        logger = logging.getLogger(name)
        monkeypatch.setattr(logger, "handlers", list(logger.handlers))
        monkeypatch.setattr(logger, "propagate", logger.propagate)
        monkeypatch.setattr(logger, "level", logger.level)
    for name, stream in streams.items():
        monkeypatch.setattr(sys, name, stream)

    privacy.install_console_protection()
    main_module._configure_console_output()

    def missing_config(key):
        raise KeyError(key)

    monkeypatch.setattr(strategy_runner, "get_config", missing_config)
    assert strategy_runner.safe_get_config("MAX_POSITIONS", default=1) == 1
    for name in streams:
        protected = getattr(sys, name)
        assert isinstance(protected, privacy.SafeTextStream)
        assert streams[name].errors == "replace"
        before = buffers[name].getvalue()
        protected.write(token[:10])
        protected.reconfigure(errors="replace")
        protected.flush()
        assert buffers[name].getvalue() == before
        protected.write(token[10:] + " \u2192 safe\n")
        protected.write(token)
        protected.finish()
        assert token.encode("ascii") not in buffers[name].getvalue()
        assert buffers[name].getvalue().endswith(b"REDACTED ? safe\nREDACTED")

    for name, stream in original_streams.items():
        monkeypatch.setattr(sys, name, stream)
    assert (
        b"[CONFIG][WARN] Missing optional config: MAX_POSITIONS ? using default=1\n"
        in buffers["stdout"].getvalue()
    )


def test_text_reconfiguration_preserves_utf8_output():
    buffer = io.BytesIO()
    stream = io.TextIOWrapper(buffer, encoding="utf-8", errors="strict", newline="\n", write_through=True)
    protected = privacy.SafeTextStream(stream)
    protected.reconfigure(errors="replace")
    protected.write("diagnostic \u2192 preserved\n")
    protected.finish()
    assert buffer.getvalue().decode("utf-8") == "diagnostic \u2192 preserved\n"
