"""
verification_scripts/verify_system_reality_v2.py
System Reality Check v2 (Root/DB/Runner/Broker Adapter)

One-shot: identifies project root, correct DB path, StrategyRunner location,
and why execution is disabled.

No trades. No writes. Safe to run anytime.
"""

import os
import sys
import json
import pkgutil
import inspect
import importlib
from datetime import datetime, timezone

REPORT = {
    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    "paths": {},
    "runtime": {},
    "db": {},
    "strategy_runner_discovery": {},
    "broker_adapter_discovery": {},
    "verdict": {},
}

# ----------------------------
# PATHS / ROOT
# ----------------------------
here = os.path.abspath(__file__)
repo_root_guess = os.path.abspath(os.path.join(os.path.dirname(here), ".."))

REPORT["paths"] = {
    "script_path": here,
    "cwd": os.getcwd(),
    "repo_root_guess": repo_root_guess,
    "python_exe": sys.executable,
    "sys_path_head": sys.path[:8],
}

# Ensure repo root is on sys.path (safe; doesn’t mutate files)
if repo_root_guess not in sys.path:
    sys.path.insert(0, repo_root_guess)

# ----------------------------
# RUNTIME CONFIG (authoritative)
# ----------------------------
def safe_get_config():
    out = {}
    try:
        from src.config.runtime_config import get_config
        keys = [
            "RUN_MODE",
            "EXECUTION_ENABLED",
            "IBKR_READONLY_ENABLED",
            "IBKR_API_WRITE_ALLOWED",
            "IBKR_HOST",
            "IBKR_PORT",
            "IBKR_CLIENT_ID",
            "IBKR_MARKET_DATA_TYPE",
            "SQLITE_PATH",
            "SCHEMA_VERSION",
        ]
        for k in keys:
            try:
                out[k] = get_config(k)
            except Exception as e:
                out[k] = f"ERROR({e})"
    except Exception as e:
        out["error"] = str(e)
    return out

REPORT["runtime"] = safe_get_config()

# ----------------------------
# DB PATHS (config vs relative)
# ----------------------------
def file_info(path):
    try:
        return {
            "path": path,
            "abs": os.path.abspath(path),
            "exists": os.path.exists(path),
            "size_bytes": os.path.getsize(path) if os.path.exists(path) else None,
        }
    except Exception as e:
        return {"path": path, "error": str(e)}

sqlite_cfg = REPORT["runtime"].get("SQLITE_PATH")
db_candidates = []

if sqlite_cfg and isinstance(sqlite_cfg, str) and sqlite_cfg.strip():
    db_candidates.append(sqlite_cfg)

# common relative candidate
db_candidates.append(os.path.join("data", "ibkr_system.db"))
# absolute candidate under guessed repo root
db_candidates.append(os.path.join(repo_root_guess, "data", "ibkr_system.db"))

REPORT["db"]["candidates"] = [file_info(p) for p in db_candidates]

# ----------------------------
# StrategyRunner discovery (find actual module)
# ----------------------------
def discover_strategy_runner():
    results = {
        "found": False,
        "candidates": [],
        "errors": [],
    }

    try:
        import src
        for mod in pkgutil.walk_packages(src.__path__, "src."):
            name = mod.name
            # keep it cheap: only modules likely to contain runner classes
            if ("runner" not in name.lower()) and ("orchestr" not in name.lower()):
                continue
            try:
                m = importlib.import_module(name)
            except Exception as e:
                results["errors"].append({"module": name, "error": str(e)})
                continue

            for attr_name in dir(m):
                if attr_name.lower() in ("strategyrunner", "strategy_runner"):
                    obj = getattr(m, attr_name, None)
                    if obj and inspect.isclass(obj):
                        results["candidates"].append({
                            "module": name,
                            "class": attr_name,
                            "doc": (inspect.getdoc(obj) or "")[:200],
                        })
                        results["found"] = True
    except Exception as e:
        results["errors"].append({"fatal": str(e)})

    return results

REPORT["strategy_runner_discovery"] = discover_strategy_runner()

# ----------------------------
# Broker adapter discovery (IBKR paper/live)
# ----------------------------
def discover_broker_adapters():
    results = {"candidates": [], "errors": []}
    try:
        import src
        for mod in pkgutil.walk_packages(src.__path__, "src."):
            name = mod.name.lower()
            if "broker" not in name and "ibkr" not in name and "adapter" not in name:
                continue
            try:
                m = importlib.import_module(mod.name)
            except Exception as e:
                results["errors"].append({"module": mod.name, "error": str(e)})
                continue

            for attr_name in dir(m):
                if "broker" in attr_name.lower() or "adapter" in attr_name.lower():
                    obj = getattr(m, attr_name, None)
                    if obj and inspect.isclass(obj):
                        results["candidates"].append({
                            "module": mod.name,
                            "class": attr_name,
                            "doc": (inspect.getdoc(obj) or "")[:200],
                        })
    except Exception as e:
        results["errors"].append({"fatal": str(e)})
    return results

REPORT["broker_adapter_discovery"] = discover_broker_adapters()

# ----------------------------
# Verdict
# ----------------------------
exec_enabled = REPORT["runtime"].get("EXECUTION_ENABLED") is True
mode = REPORT["runtime"].get("RUN_MODE")

db_any_exists = any(c.get("exists") for c in REPORT["db"]["candidates"] if isinstance(c, dict))
runner_found = REPORT["strategy_runner_discovery"].get("found") is True
has_broker_candidates = len(REPORT["broker_adapter_discovery"].get("candidates", [])) > 0

REPORT["verdict"] = {
    "run_mode": mode,
    "execution_enabled": exec_enabled,
    "db_found_anywhere": db_any_exists,
    "strategy_runner_found_somewhere": runner_found,
    "broker_adapter_classes_found": has_broker_candidates,
    "status": (
        "READY_TO_TEST_PAPER_TRADING"
        if (mode == "PAPER" and exec_enabled and db_any_exists and runner_found and has_broker_candidates)
        else "NOT_READY"
    )
}

print("\n=== SYSTEM REALITY REPORT v2 ===")
print(json.dumps(REPORT, indent=2))
