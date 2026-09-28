"""Supported standalone single-symbol/batch news research command."""
from __future__ import annotations

import argparse
from contextlib import redirect_stdout
from dataclasses import fields, replace
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.news.news_intelligence_contract import NewsCandidate
from src.news.standalone_lookup import (
    LookupSettings, human_report, jsonable, lookup_news, normalize_candidates,
)

STARTUP_ALLOWANCE_SECONDS = 10.0
TERMINATION_ALLOWANCE_SECONDS = 5.0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Look up issuer news through the canonical service, independently of IBKR and market hours.")
    parser.add_argument("symbols", nargs="*", help="One ticker or a space/comma-separated list")
    parser.add_argument("--candidates-file", type=Path, help="JSON list of NewsCandidate identities, or an object with a candidates list")
    parser.add_argument("--company-name", help="Issuer name for a single-symbol query")
    parser.add_argument("--alias", action="append", default=[], help="Issuer alias for a single symbol; repeatable")
    parser.add_argument("--lookback-hours", type=float, default=24.0)
    parser.add_argument("--source-groups", nargs="+", default=["FAST_TRADING", "PREP_EXTENDED"])
    parser.add_argument("--cache-mode", choices=("use", "refresh", "only", "off"), default="use")
    parser.add_argument("--cache-file", type=Path, default=LookupSettings().cache_file)
    parser.add_argument("--prep-file", type=Path, help="Optional explicit prep artifact; default does not read operational prep")
    parser.add_argument("--budget-seconds", type=float, default=30.0)
    parser.add_argument("--request-timeout-seconds", type=float, default=5.0)
    parser.add_argument("--cleanup-seconds", type=float, default=10.0)
    parser.add_argument("--refresh-interval-seconds", type=float, default=300.0)
    parser.add_argument("--max-items", type=int, default=20)
    parser.add_argument("--format", choices=("human", "json"), default="human")
    parser.add_argument("--json-output", type=Path, help="Also write the complete machine-readable result")
    parser.add_argument("--_worker-config", type=Path, help=argparse.SUPPRESS)
    return parser


def _candidate_from_mapping(value) -> NewsCandidate:
    if isinstance(value, str):
        return NewsCandidate(value)
    if not isinstance(value, dict):
        raise ValueError("Candidate entries must be tickers or objects")
    allowed = {field.name for field in fields(NewsCandidate)}
    unknown = set(value) - allowed
    if unknown:
        raise ValueError("Unknown candidate fields (put extra issuer identity in metadata): " + ", ".join(sorted(unknown)))
    if not value.get("symbol") or not isinstance(value["symbol"], str):
        raise ValueError("Each candidate requires a string symbol")
    values = dict(value)
    aliases = values.get("aliases", ())
    if isinstance(aliases, str):
        aliases = (aliases,)
    if not isinstance(aliases, (list, tuple)) or not all(isinstance(alias, str) for alias in aliases):
        raise ValueError("Candidate aliases must be a list of strings")
    values["aliases"] = tuple(aliases)
    if not isinstance(values.get("metadata", {}), dict):
        raise ValueError("Candidate metadata must be an object")
    return NewsCandidate(**values)


def _inputs(args):
    values = []
    if args.candidates_file:
        raw = json.loads(args.candidates_file.read_text(encoding="utf-8-sig"))
        raw = raw.get("candidates") if isinstance(raw, dict) else raw
        if not isinstance(raw, list):
            raise ValueError("Candidate file must contain a list or an object with a candidates list")
        values.extend(_candidate_from_mapping(item) for item in raw)
    values.extend(value for argument in args.symbols for value in argument.split(",") if value.strip())
    candidates = normalize_candidates(values)
    if args.company_name or args.alias:
        if len(candidates) != 1:
            raise ValueError("--company-name/--alias require one symbol; use --candidates-file for batch identities")
        candidate = candidates[0]
        candidates = (replace(candidate, company_name=args.company_name or candidate.company_name,
                              aliases=tuple(dict.fromkeys((*candidate.aliases, *args.alias)))),)
    settings = LookupSettings(
        lookback_hours=args.lookback_hours, budget_seconds=args.budget_seconds,
        request_timeout_seconds=args.request_timeout_seconds, cleanup_seconds=args.cleanup_seconds,
        refresh_interval_seconds=args.refresh_interval_seconds, max_items=args.max_items,
        source_groups=tuple(part for group in args.source_groups for part in group.split(",")),
        cache_mode=args.cache_mode, cache_file=args.cache_file.resolve(),
        prep_file=args.prep_file.resolve() if args.prep_file else None,
    ).validated()
    if args.json_output:
        protected = {settings.cache_file.resolve()}
        protected.update(path.resolve() for path in (args.prep_file, args.candidates_file) if path)
        if args.json_output.resolve() in protected:
            raise ValueError("--json-output must be different from cache, prep and candidate input files")
    return candidates, settings


