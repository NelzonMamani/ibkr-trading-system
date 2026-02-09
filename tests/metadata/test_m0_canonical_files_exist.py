from src.metadata.m0_canon_verifier import verify_m0


def test_governance_files_parseable() -> None:
    results = verify_m0()
    assert all(item["ends_with_end"] for item in results["governance_syntax"].values())


def test_conflict_rules_present() -> None:
    results = verify_m0()
    assert results["conflict_rules"]["rules_present"]
