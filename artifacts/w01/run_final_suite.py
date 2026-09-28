import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

root = Path.cwd()
out = root / "artifacts/w01"
files = sorted({p for folder in ("src", "tests", "scripts", "verification_scripts") for p in (root / folder).rglob("*.py")})
manifest = {str(p.relative_to(root)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
(out / "final_source_hashes.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
record = {"started_at": datetime.now(timezone.utc).isoformat(), "interpreter": sys.executable,
          "base_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
          "source_manifest_sha256": hashlib.sha256((out / "final_source_hashes.json").read_bytes()).hexdigest(),
          "command": [sys.executable, "-m", "pytest", "-q"], "supervisor_pid": os.getpid()}
(out / "final_suite_status.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
with (out / "compile.log").open("w", encoding="utf-8") as log:
    record["compile_exit_code"] = subprocess.run([sys.executable, "-m", "compileall", "-q", "src"], stdout=log, stderr=subprocess.STDOUT, env=env).returncode
with (out / "final_full_suite.log").open("w", encoding="utf-8") as log:
    child = subprocess.Popen(record["command"], stdout=log, stderr=subprocess.STDOUT, env=env)
    record["pytest_pid"] = child.pid
    (out / "final_suite_status.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    record["exit_code"] = child.wait()
record["completed_at"] = datetime.now(timezone.utc).isoformat()
record["log_sha256"] = hashlib.sha256((out / "final_full_suite.log").read_bytes()).hexdigest()
record["source_changes_during_tests"] = [name for name, digest in manifest.items() if not (root / name).exists() or hashlib.sha256((root / name).read_bytes()).hexdigest() != digest]
(out / "final_suite_status.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
print(json.dumps(record, indent=2))
sys.exit(record["exit_code"])
