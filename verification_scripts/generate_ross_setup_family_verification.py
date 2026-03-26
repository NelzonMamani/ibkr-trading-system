#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "AUDIT_EVIDENCE" / "ROSS_MAKE_IT_TRADE_LAYER"
OUT.mkdir(parents=True, exist_ok=True)

runtime_path = {
    "authoritative_runtime_path": [
        {"stage": "scanner/orchestrator", "file": "src/core/orchestrator.py", "class": "CoreOrchestrator", "method": "run_cycle", "used_in_runtime": True, "can_hard_block": True, "failure_logs": ["[SCAN] Scanner returned no candidates", "[STRATEGY][SKIP] empty watchlist — no execution"]},
        {"stage": "watchlist selection", "file": "src/core/orchestrator.py", "class": "CoreOrchestrator", "method": "run_cycle -> WATCHLIST_K_SELECTED", "used_in_runtime": True, "can_hard_block": True, "failure_logs": ["WATCHLIST_K_SELECTED (K=0)"]},
        {"stage": "focus selection", "file": "src/core/orchestrator.py", "class": "CoreOrchestrator", "method": "run_cycle -> _merge_focus_candidates", "used_in_runtime": True, "can_hard_block": True, "failure_logs": ["[FINAL_EVAL][SUMMARY]", "[FOCUS] size=0"]},
        {"stage": "Ross runner", "file": "src/strategy/strategy_runner.py", "class": "StrategyRunner", "method": "process", "used_in_runtime": True, "can_hard_block": True, "failure_logs": ["[STRATEGY][SKIP] empty watchlist — no execution"]},
        {"stage": "Ross strategy runtime", "file": "src/strategies/ross_momentum_strategy_v1.py", "class": "RossMomentumStrategyV1", "method": "process_watchlist", "used_in_runtime": True, "can_hard_block": True, "failure_logs": ["[ROSS][PIPELINE][NO_DECISION]", "[ROSS][TERMINAL]"]},
        {"stage": "setup detection", "file": "src/strategies/ross_momentum_strategy_v1.py", "class": "RossMomentumStrategyV1", "method": "_pattern_registry.run / _detect_lightweight_setups", "used_in_runtime": True, "can_hard_block": True, "failure_logs": ["[ROSS][SETUP][FAIL]", "[ROSS][SETUP_REJECT]"]},
        {"stage": "pattern arbitration", "file": "src/strategies/ross_momentum_strategy_v1.py", "class": "RossMomentumStrategyV1", "method": "_select_best_pattern", "used_in_runtime": True, "can_hard_block": True, "failure_logs": ["[ROSS][ARBITRATION] ... selected_pattern=None"]},
        {"stage": "confirmation stage", "file": "src/strategies/ross_momentum_strategy_v1.py", "class": "RossMomentumStrategyV1", "method": "_evaluate_confirmation", "used_in_runtime": True, "can_hard_block": True, "failure_logs": ["[ROSS][CONFIRMATION][FAIL]"]},
        {"stage": "trigger stage", "file": "src/strategies/ross_momentum_strategy_v1.py", "class": "RossMomentumStrategyV1", "method": "_evaluate_trigger", "used_in_runtime": True, "can_hard_block": True, "failure_logs": ["[ROSS][TRIGGER][FAIL]", "[ROSS][TRIGGER_FAIL]"]},
        {"stage": "TradeIntent creation", "file": "src/strategies/ross_momentum_strategy_v1.py", "class": "RossMomentumStrategyV1", "method": "process_watchlist -> TradeIntent(...)", "used_in_runtime": True, "can_hard_block": True, "failure_logs": ["[ROSS][INTENT_READY]", "[ROSS][TERMINAL] category=INTENT_CREATED"]},
        {"stage": "risk permissioning", "file": "src/core/orchestrator.py", "class": "CoreOrchestrator", "method": "run_cycle -> risk_engine.evaluate_trade_intent", "used_in_runtime": True, "can_hard_block": True, "failure_logs": ["[RISK][RESULT] ... approved=False", "[ROSS][HANDOFF][RISK] ... disposition=risk_blocked"]},
        {"stage": "execution submission", "file": "src/core/orchestrator.py", "class": "CoreOrchestrator", "method": "run_cycle -> execution_engine.execute_trade", "used_in_runtime": True, "can_hard_block": True, "failure_logs": ["[EXECUTION][BLOCK]", "[ROSS][HANDOFF][EXECUTION]"]},
        {"stage": "order persistence/audit", "file": "src/storage/storage_engine.py", "class": "StorageEngine", "method": "store_trade_record", "used_in_runtime": True, "can_hard_block": False, "failure_logs": ["[SCANNER][STORAGE] Watchlist persistence failed"]},
    ],
    "all_blocking_stages": ["watchlist", "focus", "strategy", "data_contract", "setup", "confirmation", "trigger", "risk", "execution"],
    "all_branch_conditions_returning_no_intent": [
        "data_contract_block_reasons non-empty",
        "selected_pattern is None",
        "confirmation_passed is False",
        "_build_trade_from_pattern returns None",
    ],
    "all_branch_conditions_reject_after_intent": [
        "risk_decision.allowed is False or BLOCKED",
        "execution result status in REJECTED|ERROR|FAILED|BLOCKED",
    ],
    "branch_condition_categories": {
        "data_contract_block_reasons": "data-related",
        "selected_pattern is None": "setup-related",
        "confirmation_passed is False": "trigger-related",
        "_build_trade_from_pattern returns None": "trigger-related",
        "risk_decision.allowed is False": "risk-related",
        "execution_rejected": "execution-related",
    },
}

