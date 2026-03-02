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
from src.strategy_policy_v2.registry import resolve_policy_v2

EVIDENCE_ROOT = REPO_ROOT / "TRADING_OS_MASTER_CATALOGUE" / "AUDIT_EVIDENCE" / "P03_MEAN_REVERSION_POLICY_V2_CONSUMPTION"


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _fixtures() -> list[dict]:
    return [
        {
            "symbol": "MRV1",
            "session_label": "RTH",
            "last_price": 18.5,
            "pct_change": 12.0,
            "volume": 2_200_000,
            "premarket_volume": 140_000,
            "rvol": 2.4,
            "dollar_volume": 30_000_000.0,
            "float_millions": 55.0,
            "spread_pct": 0.35,
            "halted": False,
            "ssr": False,
            "news_catalyst": "EARNINGS",
        },
        {
            "symbol": "MRV2",
            "session_label": "RTH",
            "last_price": 42.0,
            "pct_change": 19.0,
            "volume": 1_900_000,
            "premarket_volume": 90_000,
            "rvol": 2.0,
            "dollar_volume": 34_000_000.0,
            "float_millions": 120.0,
            "spread_pct": 0.55,
            "halted": False,
            "ssr": True,
            "news_catalyst": True,
        },
        {
            "symbol": "MRV3",
            "session_label": "RTH",
            "last_price": 7.4,
            "pct_change": 44.0,
            "volume": 5_000_000,
            "premarket_volume": 280_000,
            "rvol": 6.2,
            "dollar_volume": 24_500_000.0,
            "float_millions": 22.0,
            "spread_pct": 0.75,
            "halted": False,
            "ssr": False,
            "news_catalyst": "NEWSWIRE",
        },
    ]


def main() -> int:
    evidence_dir = EVIDENCE_ROOT / _ts()
    evidence_dir.mkdir(parents=True, exist_ok=True)

    policy = resolve_policy_v2("mean_reversion")
    if policy is None:
        raise RuntimeError("resolve_policy_v2('mean_reversion') returned None")

    rg_cmd = [
        "rg",
        "-n",
        "SelectionEngineV2|RankingEngineV2|WatchlistBuilderV2|FocusBuilderV2|resolve_policy_v2",
        "src/core/orchestrator.py",
    ]
    rg_result = subprocess.run(rg_cmd, cwd=REPO_ROOT, text=True, capture_output=True, check=False)

    candidates = _fixtures()
    selection = SelectionEngineV2().evaluate(policy, candidates)
    ranking = RankingEngineV2().rank(policy, selection.eligible)
    watchlist = WatchlistBuilderV2().build(policy, ranking.ranked)
    focus = FocusBuilderV2().build(policy, ranking.ranked)

    ranked_rows = [
        {"symbol": row.candidate.get("symbol"), "score": row.score, "score_breakdown": row.score_breakdown}
        for row in ranking.ranked
    ]
    dropped_rows = [{"symbol": row.candidate.get("symbol"), "reasons": row.reasons} for row in selection.dropped]

    (evidence_dir / "WATCHLIST.json").write_text(json.dumps(watchlist.watchlist, indent=2) + "\n", encoding="utf-8")
    (evidence_dir / "FOCUS.json").write_text(json.dumps(focus.focus, indent=2) + "\n", encoding="utf-8")
    (evidence_dir / "RANKED.json").write_text(json.dumps(ranked_rows, indent=2) + "\n", encoding="utf-8")
    (evidence_dir / "DROPPED.json").write_text(json.dumps(dropped_rows, indent=2) + "\n", encoding="utf-8")
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
                f"- strategy_id: {policy.identity.strategy_id}",
                f"- eligible_count: {len(selection.eligible)}",
                f"- dropped_count: {len(selection.dropped)}",
                f"- watchlist_symbols: {[row.get('symbol') for row in watchlist.watchlist]}",
                f"- focus_symbols: {[row.get('symbol') for row in focus.focus]}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (evidence_dir / "console_log.txt").write_text(
        f"$ {' '.join(rg_cmd)}\n\n{rg_result.stdout}\n{rg_result.stderr}".strip() + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"evidence_dir": str(evidence_dir), "strategy_id": policy.identity.strategy_id}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
