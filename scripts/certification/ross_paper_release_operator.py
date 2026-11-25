"""Offline planning and bounded invocation of the ordinary Core PAPER runtime."""

import argparse
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from threading import Timer
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.certification.pr1090_terminal_observation_supervisor import runtime_inventory
from src.config.config_registry import CONFIG_REGISTRY
from src.ibkr.evidence_safety import write_json

_DURATION_SECONDS = 900
_STATE_FILES = ("ibkr_system.db", "order-id.json", "submission-guard.json")
_CALENDAR_FIELDS = {"coverage", "holidays", "half_days", "early_close"}


def _verified_sdk():
    # Source/protobuf attestation precedes every broker import. A retained
    # witness from the isolated SDK cannot authorize the old project interpreter.
    from src.ibkr.sdk_profile import require_supported_sdk

    try:
        return require_supported_sdk()
    except RuntimeError:
        raise RuntimeError("PAPER_RELEASE_SDK_PROFILE_UNVERIFIED") from None


def require_calibrated_sdk(calibration):
    if calibration.get("sdk_distribution") != _verified_sdk():
        raise RuntimeError("PAPER_RELEASE_VOLUME_SDK_MISMATCH")


def _require_exclusive_process():
    inventory = runtime_inventory(include_controllers=True, owned_pids=(os.getpid(),))
    if not inventory["completed"] or inventory["runtimes"]:
        raise RuntimeError("PAPER_RELEASE_EXCLUSIVE_PROCESS_CHECK_FAILED")


def _load_reviewed_calendar(calendar, calendar_sha256):
    if calendar is None or not calendar.is_file():
        raise RuntimeError("PAPER_RELEASE_REVIEWED_CALENDAR_REQUIRED")
    try:
        raw = calendar.read_bytes()
    except OSError:
        raise RuntimeError("PAPER_RELEASE_REVIEWED_CALENDAR_REQUIRED") from None
    if hashlib.sha256(raw).hexdigest() != calendar_sha256:
        raise RuntimeError("PAPER_RELEASE_CALENDAR_HASH_MISMATCH")
    try:
        receipt = json.loads(raw)
    except ValueError:
        raise RuntimeError("PAPER_RELEASE_CALENDAR_FORMAT_INVALID") from None
    if type(receipt) is not dict or set(receipt) != _CALENDAR_FIELDS:
        raise RuntimeError("PAPER_RELEASE_CALENDAR_FORMAT_INVALID")
    return receipt


def _require_state_files(state):
    if state is None or not all((state / name).is_file() for name in _STATE_FILES):
        raise RuntimeError("PAPER_RELEASE_EXISTING_STATE_FILES_REQUIRED")


def _opening_envelope(start_time, read_window):
    start = read_window(start_time)
    end = read_window(start_time + timedelta(seconds=_DURATION_SECONDS + 360))
    if (start is None or end is None or start.phase != "RTH_OPEN" or end.phase != "RTH_OPEN"
            or start.fingerprint != end.fingerprint):
        raise RuntimeError("PAPER_RELEASE_REVIEWED_OPENING_ENVELOPE_REQUIRED")
    return start


def _calendar_environment(receipt):
    return dict(
        MARKET_SESSION_COVERAGE=json.dumps(receipt["coverage"], separators=(",", ":")),
        MARKET_HOLIDAYS=receipt["holidays"], MARKET_HALF_DAYS=receipt["half_days"],
        MARKET_EARLY_CLOSE_TIME=receipt["early_close"],
    )


def _plan_opening_envelope(stamp, receipt):
    # The calendar owner consumes environment settings. Isolate the planned
    # date from the current process and keep the reviewed owner byte-identical.
    program = """
import contextlib, io, json, os, sys
from datetime import datetime

def offline(event, args):
    if event.startswith('socket.') or event in {'subprocess.Popen', 'os.system',
            'os.exec', 'os.posix_spawn', 'os.mkdir', 'os.remove', 'os.rename'}:
        raise PermissionError('offline calendar planner')
    if event == 'open' and args[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
        raise PermissionError('offline calendar planner')

sys.addaudithook(offline)
sys.path.insert(0, sys.argv[1])
with contextlib.redirect_stdout(io.StringIO()):
    from scripts.certification.ross_paper_release_operator import _opening_envelope
    from src.market_data.session_pct_change import covered_opening_window
    try:
        window = _opening_envelope(datetime.fromisoformat(sys.argv[2]), covered_opening_window)
    except RuntimeError:
        window = None
print(json.dumps({'close': window.current_close.isoformat(), 'date': window.target_session} if window else None))
"""
    env = {key: value for key, value in os.environ.items() if key.upper() in {"SYSTEMROOT", "WINDIR"}}
    env.update(_calendar_environment(receipt))
    try:
        result = subprocess.run([sys.executable, "-I", "-B", "-c", program, str(ROOT), stamp.isoformat()],
                                capture_output=True, text=True, env=env, timeout=20, check=True)
        payload = json.loads(result.stdout)
        if payload is not None:
            return SimpleNamespace(current_close=datetime.fromisoformat(payload["close"]), target_session=payload["date"])
    except (OSError, TypeError, ValueError, KeyError, subprocess.SubprocessError):
        raise RuntimeError("PAPER_RELEASE_CALENDAR_PLAN_UNAVAILABLE") from None
    raise RuntimeError("PAPER_RELEASE_REVIEWED_OPENING_ENVELOPE_REQUIRED")