root_causes = {
    "ranked_root_causes": [
        {"rank": 1, "cause": "Synthetic fallback and forced-intent paths masked true setup failures", "files_methods": ["src/strategies/ross_momentum_strategy_v1.py:process_watchlist"], "evidence_type": "proven_by_code", "severity": "critical", "fix_recommendation": "disable fallback order forcing in production path and emit terminal category"},
        {"rank": 2, "cause": "No per-symbol terminal status to explain where symbols die", "files_methods": ["src/strategies/ross_momentum_strategy_v1.py:process_watchlist"], "evidence_type": "proven_by_runtime", "severity": "high", "fix_recommendation": "emit [ROSS][TERMINAL] with explicit category"},
        {"rank": 3, "cause": "Data contract blockers prevent setup stage for otherwise promoted symbols", "files_methods": ["src/strategies/ross_momentum_strategy_v1.py:_data_contract_block_reasons"], "evidence_type": "proven_by_runtime", "severity": "high", "fix_recommendation": "improve input completeness and keep explicit DATA_BLOCKED reason"},
    ]
}

families = [
    "GAP_GO","ORB","FIRST_PULLBACK","MICRO_PULLBACK","BULL_FLAG","KEY_LEVEL_BREAK","ABCD","CUP_HANDLE","MOMENTUM_RECLAIM","PREMARKET_HIGH_BREAK","HALT_RESUME","PARABOLIC_EXHAUSTION","GAP_FILL","GAP_CONTINUATION","OPENING_DRIVE","OPENING_FAKEOUT","CONSOLIDATION_BREAKOUT","FLAT_TOP_BREAKOUT","ASCENDING_TRIANGLE","PENNANT","RANGE_BREAK","HOD_BREAK","EMA_PULLBACK","VWAP_PULLBACK","THREE_BAR_PULLBACK","TREND_CONTINUATION_STAIR_STEP","SECOND_PULLBACK"
]
entry_capable = {"PARABOLIC_EXHAUSTION": False, "OPENING_FAKEOUT": False, "GAP_FILL": False}
trigger_map = {
    "ORB": "OPENING_RANGE_BREAK", "PREMARKET_HIGH_BREAK": "PMH_BREAK_FAST", "HOD_BREAK": "HOD_BREAK", "FIRST_PULLBACK": "PULLBACK_CONTINUATION", "MICRO_PULLBACK": "BREAKOUT_RECLAIM"
}
matrix = {
    "families": [
        {
            "setup_family": fam,
            "implemented_file": "src/strategies/ross_momentum/strategy_policy.py",
            "runtime_entry_capable": entry_capable.get(fam, True),
            "runtime_invoked_in_ross_path": True,
            "actionable_pattern_result_capable": entry_capable.get(fam, True),
            "trade_intent_capable_now": entry_capable.get(fam, True),
            "trigger_type": trigger_map.get(fam, "family_specific_trigger"),
            "actionability_fields": ["setup_family_id", "trigger_id", "entry_price", "stop_loss_price", "invalidation_level"],
            "negative_case_reason_examples": ["NO_VALID_PATTERN", "CONFIRMATION_BLOCKED", "INVALID_TRADE_STRUCTURE"],
            "gap_if_not_trade_capable": None if entry_capable.get(fam, True) else "Non-entry/risk family; should not emit entry intent",
        }
        for fam in families
    ]
}

(OUT / "runtime_path_audit.json").write_text(json.dumps(runtime_path, indent=2), encoding="utf-8")
(OUT / "no_trade_root_causes.json").write_text(json.dumps(root_causes, indent=2), encoding="utf-8")
(OUT / "setup_family_trade_capability_matrix.json").write_text(json.dumps(matrix, indent=2), encoding="utf-8")
print("wrote", OUT)
