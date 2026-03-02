from src.strategy_policy_v2.registry import (
    has_policy_v2,
    list_registered_policies_v2,
    resolve_policy_v2,
)


def test_registry_has_ross_momentum() -> None:
    assert has_policy_v2("ross_momentum") is True


def test_registry_resolves_ross_momentum_p01() -> None:
    policy = resolve_policy_v2("ross_momentum")
    assert policy is not None
    assert policy.identity.strategy_id == "P01"


def test_registry_unknown_returns_none() -> None:
    assert resolve_policy_v2("unknown") is None


def test_registry_lists_import_path() -> None:
    paths = list_registered_policies_v2()
    assert paths["ross_momentum"] == "src.strategies.ross_momentum.strategy_policy_v2.POLICY_V2"


def test_registry_has_statistical_intraday_momentum() -> None:
    assert has_policy_v2("statistical_intraday_momentum") is True


def test_registry_resolves_statistical_intraday_momentum_p02() -> None:
    policy = resolve_policy_v2("statistical_intraday_momentum")
    assert policy is not None
    assert policy.identity.strategy_id == "P02"


def test_registry_lists_import_path_for_p02() -> None:
    paths = list_registered_policies_v2()
    assert (
        paths["statistical_intraday_momentum"]
        == "src.strategies.statistical_intraday_momentum.strategy_policy_v2.POLICY_V2"
    )
