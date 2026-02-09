from src.metadata.m2_contract_registry import load_registry, validate_registry


def test_m2_contract_registry_schema() -> None:
    registry = load_registry()
    errors = validate_registry(registry)
    assert errors == []
