from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from src.metadata.m0_canon_helpers import get_repo_root, write_json
from src.metadata.m10_data_provenance_ledger import (
    DATA_SOURCE_REGISTRY,
    MODE_TRUTH_MATRIX,
    DataProvenanceLedger,
)

EPOCH = "M10_DATA_PROVENANCE_LEDGER"
EVIDENCE_DIR_REL = Path("TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/M10_DATA_PROVENANCE_LEDGER")
STATE_FILE_REL = Path("TRADING_OS_MASTER_CATALOGUE/SYSTEM_STATE_CERTIFIED.md")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _utc_now_z() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _stable(payload: dict) -> dict:
    return {k: v for k, v in payload.items() if k != "generated_at_utc"}


def _verify_once(repo_root: Path) -> dict:
    violations: list[dict[str, str]] = []
    if set(MODE_TRUTH_MATRIX) != {"SIM", "PAPER", "READ_ONLY", "LIVE"}:
        violations.append(
            {
                "check": "MODE_TRUTH_MATRIX_COVERS_ALL_MODES",
                "expected": "SIM,PAPER,READ_ONLY,LIVE",
                "actual": ",".join(sorted(MODE_TRUTH_MATRIX)),
            }
        )

    source_ids = {item.get("source_id") for item in DATA_SOURCE_REGISTRY if isinstance(item, dict)}
    required_sources = {"IBKR_SNAPSHOT", "IBKR_STREAM", "HIST_BARS", "CACHE_DB", "FALLBACK_PROVIDER"}
    if not required_sources.issubset(source_ids):
        violations.append(
            {
                "check": "DATA_SOURCE_REGISTRY_REQUIRED_SOURCES",
                "expected": ",".join(sorted(required_sources)),
                "actual": ",".join(sorted(str(item) for item in source_ids)),
            }
        )

    evidence_dir = repo_root / EVIDENCE_DIR_REL
    sample_ledger_path = evidence_dir / "sample_data_provenance_ledger.jsonl"
    ledger = DataProvenanceLedger(sample_ledger_path)
    sample_ledger_path.write_text("", encoding="utf-8")

    input_event = ledger.append_event(
        {
            "event_id": "M10-SAMPLE-INPUT",
            "symbol": "AAPL",
            "data_type": "PRICE_BAR",
            "timeframe_scope": "INTRADAY",
            "timeframe_resolution": "1M",
            "source_id": "IBKR_STREAM",
            "mode": "SIM",
            "session_state": "PRE",
            "freshness_class": "REALTIME",
            "confidence_level": "HIGH",
            "known_limitations": "",
            "checksum_or_fingerprint": "",
            "linkage": {"signal_ids": ["SIG-AAPL-OPEN"], "decision_ids": [], "order_ids": [], "parent_event_ids": []},
        }
    )
    ledger.append_event(
        {
            "event_id": "M10-SAMPLE-DERIVED",
            "symbol": "AAPL",
            "data_type": "INDICATOR",
            "timeframe_scope": "MULTI_TIMEFRAME",
            "timeframe_resolution": "5M",
            "source_id": "CACHE_DB",
            "mode": "SIM",
            "session_state": "PRE",
            "freshness_class": "DELAYED",
            "confidence_level": "MEDIUM",
            "known_limitations": "historical_backfill_used",
            "checksum_or_fingerprint": "",
            "linkage": {
                "signal_ids": ["SIG-AAPL-OPEN"],
                "decision_ids": ["DEC-AAPL-OPEN"],
                "order_ids": ["ORD-AAPL-OPEN"],
                "parent_event_ids": [input_event["event_id"]],
            },
        }
    )
    ledger.append_hydration_event(
        symbol="AAPL",
        mode="SIM",
        session_state="PRE",
        hydration_state="DATA_HYDRATION_READY",
        datasets_requested=["1D", "5M", "NEWS_BOOLEAN"],
        datasets_succeeded=["1D", "5M", "NEWS_BOOLEAN"],
        datasets_failed=[],
        decision_ids=["DEC-AAPL-OPEN"],
    )

    result = ledger.verify()
    if not result.valid:
        violations.append(
            {
                "check": "LEDGER_HASH_CHAIN_VALID",
                "expected": "valid",
                "actual": ";".join(result.violations),
            }
        )

    if len(ledger.query(decision_id="DEC-AAPL-OPEN")) < 2:
        violations.append(
            {
                "check": "DECISION_LINKAGE_PRESENT",
                "expected": ">=2_events_for_DEC-AAPL-OPEN",
                "actual": str(len(ledger.query(decision_id="DEC-AAPL-OPEN"))),
            }
        )

    return {
        "epoch": EPOCH,
        "valid": not violations,
        "violations": sorted(violations, key=lambda item: (item["check"], item["actual"], item["expected"])),
        "sample_ledger": str(sample_ledger_path.relative_to(repo_root)),
        "generated_at_utc": _utc_now_iso(),
    }


def verify_m10_data_provenance_ledger(repo_root: Path | None = None) -> dict:
    repo_root = get_repo_root(repo_root)
    first = _verify_once(repo_root)
    second = _verify_once(repo_root)
    if _stable(first) != _stable(second):
        merged = dict(first)
        violations = list(merged.get("violations", []))
        violations.append(
            {
                "check": "M10_VERIFIER_DETERMINISTIC_OUTPUT",
                "expected": "stable_result",
                "actual": "non_deterministic_output_detected",
            }
        )
        merged["violations"] = sorted(violations, key=lambda item: (item["check"], item["actual"], item["expected"]))
        merged["valid"] = False
        first = merged
    return first


def build_evidence_index(files: list[Path]) -> dict:
    entries = [{"file": path.name, "bytes": path.stat().st_size} for path in sorted(files, key=lambda p: p.name)]
    return {"epoch": EPOCH, "files": entries, "generated_at_utc": _utc_now_z()}


def write_outputs(result: dict, output_json: Path, output_md: Path, evidence_index_json: Path) -> None:
    write_json(output_json, result)
    lines = [
        "# M10 Data Provenance Ledger Summary",
        "",
        f"- Valid: {result.get('valid')}",
        f"- Sample ledger: {result.get('sample_ledger')}",
        f"- Violations: {len(result.get('violations', []))}",
    ]
    output_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    write_json(evidence_index_json, build_evidence_index([output_json, output_md]))
