"""Account privacy at observable boundaries; sensitive tokens never leave memory."""
from __future__ import annotations

import copy
import json
import logging
import os
import re
import atexit
from contextlib import contextmanager
from pathlib import Path
import sys
import threading

REDACTED = "REDACTED"
_ACCOUNT_KEYS = {"account", "accountid", "account_id", "acctnumber", "accounts", "managedaccounts", "account_id_redacted", "acctcode", "accountcode"}
_lock = threading.RLock()
_tokens: set[str] = set()
_ACCOUNT_PATTERN = re.compile(r"(?<![A-Za-z0-9])(?:DU|U|DF|F)[0-9]{5,}(?![A-Za-z0-9])")


def register_account(value):
    if isinstance(value, str):
        with _lock:
            _tokens.update(t.strip() for t in value.split(",") if t.strip() and t.strip().upper() not in {REDACTED, "UNKNOWN", "NONE", "N/A", "REDACTED_ACCOUNT", "[REDACTED]", "NO_SECRET_DATA_PRESENT"})
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            register_account(item)


def scrub_text(value: str) -> str:
    with _lock:
        for token in sorted(_tokens, key=len, reverse=True):
            value = value.replace(token, REDACTED)
    return _ACCOUNT_PATTERN.sub(REDACTED, value)


def _account_key(key):
    return str(key).lower() in _ACCOUNT_KEYS


def register_payload(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if _account_key(key):
                register_account(child)
            else:
                register_payload(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            register_payload(child)
    elif hasattr(value, "__dict__"):
        register_payload(vars(value))


def sanitize(value):
    # Register all fields before handling free-form siblings, irrespective of order.
    register_payload(value)
    def clean(item):
        if isinstance(item, str):
            return scrub_text(item)
        if isinstance(item, dict):
            return {scrub_text(str(k)): (v if isinstance(v, str) and v in {REDACTED, "NO_SECRET_DATA_PRESENT"} else REDACTED) if _account_key(k) else clean(v) for k, v in item.items()}
        if isinstance(item, list):
            return [clean(v) for v in item]
        if isinstance(item, tuple):
            values = [clean(v) for v in item]
            return type(item)(*values) if hasattr(item, "_fields") else tuple(values)
        if hasattr(item, "__dict__"):
            result = copy.copy(item)
            for k, v in vars(item).items():
                object.__setattr__(result, k, (v if isinstance(v, str) and v in {REDACTED, "NO_SECRET_DATA_PRESENT"} else REDACTED) if _account_key(k) else clean(v))
            return result
        return item
    return clean(value)


def write_text(path, text):
    """Sanitize completely before opening the persistent destination."""
    path = Path(path)
    text = scrub_text(str(text))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(text)
        stream.flush()
        os.fsync(stream.fileno())


def write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = scrub_text(json.dumps(sanitize(payload), indent=2, sort_keys=True, default=str)) + "\n"
    write_text(path, text)


def scan_artifacts(directory):
    findings = {}
    with _lock:
        tokens = tuple(_tokens)
    for path in Path(directory).rglob("*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace")
            matches = {(match.start(), match.end()) for match in _ACCOUNT_PATTERN.finditer(text)}
            for token in tokens:
                matches.update((match.start(), match.end()) for match in re.finditer(re.escape(token), text))
            count = len(matches)
            if count:
                findings[scrub_text(str(path.relative_to(directory)))] = count
    return {"passed": not findings, "occurrences": sum(findings.values()), "files": findings}


class SafeTextStream:
    """Buffer logical lines so split writes cannot bypass exact-token scrubbing."""
    def __init__(self, stream):
        self.stream = stream
        self.pending = ""
        self.lock = threading.RLock()

    def write(self, text):
        with self.lock:
            self.pending += text
            while "\n" in self.pending:
                line, self.pending = self.pending.split("\n", 1)
                self.stream.write(scrub_text(line) + "\n")
        return len(text)

    def flush(self):
        # Keep incomplete lines buffered: flush must not expose half a token.
        self.stream.flush()

    def finish(self):
        with self.lock:
            self.stream.write(scrub_text(self.pending))
            self.pending = ""
            self.stream.flush()

    @property
    def encoding(self):
        return self.stream.encoding

    def isatty(self):
        return False


def install_console_protection():
    factory = logging.getLogRecordFactory()
    if not getattr(factory, "_evidence_safe", False):
        def safe_record(*args, **kwargs):
            record = factory(*args, **kwargs)
            register_payload(record.args)
            record.msg = scrub_text(record.getMessage())
            record.args = ()
            if record.exc_info:
                import traceback
                record.exc_text = scrub_text("".join(traceback.format_exception(*record.exc_info)))
                record.exc_info = None
            if record.stack_info:
                record.stack_info = scrub_text(record.stack_info)
            return record
        safe_record._evidence_safe = True
        logging.setLogRecordFactory(safe_record)
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name)
        if not isinstance(stream, SafeTextStream):
            setattr(sys, name, SafeTextStream(stream))
    # Wire-level SDK records can precede account callbacks. Suppress them at source.
    # Application connection/callback evidence remains available and sanitized.
    for name in ("ibapi", "ib_insync"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.addHandler(logging.NullHandler())
        logger.propagate = False
        logger.setLevel(logging.CRITICAL + 1)


def finish_console_protection():
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name)
        if isinstance(stream, SafeTextStream):
            stream.finish()
        else:
            stream.flush()


@contextmanager
def capture_console(directory):
    """Capture both streams through line buffering and prewrite redaction."""
    from contextlib import redirect_stdout, redirect_stderr
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "stdout.log").open("w", encoding="utf-8") as out, (directory / "stderr.log").open("w", encoding="utf-8") as err:
        stdout, stderr = SafeTextStream(out), SafeTextStream(err)
        try:
            with redirect_stdout(stdout), redirect_stderr(stderr):
                yield
        finally:
            stdout.finish()
            stderr.finish()
            os.fsync(out.fileno())
            os.fsync(err.fileno())


atexit.register(finish_console_protection)
