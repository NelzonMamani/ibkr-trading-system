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

EVIDENCE_ROOT = (
    REPO_ROOT / "TRADING_OS_MASTER_CATALOGUE" / "AUDIT_EVIDENCE" / "P02_STATISTICAL_INTRADAY_MOMENTUM_POLICY_V2_CONSUMPTION"
)


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _fixtures() -> list[dict]:
    return [
        {
            "symbol": "SIMA",
            "session_label": "PRE",
            "last_price": 7.5,
            "pct_change": 28.0,
            "volume": 2_700_000,
            "premarket_volume": 260_000,
            "rvol": 8.4,
            "dollar_volume": 19_400_000.0,
            "float_millions": 11.0,
            "spread_pct": 0.45,
            "halted": False,
            "ssr": False,
            "news_catalyst": "HIGH",
        },
        {
            "symbol": "SIMB",
            "session_label": "RTH",
            "last_price": 9.1,
            "pct_change": 19.5,
            "volume": 2_100_000,
            "premarket_volume": 180_000,
            "rvol": 6.2,
            "dollar_volume": 15_200_000.0,
            "float_millions": 17.0,
            "spread_pct": 0.7,
            "halted": False,
            "ssr": False,
            "news_catalyst": True,
        },
        {
            "symbol": "SIMC",
            "session_label": "AH",
            "last_price": 5.2,
            "pct_change": 12.0,
            "volume": 1_800_000,
            "premarket_volume": 120_000,
            "rvol": 4.9,
            "dollar_volume": 9_400_000.0,
            "float_millions": 24.0,
            "spread_pct": 1.2,
            "halted": False,
            "ssr": False,
            "news_catalyst": False,
        },
    ]


def main() -> int:
    evidence_dir = EVIDENCE_ROOT / _ts()
    evidence_dir.mkdir(parents=True, exist_ok=True)

    rg_cmd = [
        "rg",
        "-n",
        "resolve_policy_v2|is_policy_v2_enabled_for_strategy|STRATEGY_POLICY_V2_STRATEGIES|SelectionEngineV2",
        "src/core/orchestrator.py",
        "src/strategy_policy_v2/registry.py",
        "src/config/config_registry.py",
    ]
    rg_result = subprocess.run(rg_cmd, cwd=REPO_ROOT, text=True, capture_output=True, check=False)

    policy = resolve_policy_v2("statistical_intraday_momentum")
    if policy is None:
        raise RuntimeError("resolve_policy_v2 returned None for statistical_intraday_momentum")

    candidates = _fixtures()
    selection = SelectionEngineV2().evaluate(policy, candidates)
    ranking = RankingEngineV2().rank(policy, selection.eligible)
    watchlist = WatchlistBuilderV2().build(policy, ranking.ranked)
    focus = FocusBuilderV2().build(policy, ranking.ranked)

    ranked_rows = [{"symbol": row.candidate.get("symbol"), "score": row.score} for row in ranking.ranked]
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
                "## Resolver smoke",
                f"- strategy_id: {policy.identity.strategy_id}",
                f"- strategy_name: {policy.identity.name}",
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
    (evidence_dir / "console_log.txt").write_text(
        f"$ {' '.join(rg_cmd)}\n\n{rg_result.stdout}\n{rg_result.stderr}".strip() + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"evidence_dir": str(evidence_dir), "watchlist": [x.get("symbol") for x in watchlist.watchlist]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
