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


def test_registry_has_mean_reversion() -> None:
    assert has_policy_v2("mean_reversion") is True


def test_registry_resolves_mean_reversion_p03() -> None:
    policy = resolve_policy_v2("mean_reversion")
    assert policy is not None
    assert policy.identity.strategy_id == "P03"


def test_registry_lists_import_path() -> None:
    paths = list_registered_policies_v2()
    assert paths["ross_momentum"] == "src.strategies.ross_momentum.strategy_policy_v2.POLICY_V2"
    assert paths["mean_reversion"] == "src.strategies.mean_reversion.strategy_policy_v2.POLICY_V2"
