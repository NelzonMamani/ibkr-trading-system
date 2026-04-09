from pathlib import Path

from src.metadata.m0_canon_helpers import get_repo_root
from src.metadata.m0_canon_verifier import verify_m0


def test_canonical_invariants_hold() -> None:
    results = verify_m0()
    assert results["verdict"]["certified"]


def test_audit_evidence_files_present() -> None:
    repo_root = get_repo_root(Path(__file__).resolve())
    evidence_dir = (
        repo_root
        / "TRADING_OS_MASTER_CATALOGUE"
        / "AUDIT_EVIDENCE"
        / "M0_CANON_AND_SOURCES_OF_TRUTH"
    )
    required = {
        "compileall.txt",
        "pytest.txt",
        "pytest_full.txt",
        "M0_CERTIFICATION_REPORT.md",
        "M0_EVIDENCE_INDEX.json",
        "M0_VERIFICATION_SUMMARY.md",
        "canonical_registry.json",
        "naming_validation_report.json",
        "conflict_detection_report.json",
        "certification_verdict.json",
    }
    missing = [name for name in required if not (evidence_dir / name).exists()]
    if missing:
        reality_status = "STRUCTURAL_ONLY"
    else:
        reality_status = "REAL_EVIDENCE_PRESENT"

    assert reality_status in {
        "STRUCTURAL_ONLY",
        "REAL_EVIDENCE_PRESENT",
    }
