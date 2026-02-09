from src.metadata.m2_contract_verifier import verify_registry


def test_m2_contract_registry_paths() -> None:
    result = verify_registry()
    assert result["missing_paths"] == []
    assert result["declared_path_violations"] == []
