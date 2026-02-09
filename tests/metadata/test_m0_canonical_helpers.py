from pathlib import Path

from src.metadata.m0_canon_helpers import (
    get_repo_root,
    list_canonical_sources,
    validate_canonical_names,
    verify_identity_uniqueness,
)


def test_canonical_sources_unique_and_exist() -> None:
    repo_root = get_repo_root(Path(__file__).resolve())
    sources = list_canonical_sources(repo_root)
    uniqueness = verify_identity_uniqueness(sources, key="id")
    assert uniqueness["unique"]
    for source in sources:
        for rel_path in source["paths"]:
            assert (repo_root / rel_path).exists(), f"Missing canonical path: {rel_path}"


def test_validate_canonical_names_rules() -> None:
    valid_names = ["SF_ALPHA", "XL_BETA", "C_GAMMA", "K_DELTA"]
    validation = validate_canonical_names(valid_names)
    assert validation["valid"]

    invalid_names = ["SF_ALPHA", "INVALID_NAME"]
    invalid_validation = validate_canonical_names(invalid_names)
    assert not invalid_validation["valid"]
    assert "INVALID_NAME" in invalid_validation["invalid_prefix"]