def _write_result(path: Path, result):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".writing")
    temporary.write_text(json.dumps(jsonable(result), indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def _source_identity():
    paths = sorted((REPO_ROOT / "src/news").glob("*.py"))
    paths.extend([Path(__file__).resolve(), REPO_ROOT / "scripts/verify_news_provider_batch.py"])
    hashes = {path.relative_to(REPO_ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths if path.is_file()}
    try:
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True, stderr=subprocess.DEVNULL).strip()
        dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=REPO_ROOT, text=True, stderr=subprocess.DEVNULL).strip())
    except (OSError, subprocess.SubprocessError):
        head, dirty = None, None
    dependencies = {}
    for package in ("requests", "feedparser"):
        try:
            dependencies[package] = version(package)
        except PackageNotFoundError:
            dependencies[package] = None
    return {"git_head": head, "git_dirty": dirty, "source_hashes": hashes, "interpreter": sys.executable, "python_version": sys.version, "dependencies": dependencies}


def _worker(config_path: Path) -> int:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    output_path = Path(config["result_file"])
    identity = _source_identity()
    try:
        candidates = [_candidate_from_mapping(item) for item in config["candidates"]]
        settings = LookupSettings(**config["settings"]).validated()
        def partial(result):
            result["runtime"] = identity
            result["worker_stage"] = "retrieval_complete_cleanup_pending"
            _write_result(output_path, result)
        # Existing canonical diagnostics stay visible without corrupting JSON stdout.
        with redirect_stdout(sys.stderr):
            result = lookup_news(candidates, settings, on_retrieval=partial)
        result["runtime"] = identity
        result["runtime"]["source_hashes_unchanged"] = identity["source_hashes"] == _source_identity()["source_hashes"]
        result["worker_stage"] = "cleanup_wait_complete"
        _write_result(output_path, result)
        return 0
    except Exception as exc:
        _write_result(output_path, {"schema_version": "news.standalone_lookup.v1", "ok": False,
                                   "error": f"{type(exc).__name__}: {exc}", "runtime": identity})
        return 1


def run_supervised(candidates, settings: LookupSettings):
    """A process deadline also bounds workers that HTTP cancellation cannot stop."""
    started = time.monotonic()
    wall_limit = STARTUP_ALLOWANCE_SECONDS + settings.budget_seconds + settings.cleanup_seconds
    timed_out = False
    with tempfile.TemporaryDirectory(prefix="canonical-news-lookup-") as directory:
        temporary_root = Path(directory).resolve()
        if temporary_root.parent != Path(tempfile.gettempdir()).resolve():
            raise RuntimeError("Unexpected temporary output location")
        config_path = temporary_root / "request.json"
        result_path = temporary_root / "result.json"
        config_path.write_text(json.dumps({"candidates": jsonable(candidates), "settings": jsonable(settings),
                                          "result_file": str(result_path)}, allow_nan=False), encoding="utf-8")
        process = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "--_worker-config", str(config_path)],
            cwd=REPO_ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
            env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"},
        )
        try:
            try:
                stdout, stderr = process.communicate(timeout=wall_limit)
            except subprocess.TimeoutExpired:
                timed_out = True
                process.terminate()
                try:
                    stdout, stderr = process.communicate(timeout=TERMINATION_ALLOWANCE_SECONDS)
                except subprocess.TimeoutExpired:
                    process.kill()
                    stdout, stderr = process.communicate(timeout=TERMINATION_ALLOWANCE_SECONDS)
        except BaseException:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=TERMINATION_ALLOWANCE_SECONDS)
            raise
        if stderr:
            print(stderr, file=sys.stderr, end="" if stderr.endswith("\n") else "\n")
        if stdout:
            print(stdout, file=sys.stderr, end="" if stdout.endswith("\n") else "\n")
        result = json.loads(result_path.read_text(encoding="utf-8")) if result_path.exists() else {
            "schema_version": "news.standalone_lookup.v1", "ok": False,
            "error": "Lookup process ended before a result was available",
        }
        result["process"] = {"exit_code": process.returncode, "exit_confirmed": process.poll() is not None,
                             "wall_limit_seconds": wall_limit, "termination_allowance_seconds": TERMINATION_ALLOWANCE_SECONDS,
                             "terminated_at_wall_limit": timed_out,
                             "wall_elapsed_seconds": time.monotonic() - started}
        if timed_out:
            result["ok"] = False
            result["error"] = "Standalone wall limit reached; the owned process was terminated"
            result.setdefault("cleanup", {}).update(cleanup_complete=False, terminated_process=True)
        result.setdefault("timing", {})["command_wall_elapsed_seconds"] = time.monotonic() - started
        return result, 0 if result.get("ok") and process.returncode == 0 and not timed_out else 1


def main(argv=None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args._worker_config:
        return _worker(args._worker_config)
    try:
        candidates, settings = _inputs(args)
    except (ValueError, TypeError, OSError) as exc:
        parser.error(str(exc))
    result, exit_code = run_supervised(candidates, settings)
    if args.json_output:
        _write_result(args.json_output.resolve(), result)
    if args.format == "json":
        print(json.dumps(jsonable(result), indent=2, allow_nan=False))
    else:
        print(human_report(result))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
