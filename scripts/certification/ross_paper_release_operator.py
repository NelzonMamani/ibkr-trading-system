"""Preflight and bounded invocation of the ordinary Core PAPER runtime."""

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from threading import Timer

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.certification.pr1090_terminal_observation_supervisor import runtime_inventory
from src.config.config_registry import CONFIG_REGISTRY
from src.ibkr.evidence_safety import write_json

_DURATION_SECONDS = 900


def run(state, evidence, calendar, calendar_sha256):
    inventory = runtime_inventory(include_controllers=True, owned_pids=(os.getpid(),))
    if not inventory["completed"] or inventory["runtimes"]:
        return "PAPER_RELEASE_EXCLUSIVE_PROCESS_CHECK_FAILED", 2

    raw = calendar.read_bytes()
    if hashlib.sha256(raw).hexdigest() != calendar_sha256:
        return "PAPER_RELEASE_CALENDAR_HASH_MISMATCH", 2
    receipt = json.loads(raw)
    if set(receipt) != {"coverage", "holidays", "half_days", "early_close"}:
        return "PAPER_RELEASE_CALENDAR_FORMAT_INVALID", 2
    if not (state / "ibkr_system.db").is_file():
        return "PAPER_RELEASE_EXISTING_STATE_DATABASE_REQUIRED", 2

    # Apply only the controlled PAPER profile and the explicit calendar receipt.
    env_keys = {name for item in CONFIG_REGISTRY.values() for name in item["env"]}
    for key in tuple(os.environ):
        if (key in env_keys or key.startswith(("PR1090_", "ROSS_", "DEV_", "FORCE_", "IBKR_"))
                or key in {"SESSION_OVERRIDE", "MARKET_SESSION_OVERRIDE", "FLATTEN_ON_STARTUP"}):
            if key not in {"ROSS_PAPER_EXPECTED_ACCOUNT", "ROSS_PAPER_EXCLUSIVE_START_ATTESTED"}:
                del os.environ[key]
    os.environ.update(
        RUN_MODE="PAPER", EXECUTION_ENABLED="true", RISK_PROFILE="MICRO",
        IBKR_HOST="127.0.0.1", IBKR_PORT="7497", IBKR_CLIENT_ID="71",
        IBKR_PAPER_HOST="127.0.0.1", IBKR_PAPER_PORT="7497",
        IBKR_READONLY_ENABLED="false", IBKR_API_WRITE_ALLOWED="true",
        IBKR_ORDER_SUBMISSION_ENABLED="true", IBKR_ORDER_TRANSLATION_ENABLED="true",
        IBKR_MARKET_DATA_TYPE="LIVE", ROSS_PAPER_RELEASE_ENABLED="1",
        STATISTICAL_INTRADAY_MOMENTUM_STRATEGY_ENABLED="false",
        MEAN_REVERSION_STRATEGY_ENABLED="false",
        FORCE_CLEAN_START="false", FLATTEN_ON_STARTUP="false",
        PERSISTENCE_SQLITE_PATH=str(state / "ibkr_system.db"),
        IBKR_ORDER_ID_STATE_PATH=str(state / "order-id.json"),
        IBKR_GUARD_PERSIST_PATH=str(state / "submission-guard.json"),
        PR1090_STOP_FILE=str(evidence / "stop"),
        PR1090_EVIDENCE_DIR=str(evidence),
        MARKET_SESSION_COVERAGE=json.dumps(receipt["coverage"], separators=(",", ":")),
        MARKET_HOLIDAYS=receipt["holidays"], MARKET_HALF_DAYS=receipt["half_days"],
        MARKET_EARLY_CLOSE_TIME=receipt["early_close"],
    )
    from src.market_data.session_pct_change import covered_opening_window

    now = datetime.now(timezone.utc)
    start = covered_opening_window(now)
    end = covered_opening_window(now + timedelta(seconds=_DURATION_SECONDS + 360))
    if (start is None or end is None or start.phase != "RTH_OPEN" or end.phase != "RTH_OPEN"
            or start.fingerprint != end.fingerprint):
        return "PAPER_RELEASE_REVIEWED_OPENING_ENVELOPE_REQUIRED", 2

    from src.main import main

    stop = Timer(_DURATION_SECONDS, lambda: (evidence / "stop").touch())
    sys.argv = ["src.main", "--mode", "PAPER", "--strategy", "ross_momentum"]
    stop.start()
    try:
        core = main()
    finally:
        stop.cancel()
        stop.join()
    shutdown = json.loads((evidence / "shutdown_evidence.json").read_text(encoding="utf-8"))
    complete = any(row.get("event") == "SHUTDOWN_COMPLETE" and row.get("completed") is True
                   for row in shutdown["events"])
    release = getattr(core, "_paper_release", None)
    if not complete or release is None:
        return "PAPER_RELEASE_SHUTDOWN_INCOMPLETE", 2
    if release.attempted:
        return "PAPER_RELEASE_ENTRY_ATTEMPT_REQUIRES_LOCAL_REVIEW", 0
    gate = release.last_gate
    # Only fixed gate tokens may leave the private log.
    if isinstance(gate, str) and re.fullmatch(
            r"(?:PAPER_RELEASE_|ROSS_|POSITION_TRUTH_|CAPITAL_|DAILY_RISK_|AUTONOMOUS_RECOVERY_)[A-Z0-9_]+", gate):
        return "PAPER_RELEASE_NO_TRADE__" + gate, 2
    return "PAPER_RELEASE_NO_TRADE", 0


def cli():
    state, evidence, calendar = map(Path, sys.argv[1:4])
    calendar_sha256 = sys.argv[4]
    reason, status = "PAPER_RELEASE_LOCAL_RUNTIME_ERROR", 2
    try:
        reason, status = run(state, evidence, calendar, calendar_sha256)
    except RuntimeError as exc:
        if re.fullmatch(r"PAPER_RELEASE_[A-Z0-9_]+", str(exc)):
            reason = str(exc)
        raise
    finally:
        write_json(evidence / "sanitized-result.json", {"status": reason, "paper_ready": False})
    return status


if __name__ == "__main__":
    raise SystemExit(cli())
