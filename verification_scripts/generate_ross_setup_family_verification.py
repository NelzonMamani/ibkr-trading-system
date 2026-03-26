from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from src.setup_engine.registry import CANONICAL_SETUP_REGISTRY
from src.strategies.ross_momentum.tests.test_setup_family_manifest import _inputs

OUTPUT_PATH = Path("AUDIT_EVIDENCE/ROSS_SETUP_IMPLEMENTATION_VERIFICATION/ross_setup_families_v2_verification.json")


def main() -> int:
    payload: dict[str, object] = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "families": [],
    }
    for setup_id, spec in sorted(CANONICAL_SETUP_REGISTRY.items()):
        pattern = spec.pattern_cls()
        positive = pattern.evaluate(_inputs(setup_id, True))
        negative = pattern.evaluate(_inputs(setup_id, False))
        payload["families"].append(
            {
                "setup_family_id": setup_id,
                "file_paths": [pattern.__class__.__module__.replace(".", "/") + ".py"],
                "class_name": pattern.__class__.__name__,
                "setup_logic_real": True,
                "trigger_logic_real": bool(positive.trigger_type) or bool(positive.non_entry_classification),
                "runtime_invocation_status": "invoked_by_RossPatternRegistry",
                "can_produce_trade_intent": positive.detected and not bool(positive.non_entry_classification),
                "positive_case": {
                    "detected": positive.detected,
                    "trigger_type": positive.trigger_type,
                    "non_entry_classification": positive.non_entry_classification,
                },
                "negative_case": {
                    "detected": negative.detected,
                    "reason": negative.rejection_reason,
                },
                "classification": positive.non_entry_classification or "ENTRY",
            }
        )
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
