# RUNTIME_WIRING_TRACE

## Search roots
- src

## Surface consumption evidence

### selection_plan
- `src/metadata/strategy_policy_v2_audit.py:230` -> `_control("D1", 1, "CRITICAL", policy.selection_plan is not None, "selection_plan missing"),`
- `src/strategy_policy_v2/README.md:3` -> `This package defines a specification-only `StrategyPolicyV2` contract and tagged-union `selection_plan` models.`
- `src/strategy_policy_v2/policy_v2.py:6` -> `from src.strategy_policy_v2.selection_plans import SelectionPlan`
- `src/strategy_policy_v2/policy_v2.py:515` -> `selection_plan: SelectionPlan`
- `src/strategy_policy_v2/types.py:41` -> `from src.strategy_policy_v2.selection_plans import (`

### stock_selection_law
- `src/metadata/strategy_policy_v2_audit.py:231` -> `_control("D1", 2, "CRITICAL", policy.stock_selection_law is not None, "stock_selection_law missing"),`
- `src/strategy_policy_v2/policy_v2.py:538` -> `stock_selection_law: StockSelectionLawV2 = field(default_factory=StockSelectionLawV2)`

### ranking_model
- `src/metadata/strategy_policy_v2_audit.py:233` -> `_control("D1", 4, "MAJOR", policy.ranking_model is not None and (_is_non_empty_text(policy.ranking_model.ranking_commentary) or _na_declared(policy, "RANK")), "ranking model missing rationale", na=_na_declared(policy, "RANK")),`
- `src/strategy_policy_v2/policy_v2.py:540` -> `ranking_model: RankingModelV2 = field(default_factory=RankingModelV2)`

### risk/exit/trailing
- `src/directory_tree_report.txt:917` -> `│   │   │   │   ├── test_exit_models.py`
- `src/directory_tree_report.txt:927` -> `│   │   │   ├── exit_models.py`
- `src/metadata/strategy_policy_v2_audit.py:188` -> `and len(policy.exit_model.rules) == 0`
- `src/metadata/strategy_policy_v2_audit.py:291` -> `_control("D7", 1, "CRITICAL", policy.risk_model is not None, "risk_model missing"),`
- `src/metadata/strategy_policy_v2_audit.py:301` -> `_control("D8", 1, "MAJOR", len(policy.exit_model.rules) >= 1, "exit rules require >=1", na=_na_declared(policy, "EXIT")),`
- `src/metadata/strategy_policy_v2_audit.py:302` -> `_control("D8", 2, "MINOR", len(policy.trailing_model.rules) >= 1, "trailing rules should be declared", na=trailing_na),`
- `src/metadata/strategy_policy_v2_audit.py:303` -> `_control("D8", 3, "MINOR", len(policy.exit_model.rules) >= 1 or len(policy.intrabar_execution.safety_throttles) >= 1, "failure-fast bailout behavior not declared"),`
- `src/strategy_policy_v2/policy_v2.py:518` -> `risk_model: RiskModelV2`
- `src/strategy_policy_v2/policy_v2.py:535` -> `trailing_model: TrailingModelV2 = field(default_factory=TrailingModelV2)`
- `src/strategy_policy_v2/policy_v2.py:536` -> `exit_model: ExitModelV2 = field(default_factory=ExitModelV2)`

## Grep evidence
- `rg -n \\.selection_plan src` (exit=1)
- `rg -n selection_plan src` (exit=0)
- `rg -n \\.stock_selection_law src` (exit=1)
- `rg -n stock_selection_law src` (exit=0)
- `rg -n \\.ranking_model src` (exit=1)
- `rg -n ranking_model src` (exit=0)
- `rg -n \\.risk_model src` (exit=1)
- `rg -n \\.exit_model src` (exit=1)
- `rg -n \\.trailing_model src` (exit=1)
- `rg -n risk_model src` (exit=0)
- `rg -n exit_model src` (exit=0)
- `rg -n trailing_model src` (exit=0)
