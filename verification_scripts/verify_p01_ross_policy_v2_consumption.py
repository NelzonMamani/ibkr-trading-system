from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.strategy_policy_v2.consumption import (
    FocusBuilderV2,
    RankingEngineV2,
    SelectionEngineV2,
    WatchlistBuilderV2,
)
from src.strategies.ross_momentum.strategy_policy_v2 import POLICY_V2

EVIDENCE_ROOT = REPO_ROOT / "TRADING_OS_MASTER_CATALOGUE" / "AUDIT_EVIDENCE" / "P01_ROSS_POLICY_V2_CONSUMPTION"


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _fixtures() -> list[dict]:
    return [
        {"symbol": "AAA", "session_label": "PRE", "last_price": 6.0, "pct_change": 35.0, "volume": 3000000, "premarket_volume": 300000, "rvol": 9.0, "dollar_volume": 22000000.0, "float_millions": 8.0, "spread_pct": 0.4, "halted": False, "ssr": False, "news_catalyst": "HIGH"},
        {"symbol": "BBB", "session_label": "PRE", "last_price": 8.0, "pct_change": 22.0, "volume": 2500000, "premarket_volume": 200000, "rvol": 7.0, "dollar_volume": 18000000.0, "float_millions": 12.0, "spread_pct": 0.7, "halted": False, "ssr": False, "news_catalyst": True},
        {"symbol": "CCC", "session_label": "RTH", "last_price": 30.0, "pct_change": 25.0, "volume": 4000000, "premarket_volume": 300000, "rvol": 8.0, "dollar_volume": 35000000.0, "float_millions": 10.0, "spread_pct": 0.5, "halted": False, "ssr": False, "news_catalyst": True},
    ]


def main() -> int:
    evidence_dir = EVIDENCE_ROOT / _ts()
    evidence_dir.mkdir(parents=True, exist_ok=True)

    rg_cmd = ["rg", "-n", "SelectionEngineV2|_build_watchlist_focus_v2|STRATEGY_POLICY_V2_ENABLED|ROSS_POLICY_V2", "src/core/orchestrator.py"]
    rg_result = subprocess.run(rg_cmd, cwd=REPO_ROOT, text=True, capture_output=True, check=False)

    candidates = _fixtures()
    selection = SelectionEngineV2().evaluate(POLICY_V2, candidates)
    ranking = RankingEngineV2().rank(POLICY_V2, selection.eligible)
    watchlist = WatchlistBuilderV2().build(POLICY_V2, ranking.ranked)
    focus = FocusBuilderV2().build(POLICY_V2, ranking.ranked)

    ranked_rows = [{"symbol": row.candidate.get("symbol"), "score": row.score, "score_breakdown": row.score_breakdown} for row in ranking.ranked]
    dropped_rows = [{"symbol": row.candidate.get("symbol"), "reasons": row.reasons} for row in selection.dropped]

    (evidence_dir / "WATCHLIST.json").write_text(json.dumps(watchlist.watchlist, indent=2) + "\n", encoding="utf-8")
    (evidence_dir / "FOCUS.json").write_text(json.dumps(focus.focus, indent=2) + "\n", encoding="utf-8")
    (evidence_dir / "DROPPED.json").write_text(json.dumps(dropped_rows, indent=2) + "\n", encoding="utf-8")
    (evidence_dir / "RANKED.json").write_text(json.dumps(ranked_rows, indent=2) + "\n", encoding="utf-8")
    (evidence_dir / "SELECTION_OUTPUTS.json").write_text(json.dumps({"metrics": selection.metrics, "dropped": dropped_rows}, indent=2) + "\n", encoding="utf-8")
    (evidence_dir / "RANKING_OUTPUTS.json").write_text(json.dumps({"ranked": ranked_rows}, indent=2) + "\n", encoding="utf-8")

    (evidence_dir / "CONSUMPTION_TRACE.md").write_text(
        "\n".join(
            [
                "# CONSUMPTION_TRACE",
                "",
                "## Runtime call-site trace",
                "```",
                rg_result.stdout.strip(),
                "```",
                "",
                "## Deterministic dry-run",
                f"- eligible_count: {len(selection.eligible)}",
                f"- dropped_count: {len(selection.dropped)}",
                f"- watchlist_symbols: {[row.get('symbol') for row in watchlist.watchlist]}",
                f"- focus_symbols: {[row.get('symbol') for row in focus.focus]}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (evidence_dir / "console_log.txt").write_text(f"$ {' '.join(rg_cmd)}\n\n{rg_result.stdout}\n{rg_result.stderr}".strip() + "\n", encoding="utf-8")
    print(json.dumps({"evidence_dir": str(evidence_dir), "watchlist": [x.get("symbol") for x in watchlist.watchlist]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
