from pathlib import Path

from src.e21.harness import run_harness


def test_harness_reports(tmp_path: Path):
    report = run_harness(tmp_path)
    assert report["verdict"] in {"PASS", "FAIL"}
    assert (tmp_path / "harness_report.json").exists()
    assert (tmp_path / "harness_report.md").exists()
    assert (tmp_path / "E21_CERTIFICATION_REPORT.md").exists()
    assert (tmp_path / "E21_EVIDENCE_INDEX.json").exists()
    assert (tmp_path / "E21_MODE_PARITY_MATRIX.md").exists()
    assert (tmp_path / "E21_SCENARIO_COVERAGE.md").exists()
    assert (tmp_path / "E21_FAILURE_DRILLS_REPORT.md").exists()
    assert (tmp_path / "E21_NON_INTERFERENCE_PROOF.md").exists()
