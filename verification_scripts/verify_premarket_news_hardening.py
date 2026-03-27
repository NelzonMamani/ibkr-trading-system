from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from src.prep.premarket_prep import PreMarketPrepEngine
from src.prep.premarket_prep_artifact import write_canonical_premarket_prep_artifact


def main() -> int:
    engine = PreMarketPrepEngine()
    symbols = ["AAPL", "TSLA", "NVDA"]
    engine.update_from_universe(
        symbols,
        last_price_by_symbol={"AAPL": 211.2, "TSLA": 188.6, "NVDA": 1025.0},
        float_by_symbol={"AAPL": 15_000_000_000, "TSLA": 3_200_000_000, "NVDA": 2_450_000_000},
        prior_close_by_symbol={"AAPL": 206.1, "TSLA": 179.5, "NVDA": 1000.0},
        gap_pct_by_symbol={"AAPL": 2.47, "TSLA": 5.07, "NVDA": 2.5},
        persisted_pct_change_by_symbol={"AAPL": 2.47, "TSLA": 5.07, "NVDA": 2.5},
        persisted_rvol_by_symbol={"AAPL": 1.6, "TSLA": 2.4, "NVDA": 2.1},
        persisted_volume_by_symbol={"AAPL": 500_000, "TSLA": 800_000, "NVDA": 420_000},
        reason="VERIFY_PREMARKET_NEWS_HARDENING",
    )

    payload = engine.build_artifact_payload(symbols)
    out_path = write_canonical_premarket_prep_artifact(payload)

    audit_dir = Path("AUDIT_EVIDENCE/premarket_news_hardening")
    audit_dir.mkdir(parents=True, exist_ok=True)
    (audit_dir / "symbol_context_packets.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    rows = payload.get("symbols", [])
    summary = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "symbols": len(rows),
        "ready_high_quality": sum(1 for row in rows if row.get("terminal_state") == "READY_HIGH_QUALITY"),
        "ready_medium_quality": sum(1 for row in rows if row.get("terminal_state") == "READY_MEDIUM_QUALITY"),
        "not_ready": sum(1 for row in rows if str(row.get("terminal_state") or "").startswith("NOT_READY_")),
    }
    (audit_dir / "premarket_quality_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (audit_dir / "prep_terminal_states.json").write_text(
        json.dumps([{"symbol": row.get("symbol"), "terminal_state": row.get("terminal_state"), "reason": row.get("terminal_reason")} for row in rows], indent=2),
        encoding="utf-8",
    )

    lines = [
        "symbol | float_state | catalyst_state | prep_state | quality_score | watchlist_rank | focus_status"
    ]
    for row in rows:
        catalyst_state = "CATALYST_PRESENT" if (row.get("catalyst_packet") or {}).get("catalyst_present") else "NO_CATALYST"
        lines.append(
            f"{row.get('symbol')} | {row.get('float_state')} | {catalyst_state} | {row.get('terminal_state')} | {row.get('premarket_quality_score')} | {row.get('watchlist_rank')} | {row.get('focus_status')}"
        )
    rendered = "\n".join(lines)
    print(rendered)
    (audit_dir / "verification_premarket_news_hardening.txt").write_text(
        rendered + f"\nartifact_path={out_path}\n", encoding="utf-8"
    )

    before_after = {
        "note": "synthetic comparison for verification",
        "before": [{"symbol": row.get("symbol"), "rank": idx + 1} for idx, row in enumerate(sorted(rows, key=lambda r: r.get("symbol")))],
        "after": [{"symbol": row.get("symbol"), "rank": row.get("watchlist_rank"), "score": row.get("premarket_quality_score")} for row in rows],
    }
    (audit_dir / "ranking_before_after_comparison.json").write_text(json.dumps(before_after, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