def _planned_start(value, now):
    if value is None:
        raise RuntimeError("PAPER_RELEASE_PLANNED_START_REQUIRED")
    try:
        stamp = datetime.fromisoformat(value)
        if stamp.utcoffset() is not None and stamp >= now:
            return stamp
    except ValueError:
        pass
    raise RuntimeError("PAPER_RELEASE_PLANNED_START_INVALID")


def _check_only(state, calendar, calendar_sha256, witness, planned_start):
    """Collect all local checks without enabling PAPER or writing any files."""
    from src.core.capital_management_authority import PaperEntryFeeCeiling
    from src.ibkr.volume_calibration import load_paper_volume_calibration

    checks = {}

    def check(name, action, passed):
        try:
            result = action()
        except (OSError, RuntimeError, TypeError, ValueError, OverflowError) as exc:
            reason = str(exc)
            checks[name] = (reason if isinstance(exc, RuntimeError)
                            and re.fullmatch(r"PAPER_RELEASE_[A-Z0-9_]+", reason)
                            else "PAPER_RELEASE_LOCAL_INPUT_INVALID")
            return None
        checks[name] = passed
        return result

    now = datetime.now(timezone.utc)
    account = os.environ.get("ROSS_PAPER_EXPECTED_ACCOUNT", "")
    account_valid = re.fullmatch(r"DUK?[0-9]+", account) is not None
    checks["account_format"] = ("PRESENT" if account_valid else "PAPER_RELEASE_EXPECTED_ACCOUNT_REQUIRED")
    check("process_inventory", _require_exclusive_process, "CLEAR_AT_CHECK_TIME")
    check("state_files", lambda: _require_state_files(state), "PRESENT")
    sdk = check("sdk", _verified_sdk, "VERIFIED")
    receipt = check("calendar", lambda: _load_reviewed_calendar(calendar, calendar_sha256),
                    "HASH_AND_FORMAT_VERIFIED")

    def read_window():
        stamp = _planned_start(planned_start, now)
        if receipt is None:
            raise RuntimeError("PAPER_RELEASE_REVIEWED_CALENDAR_REQUIRED")
        return _plan_opening_envelope(stamp, receipt)

    window = check("opening_envelope", read_window, "VERIFIED_FOR_PLAN")

    fee_path = state / "entry-fee-ceiling.json" if state is not None else None

    def read_fee():
        if fee_path is not None and fee_path.is_file() and not account_valid:
            raise RuntimeError("PAPER_RELEASE_EXPECTED_ACCOUNT_REQUIRED")
        fee = PaperEntryFeeCeiling.load(fee_path, expected_account=account, now=now)
        if window is not None:
            fee.require_rth_close(window.current_close)

    check("entry_fee", read_fee, "VALID_THROUGH_PLANNED_CLOSE" if window is not None else "VALID_AT_CHECK_TIME")

    def read_volume():
        witness_path = witness if witness is not None else state / "volume-witness.json" if state is not None else None
        if witness_path is None:
            raise RuntimeError("PAPER_RELEASE_VOLUME_CALIBRATION_REQUIRED")
        calibration = load_paper_volume_calibration(witness_path, now=now)
        if sdk is None:
            raise RuntimeError("PAPER_RELEASE_SDK_PROFILE_UNVERIFIED")
        if calibration["sdk_distribution"] != sdk:
            raise RuntimeError("PAPER_RELEASE_VOLUME_SDK_MISMATCH")
        if window is not None and calibration["trading_date"].isoformat() != window.target_session:
            raise RuntimeError("PAPER_RELEASE_VOLUME_PLANNED_DATE_MISMATCH")

    check("current_volume_witness", read_volume, "VERIFIED_FOR_PLAN" if window is not None else "VERIFIED_AT_CHECK_TIME")
    blockers = [name for name, result in checks.items() if result.startswith("PAPER_RELEASE_")]
    return {
        "status": "PAPER_RELEASE_OFFLINE_PREFLIGHT_BLOCKED" if blockers else "PAPER_RELEASE_OFFLINE_PREFLIGHT_COMPLETE",
        "checks": checks,
        "blocked_checks": blockers,
        "native_acceptance": "PENDING",
        "paper_ready": False,
    }


