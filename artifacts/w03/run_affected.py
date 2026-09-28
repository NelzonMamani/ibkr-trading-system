import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone
out=Path("artifacts/w03")
modules=json.loads((out/"targeted_modules.json").read_text(encoding="utf-8"))
files=sorted({p for d in ("src","tests","scripts","verification_scripts") for p in Path(d).rglob("*.py")})
manifest={p.as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
(out/"affected_source_hashes.json").write_text(json.dumps(manifest,indent=2,sort_keys=True),encoding="utf-8")
command=[sys.executable,"-m","pytest","-p","scripts.diagnostics.w02_offline_guard","--w02-network-audit=artifacts/w03/affected_network_audit.json","-q",*modules]
record={"started_at":datetime.now(timezone.utc).isoformat(),"command":command,"interpreter":sys.executable}
with (out/"affected.log").open("w",encoding="utf-8") as log:
    record["exit_code"]=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,env={**os.environ,"PYTHONUTF8":"1","PYTHONIOENCODING":"utf-8"}).returncode
record["completed_at"]=datetime.now(timezone.utc).isoformat()
record["source_changes"]=[p for p,h in manifest.items() if not Path(p).exists() or hashlib.sha256(Path(p).read_bytes()).hexdigest()!=h]
record["log_sha256"]=hashlib.sha256((out/"affected.log").read_bytes()).hexdigest()
(out/"affected_status.json").write_text(json.dumps(record,indent=2),encoding="utf-8")
print(json.dumps(record,indent=2))
sys.exit(record["exit_code"])
