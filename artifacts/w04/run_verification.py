import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

root = Path.cwd()
mode = sys.argv[1] if len(sys.argv) > 1 else "affected"
if mode not in {"affected", "full"}:
    raise SystemExit("Expected affected or full")
out = root / "artifacts/w04"
files = sorted({p for folder in ("src", "tests", "scripts", "verification_scripts") for p in (root / folder).rglob("*.py")})
manifest = {str(p.relative_to(root)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
(out / f"{mode}_source_hashes.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
protected = ["data/news/news_cache.json", "data/prep/premarket_prep.json"]
def protected_hashes():
    return {name: hashlib.sha256((root/name).read_bytes()).hexdigest() if (root/name).exists() else None for name in protected}
record = {"operational_files_before": protected_hashes(),"started_at": datetime.now(timezone.utc).isoformat(), "interpreter": sys.executable,
          "base_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
          "source_manifest_sha256": hashlib.sha256((out / f"{mode}_source_hashes.json").read_bytes()).hexdigest(),
          "command": [sys.executable, "-m", "pytest", "-p", "scripts.diagnostics.w02_offline_guard", f"--w02-network-audit=artifacts/w04/{mode}_network_audit.json", "-q"], "supervisor_pid": os.getpid()}
if mode == "affected":
    record["command"].extend(json.loads((out / "targeted_modules.json").read_text()))
(out / f"{mode}_status.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
with (out / "compile.log").open("w", encoding="utf-8") as log:
    record["compile_exit_code"] = subprocess.run([sys.executable, "-m", "compileall", "-q", "src"], stdout=log, stderr=subprocess.STDOUT, env=env).returncode
with (out / f"{mode}.log").open("w", encoding="utf-8") as log:
    child = subprocess.Popen(record["command"], stdout=log, stderr=subprocess.STDOUT, env=env)
    record["pytest_pid"] = child.pid
    (out / f"{mode}_status.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    record["exit_code"] = child.wait()
record["operational_files_after"] = protected_hashes()
record["operational_files_unchanged"] = record["operational_files_after"] == record["operational_files_before"]
record["network_audit"] = json.loads((out / f"{mode}_network_audit.json").read_text())
record["completed_at"] = datetime.now(timezone.utc).isoformat()
record["log_sha256"] = hashlib.sha256((out / f"{mode}.log").read_bytes()).hexdigest()
record["source_changes_during_tests"] = [name for name, digest in manifest.items() if not (root / name).exists() or hashlib.sha256((root / name).read_bytes()).hexdigest() != digest]
(out / f"{mode}_status.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
print(json.dumps(record, indent=2))
sys.exit(record["exit_code"])