def run(state, evidence, calendar, calendar_sha256, witness=None):
    try:
        _require_exclusive_process()
        receipt = _load_reviewed_calendar(calendar, calendar_sha256)
        _require_state_files(state)
    except RuntimeError as exc:
        return str(exc), 2
    witness = witness if witness is not None else state / "volume-witness.json"
    if not witness.is_file():
        return "PAPER_RELEASE_VOLUME_CALIBRATION_REQUIRED", 2
    fee_ceiling = state / "entry-fee-ceiling.json"
    if not fee_ceiling.is_file():
        return "PAPER_RELEASE_ENTRY_COST_AUTHORITY_REQUIRED", 2

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
        IBKR_MARKET_DATA_TYPE="LIVE", IBKR_FALLBACK_ENABLED="false",
        SCANNER_DATA_SOURCE="IBKR", ROSS_PAPER_RELEASE_ENABLED="1",
        ROSS_TWS_VOLUME_COMPARATOR_PATH=str(witness),
        ROSS_PAPER_ENTRY_FEE_CEILING_PATH=str(fee_ceiling),
        DECISION_TRACE_PATH=str(evidence / "decision-trace.jsonl"),
        TRACE_LOG_DIR=str(evidence / "trace"),
        STATISTICAL_INTRADAY_MOMENTUM_STRATEGY_ENABLED="false",
        MEAN_REVERSION_STRATEGY_ENABLED="false",
        FORCE_CLEAN_START="false", FLATTEN_ON_STARTUP="false",
        FORCE_EXECUTION_ON_TRADE_READY="false", FORCE_RISK_APPROVAL_FOR_TRADE_READY="false",
        PERSISTENCE_SQLITE_PATH=str(state / "ibkr_system.db"),
        IBKR_ORDER_ID_STATE_PATH=str(state / "order-id.json"),
        IBKR_GUARD_PERSIST_PATH=str(state / "submission-guard.json"),
        PR1090_STOP_FILE=str(evidence / "stop"),
        PR1090_EVIDENCE_DIR=str(evidence),
        **_calendar_environment(receipt),
    )
    from src.core.capital_management_authority import PaperEntryFeeCeiling
    from src.ibkr.volume_calibration import load_paper_volume_calibration
    from src.market_data.session_pct_change import covered_opening_window

    now = datetime.now(timezone.utc)
    calibration = load_paper_volume_calibration(witness, now=now)
    require_calibrated_sdk(calibration)
    os.environ["ROSS_TWS_VOLUME_CALIBRATION_SHA256"] = calibration["calibration_id"]
    fee_terms = PaperEntryFeeCeiling.load(
        fee_ceiling, expected_account=os.environ.get("ROSS_PAPER_EXPECTED_ACCOUNT"), now=now)
    try:
        start = _opening_envelope(now, covered_opening_window)
    except RuntimeError as exc:
        return str(exc), 2
    fee_terms.require_rth_close(start.current_close)

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
    if release is None:
        return "PAPER_RELEASE_SHUTDOWN_INCOMPLETE", 2
    if core.execution_engine._native_quarantined or (
            core.execution_engine._native_orders and not release.attempted):
        return "PAPER_RELEASE_NATIVE_STATE_REQUIRES_LOCAL_REVIEW", 2
    if not complete:
        return "PAPER_RELEASE_SHUTDOWN_INCOMPLETE", 2
    if release.attempted:
        return "PAPER_RELEASE_ENTRY_ATTEMPT_REQUIRES_LOCAL_REVIEW", 0
    gate = release.last_gate
    # Only fixed gate tokens may leave the private log.
    if isinstance(gate, str) and re.fullmatch(
            r"(?:INSUFFICIENT_CAPITAL|(?:PAPER_RELEASE_|PAPER_CAPITAL_|ROSS_|POSITION_TRUTH_|"
            r"CAPITAL_|DAILY_RISK_|AUTONOMOUS_RECOVERY_)[A-Z0-9_]+)", gate):
        return "PAPER_RELEASE_NO_TRADE__" + gate, 2
    return "PAPER_RELEASE_NO_TRADE", 0


def cli():
    if len(sys.argv) > 1 and sys.argv[1] == "--check-only":
        parser = argparse.ArgumentParser(description="Check private Ross PAPER inputs offline.")
        parser.add_argument("--state", type=Path)
        parser.add_argument("--calendar", type=Path)
        parser.add_argument("--calendar-sha256")
        parser.add_argument("--witness", type=Path)
        parser.add_argument("--planned-start")
        args = parser.parse_args(sys.argv[2:])
        try:
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                report = _check_only(args.state, args.calendar, args.calendar_sha256, args.witness, args.planned_start)
        except Exception:
            print(json.dumps({"status": "PAPER_RELEASE_OFFLINE_PREFLIGHT_UNAVAILABLE",
                              "native_acceptance": "PENDING", "paper_ready": False}, separators=(",", ":")))
            return 2
        print(json.dumps(report, separators=(",", ":")))
        return 2 if report["blocked_checks"] else 0

    state, evidence, calendar = map(Path, sys.argv[1:4])
    calendar_sha256 = sys.argv[4]
    witness = Path(sys.argv[5]) if len(sys.argv) == 6 else None
    reason, status = "PAPER_RELEASE_LOCAL_RUNTIME_ERROR", 2
    try:
        reason, status = run(state, evidence, calendar, calendar_sha256, witness)
    except RuntimeError as exc:
        if re.fullmatch(r"PAPER_RELEASE_[A-Z0-9_]+", str(exc)):
            reason = str(exc)
        raise
    finally:
        write_json(evidence / "sanitized-result.json", {"status": reason, "paper_ready": False})
    return status


if __name__ == "__main__":
    raise SystemExit(cli())
