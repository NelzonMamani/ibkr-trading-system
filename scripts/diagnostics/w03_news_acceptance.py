"""One-shot W03 diagnostic wrapper; delegates all retrieval to the supported helper."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "output/w03/live"
EVIDENCE = ROOT / "artifacts/w03"

def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, default=str) + "\n", encoding="utf-8")

def manifest():
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for folder in ("src", "tests", "scripts", "verification_scripts")
            for p in sorted((ROOT/folder).rglob("*.py"))}

def worker():
    from scripts.verify_news_discovery import _candidate_from_mapping, _source_identity
    from src.news.standalone_lookup import LookupSettings, lookup_news, human_report
    from src.news import news_fetcher
    config = json.loads((OUT / "request.json").read_text(encoding="utf-8"))
    session = json.loads((EVIDENCE / "live_session_start.json").read_text(encoding="utf-8"))
    deadline = datetime.fromisoformat(session["started_at"]).timestamp() + 600
    if time.time() + 100 > deadline:
        raise RuntimeError("Insufficient time left in the single diagnostic session")
    source_before = manifest()
    write(EVIDENCE / "live_source_hashes.json", source_before)
    identity = _source_identity()
    captures = []
    lock = threading.Lock()
    original_get = news_fetcher.requests.get
    def observed_get(url, *args, **kwargs):
        if time.time() >= deadline:
            raise RuntimeError("Diagnostic wall limit reached before request")
        started = time.monotonic()
        row = {"url": url, "started_at": datetime.now(timezone.utc).isoformat(),
               "timeout_seconds": kwargs.get("timeout")}
        try:
            response = original_get(url, *args, **kwargs)
            # requests has already received these bytes; no parse/hash work on the fetch path.
            row.update(status_code=response.status_code, content_type=response.headers.get("Content-Type"),
                       body=response.content)
            return response
        except Exception as exc:
            row["error"] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            row["request_elapsed_seconds"] = time.monotonic() - started
            with lock:
                captures.append(row)
    news_fetcher.requests.get = observed_get
    settings = LookupSettings(**config["settings"]).validated()
    diagnostic_root = (ROOT / "output/w03").resolve()
    for path in (settings.cache_file, settings.prep_file):
        if path is not None and not path.resolve().is_relative_to(diagnostic_root):
            raise ValueError("Acceptance cache/prep paths must stay under output/w03")
    candidates = [_candidate_from_mapping(value) for value in config["candidates"]]
    def partial(result):
        result["runtime"] = identity
        write(EVIDENCE / "live_batch_partial.json", result)
    try:
        result = lookup_news(candidates, settings, on_retrieval=partial)
    finally:
        news_fetcher.requests.get = original_get
    result["runtime"] = identity
    result["runtime"]["source_hashes_unchanged"] = source_before == manifest()
    result["diagnostic_capture"] = {"kind": "live_provider_batch", "body_hashing_after_cleanup_wait": True,
                                    "capture_complete_at_snapshot": result["cleanup"].get("cleanup_complete") is True,
                                    "unfinished_request_count": result["cleanup"].get("unfinished_count"),
                                    "broker_modules_loaded": sorted(name for name in sys.modules if name == "ibapi" or name.startswith("ibapi.") or name == "ib_insync" or name.startswith("ib_insync.")),
                                    "operational_paths_used": False}
    write(EVIDENCE / "live_batch.json", result)
    (EVIDENCE / "live_batch.txt").write_text(human_report(result) + "\n", encoding="utf-8")
    index = []
    with lock:
        completed_captures = list(captures)
    for i, captured in enumerate(completed_captures):
        row = dict(captured)
        body = row.pop("body", None)
        if body is not None:
            name = f"source-{i:02d}.xml"
            (OUT / name).write_bytes(body)
            row.update(body_file=str((OUT/name).relative_to(ROOT)), body_sha256=hashlib.sha256(body).hexdigest(),
                       body_bytes=len(body))
        index.append(row)
    write(EVIDENCE / "live_capture_index.json", index)
    return 0

def main():
    if "--worker" in sys.argv:
        return worker()
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    record = {"started_at": datetime.now(timezone.utc).isoformat(), "command": [sys.executable, __file__, "--worker"],
              "wall_limit_seconds": 90, "interpreter": sys.executable}
    with (EVIDENCE / "live_worker.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen(record["command"], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                   env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
        record["worker_pid"] = process.pid
        write(EVIDENCE / "live_process.json", record)
        try:
            process.wait(timeout=90)
            record["terminated_at_wall_limit"] = False
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
            record["terminated_at_wall_limit"] = True
    record.update(exit_code=process.returncode, exit_confirmed=process.poll() is not None,
                  elapsed_seconds=time.monotonic()-started, completed_at=datetime.now(timezone.utc).isoformat())
    write(EVIDENCE / "live_process.json", record)
    print(json.dumps(record, indent=2))
    return process.returncode

if __name__ == "__main__":
    raise SystemExit(main())
