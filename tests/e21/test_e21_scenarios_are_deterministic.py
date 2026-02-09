from src.e21.scenarios import get_scenario, list_scenario_ids


def test_scenarios_are_deterministic():
    for scenario_id in list_scenario_ids():
        first = get_scenario(scenario_id)
        second = get_scenario(scenario_id)
        assert first == second
        assert first.context == second.context
