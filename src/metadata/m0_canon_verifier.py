from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from src.metadata.m0_canon_helpers import (
    CANONICAL_PREFIXES,
    build_canonical_registry,
    get_repo_root,
    parse_naming_prefixes,
    sha256_for_file,
    validate_canonical_names,
    verify_identity_uniqueness,
    write_json,
)

GOVERNANCE_FILES = [
    "01_ARCHITECTURAL_INTENT.md",
    "02_CANONICAL_SOURCES_OF_TRUTH.md",
    "03_CANONICAL_NAMING_RULES.md",
    "04_CONFLICT_RESOLUTION_AND_PRECEDENCE.md",
    "05_ENFORCED_INVARIANTS.md",
    "06_EXPECTED_ARTIFACTS.md",
    "07_VERIFICATION_COMMANDS.md",
    "08_AUDIT_REPORT.md",
]

CONFLICT_RULES = [
    "Higher canonical source overrides lower.",
    "Strategy policy overrides foundation defaults.",
    "Safety epochs (E15/E16) override strategies.",
]


def load_governance_text(repo_root: Path) -> dict:
    governance_dir = (
        repo_root
        / "TRADING_OS_MASTER_CATALOGUE"
        / "02_METADATA_EPOCHS"
        / "00_M0_CANON_AND_SOURCES_OF_TRUTH"
        / "governance"
    )
    texts: dict[str, str] = {}
    for name in GOVERNANCE_FILES:
        path = governance_dir / name
        if not path.exists():
            raise FileNotFoundError(f"Missing governance file: {path}")
        texts[name] = path.read_text(encoding="utf-8")
    return texts


def governance_syntax_report(governance_texts: dict[str, str]) -> dict:
    status = {}
    for name, text in governance_texts.items():
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        status[name] = {"ends_with_end": bool(lines and lines[-1] == "END")}
    return status


def canonical_paths_report(repo_root: Path, registry: dict) -> dict:
    missing: list[str] = []
    for source in registry.get("sources", []):
        for rel_path in source.get("paths", []):
            path = repo_root / rel_path
            if not path.exists():
                missing.append(rel_path)
    return {"missing": sorted(set(missing)), "all_exist": not missing}


def conflict_rule_report(conflict_text: str) -> dict:
    missing = [rule for rule in CONFLICT_RULES if rule not in conflict_text]
    return {"missing_rules": missing, "rules_present": not missing}


def naming_rules_report(naming_text: str, sample_names: list[str] | None = None) -> dict:
    parsed_prefixes = parse_naming_prefixes(naming_text)
    prefix_match = sorted(set(parsed_prefixes)) == sorted(set(CANONICAL_PREFIXES))
    validation = validate_canonical_names(sample_names or [])
    return {
        "parsed_prefixes": parsed_prefixes,
        "expected_prefixes": list(CANONICAL_PREFIXES),
        "prefixes_match": prefix_match,
        "sample_validation": validation,
    }


def verify_m0(repo_root: Path | None = None) -> dict:
    repo_root = get_repo_root(repo_root)
    governance_texts = load_governance_text(repo_root)
    syntax = governance_syntax_report(governance_texts)
    registry = build_canonical_registry(repo_root, timestamp=timestamp_utc())
    id_uniqueness = verify_identity_uniqueness(registry["sources"], key="id")
    path_uniqueness = verify_identity_uniqueness(
        [{"path": path} for source in registry["sources"] for path in source["paths"]],
        key="path",
    )
    paths = canonical_paths_report(repo_root, registry)
    conflict_rules = conflict_rule_report(governance_texts["04_CONFLICT_RESOLUTION_AND_PRECEDENCE.md"])
    naming_rules = naming_rules_report(governance_texts["03_CANONICAL_NAMING_RULES.md"])

    verdict = {
        "certified": all(
            [
                all(item["ends_with_end"] for item in syntax.values()),
                paths["all_exist"],
                id_uniqueness["unique"],
                path_uniqueness["unique"],
                conflict_rules["rules_present"],
                naming_rules["prefixes_match"],
            ]
        ),
        "reasons": {
            "governance_syntax": syntax,
            "canonical_paths": paths,
            "id_uniqueness": id_uniqueness,
            "path_uniqueness": path_uniqueness,
            "conflict_rules": conflict_rules,
            "naming_rules": naming_rules,
        },
    }

    return {
        "timestamp": registry["timestamp"],
        "registry": registry,
        "governance_syntax": syntax,
        "canonical_paths": paths,
        "id_uniqueness": id_uniqueness,
        "path_uniqueness": path_uniqueness,
        "conflict_rules": conflict_rules,
        "naming_rules": naming_rules,
        "verdict": verdict,
    }


def timestamp_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_evidence_files(evidence_dir: Path, results: dict) -> None:
    evidence_dir.mkdir(parents=True, exist_ok=True)

    write_json(evidence_dir / "canonical_registry.json", results["registry"])
    write_json(evidence_dir / "naming_validation_report.json", results["naming_rules"])
    write_json(evidence_dir / "conflict_detection_report.json", results["conflict_rules"])
    write_json(evidence_dir / "certification_verdict.json", results["verdict"])


def write_summary_reports(evidence_dir: Path, results: dict) -> None:
    timestamp = results["timestamp"]
    verdict = "CERTIFIED" if results["verdict"]["certified"] else "NOT CERTIFIED"

    certification_report = f"""# M0 Certification Report

- Timestamp (UTC): {timestamp}
- Verdict: {verdict}

## Invariants Checked
- Single source of truth per concept (canonical registry uniqueness)
- No silent overrides (conflict precedence rules present)
- Canonical names immutable (naming rule prefixes validated)
- Metadata epochs may certify, not redefine (governance syntax present)

## Path Validation
- Missing paths: {json.dumps(results['canonical_paths']['missing'])}

## Patches Applied
- Added M0 canonical helper utilities and verifier.
- Added metadata tests and audit evidence artifacts.
"""

    evidence_dir.joinpath("M0_CERTIFICATION_REPORT.md").write_text(certification_report)

    summary = f"""# M0 Verification Summary

Timestamp (UTC): {timestamp}
Verdict: {verdict}

- Canonical sources listed: {len(results['registry']['sources'])}
- Governance files parseable: {all(item['ends_with_end'] for item in results['governance_syntax'].values())}
- Conflict rules present: {results['conflict_rules']['rules_present']}
"""
    evidence_dir.joinpath("M0_VERIFICATION_SUMMARY.md").write_text(summary)

    index = []
    for path in sorted(evidence_dir.iterdir()):
        if path.is_file():
            index.append(
                {
                    "file": path.name,
                    "sha256": sha256_for_file(path),
                    "bytes": path.stat().st_size,
                }
            )
    write_json(evidence_dir / "M0_EVIDENCE_INDEX.json", {"timestamp": timestamp, "files": index})


def run_full_verification(evidence_dir: Path | None = None) -> dict:
    repo_root = get_repo_root()
    if evidence_dir is None:
        evidence_dir = (
            repo_root
            / "TRADING_OS_MASTER_CATALOGUE"
            / "AUDIT_EVIDENCE"
            / "M0_CANON_AND_SOURCES_OF_TRUTH"
        )
    results = verify_m0(repo_root)
    write_evidence_files(evidence_dir, results)
    write_summary_reports(evidence_dir, results)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Run M0 canonical verification")
    parser.add_argument(
        "--evidence-dir",
        type=Path,
        default=None,
        help="Optional evidence output directory",
    )
    args = parser.parse_args()
    run_full_verification(args.evidence_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
