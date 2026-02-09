from src.metadata.m2_contract_registry import (
    ALLOWED_MODES,
    ALLOWED_OWNER_COMPONENTS,
    load_registry,
)


def test_m2_contract_registry_invariants() -> None:
    registry = load_registry()
    contracts = registry["contracts"]
    ids = [contract["id"] for contract in contracts]
    assert len(ids) == len(set(ids))
    assert all(contract_id.startswith("C_") for contract_id in ids)
    assert {
        contract["owner_component"] for contract in contracts
    }.issubset(ALLOWED_OWNER_COMPONENTS)
    for contract in contracts:
        assert set(contract["applies_to_modes"]).issubset(ALLOWED_MODES)
