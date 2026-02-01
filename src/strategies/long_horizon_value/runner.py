"""
Strategy Runner for Long Horizon Value.
Orchestrator calls this runner; it emits TradeIntents only.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping

from src.config.runtime_config import RunMode
from src.models.data_models import TradeIntent
from src.strategies.long_horizon_value import cadence, config, strategy_policy
from src.strategies.long_horizon_value.pipeline import (
    assemble_fundamentals,
    build_dividend_report,
    build_monitoring_reports,
    build_portfolio_plan,
    build_trade_intents,
    compute_economics,
    discover_universe,
    estimate_intrinsic_values,
    evaluate_quality,
    focus_entries_for_report,
    mos_results_for_report,
    rank_by_margin_of_safety,
)
from src.strategies.long_horizon_value.storage import persist_artifact


class LongHorizonValueRunner:
    def run(self, context: Mapping[str, Any]) -> Dict[str, Any]:
        """
        Entry point called by Core Engine.
        This method must:
        - Determine cadence
        - Invoke phases in order
        - Produce TradeIntentBatch (or empty)
        """
        mode = context.get("mode") or RunMode.SIM
        run_window = str(context.get("run_window") or context.get("session_phase") or "").upper()
        reports: List[Dict[str, Any]] = []
        metrics: Dict[str, Any] = {}
        run_id = str(context.get("run_id") or context.get("timestamp_utc") or "")
        if not run_id:
            run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

        if run_window not in cadence.ALLOWED_RUN_WINDOWS:
            reports.append(
                {
                    "phase": "PHASE_00",
                    "status": "SKIPPED_BY_CADENCE",
                    "run_window": run_window,
                    "allowed": cadence.ALLOWED_RUN_WINDOWS,
                }
            )
            return {"trade_intents": [], "reports": reports, "metrics": metrics}

        universe_snapshot = discover_universe(context)
        reports.append(
            {
                "phase": "PHASE_01",
                "mode": universe_snapshot.mode,
                "symbols": len(universe_snapshot.symbols),
                "counts_by_market": universe_snapshot.counts_by_market,
            }
        )

        fundamentals = assemble_fundamentals(
            universe_snapshot.symbols,
            run_id=run_id,
            as_of_year=int(context.get("as_of_year") or 2024),
            missing_symbols=context.get("missing_symbols", []),
        )
        reports.append(
            {
                "phase": "PHASE_02",
                "symbols": len(fundamentals.records),
                "cache_hits": fundamentals.cache_hits,
            }
        )

        market_confidence = context.get("market_confidence", {})
        quality_results = evaluate_quality(
            fundamentals,
            market_confidence=market_confidence,
            banned_symbols=context.get("banned_symbols", []),
        )
        reports.append(
            {
                "phase": "PHASE_03",
                "passed": len([res for res in quality_results.values() if res.passed]),
                "failed": len([res for res in quality_results.values() if not res.passed]),
            }
        )

        economics = compute_economics(fundamentals)
        reports.append(
            {
                "phase": "PHASE_04",
                "symbols": len(economics),
            }
        )

        intrinsic_values = estimate_intrinsic_values(economics)
        reports.append(
            {
                "phase": "PHASE_05",
                "symbols": len(intrinsic_values),
            }
        )

        mos_results, focus_entries = rank_by_margin_of_safety(
            intrinsic_values=intrinsic_values,
            quality=quality_results,
            economics=economics,
            price_snapshots=context.get("price_snapshots", {}),
        )
        reports.append(
            {
                "phase": "PHASE_06",
                "focus": len(focus_entries),
                "watchlist": len([res for res in mos_results if res.state == "WATCHLIST"]),
            }
        )

        available_allocation = float(
            context.get("available_allocation_pct") or strategy_policy.MAX_NEW_ALLOCATION_PCT
        )
        portfolio_plan = build_portfolio_plan(
            focus_entries,
            available_allocation_pct=available_allocation,
        )
        reports.append(
            {
                "phase": "PHASE_07",
                "buy_ready": len(portfolio_plan.buy_ready),
                "blocked": len(portfolio_plan.blocked),
                "total_target_pct": portfolio_plan.total_target_pct,
            }
        )

        trade_intents = build_trade_intents(
            focus_entries,
            portfolio_plan,
            mode=mode,
            require_manual_approval=bool(context.get("require_manual_approval")),
        )
        reports.append(
            {
                "phase": "PHASE_08",
                "intents": len(trade_intents),
                "intent_symbols": [intent.symbol for intent in trade_intents],
            }
        )

        cadence_label = str(context.get("monitoring_cadence") or cadence.MONTHLY_REFRESH)
        monitoring_reports = build_monitoring_reports(
            focus_entries,
            cadence_label=cadence_label,
        )
        reports.append(
            {
                "phase": "PHASE_09",
                "monitoring": len(monitoring_reports),
            }
        )

        dividend_report = build_dividend_report(
            fundamentals,
            reinvestment_enabled=config.DIVIDEND_REINVESTMENT_ENABLED,
        )
        reports.append(
            {
                "phase": "PHASE_10",
                "dividends": len(dividend_report.events),
                "reinvestment": dividend_report.reinvestment_enabled,
            }
        )

        if not context.get("disable_storage"):
            persist_artifact(
                run_id=run_id,
                name="universe_snapshot",
                payload=asdict(universe_snapshot),
            )
            persist_artifact(
                run_id=run_id,
                name="fundamentals_summary",
                payload={"symbols": list(fundamentals.records.keys())},
            )
            persist_artifact(
                run_id=run_id,
                name="quality_results",
                payload={
                    symbol: asdict(result) for symbol, result in quality_results.items()
                },
            )
            persist_artifact(
                run_id=run_id,
                name="margin_of_safety",
                payload=mos_results_for_report(mos_results),
            )
            persist_artifact(
                run_id=run_id,
                name="focus_list",
                payload=focus_entries_for_report(focus_entries),
            )
            persist_artifact(
                run_id=run_id,
                name="portfolio_plan",
                payload=asdict(portfolio_plan),
            )
            persist_artifact(
                run_id=run_id,
                name="monitoring_report",
                payload=[asdict(report) for report in monitoring_reports],
            )
            persist_artifact(
                run_id=run_id,
                name="dividend_report",
                payload=asdict(dividend_report),
            )

        metrics.update(
            {
                "symbols": len(universe_snapshot.symbols),
                "focus": len(focus_entries),
                "watchlist": len([res for res in mos_results if res.state == "WATCHLIST"]),
                "intents": len(trade_intents),
            }
        )

        return {
            "trade_intents": trade_intents,
            "reports": reports,
            "metrics": metrics,
        }
