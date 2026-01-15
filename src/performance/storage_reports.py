from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import os
from typing import Any, Iterable

from src.storage.sqlite_store import SQLiteStore


@dataclass(frozen=True)
class ReportArtifacts:
    json_path: str
    text_path: str


def generate_reports_from_storage(
    store: SQLiteStore,
    run_id: str,
    report_type: str,
    *,
    output_dir: str = "output/reports",
) -> ReportArtifacts:
    report_type = report_type.lower()
    if report_type not in {"daily", "weekly", "cumulative"}:
        raise ValueError(f"Unsupported report type: {report_type}")

    run = store.fetch_run(run_id)
    run_started = (run or {}).get("started_at_utc") or (run or {}).get("started_at")
    run_date = _run_date_label(run_started)
    output_base = os.path.join(
        output_dir,
        f"{report_type}_{run_date}_run_{run_id}",
    )
    os.makedirs(output_dir, exist_ok=True)

    trades = _normalize_trade_outcomes(store.fetch_trade_outcomes(run_id))
    latest_snapshot = _latest_snapshot(store.fetch_performance_snapshots(run_id))

    summary = _summarize_trades(trades)
    payload: dict[str, Any] = {
        "run_id": run_id,
        "report_type": report_type,
        "generated_from": "storage",
        "as_of": run_started,
        "summary": summary,
        "by_strategy": _build_buckets(trades, "strategy_name"),
        "by_trader_type": _build_buckets(trades, "trader_type"),
        "exit_category_distribution": _exit_category_distribution(latest_snapshot),
        "rule_adherence": _rule_adherence(latest_snapshot),
    }

    if report_type in {"daily", "weekly"}:
        payload["periods"] = _grouped_report(trades, report_type)

    json_path = f"{output_base}.json"
    text_path = f"{output_base}.txt"
    with open(json_path, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    with open(text_path, "w", encoding="utf-8") as handle:
        handle.write(_format_summary_text(report_type.upper(), summary))
    return ReportArtifacts(json_path=json_path, text_path=text_path)


def _run_date_label(run_started: str | None) -> str:
    if not run_started:
        return "unknown"
    try:
        return datetime.fromisoformat(run_started).date().isoformat()
    except ValueError:
        return "unknown"


def _normalize_trade_outcomes(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    trades: list[dict[str, Any]] = []
    for row in rows:
        trades.append(
            {
                "symbol": row.get("symbol") or "UNKNOWN",
                "trader_type": row.get("trader_type") or "UNKNOWN",
                "strategy_name": row.get("strategy_name") or "UNKNOWN",
                "gross_realised_pnl": float(row.get("gross_realised_pnl") or 0.0),
                "commission": float(row.get("commission") or 0.0),
                "net_realised_pnl": float(row.get("net_realised_pnl") or 0.0),
                "outcome": row.get("outcome") or "UNKNOWN",
                "closed_at": row.get("closed_at"),
            }
        )
    return trades


def _latest_snapshot(rows: Iterable[dict[str, Any]]) -> dict[str, Any] | None:
    snapshots = list(rows)
    if not snapshots:
        return None
    latest = snapshots[-1]
    payload_json = latest.get("payload_json")
    if not payload_json:
        return None
    try:
        return json.loads(payload_json)
    except json.JSONDecodeError:
        return None


def _summarize_trades(trades: list[dict[str, Any]]) -> dict[str, float | int]:
    total = len(trades)
    wins = sum(1 for trade in trades if trade.get("outcome") == "WIN")
    losses = sum(1 for trade in trades if trade.get("outcome") == "LOSS")
    flats = sum(1 for trade in trades if trade.get("outcome") == "FLAT")
    gross_pnl = sum(trade.get("gross_realised_pnl", 0.0) for trade in trades)
    total_commissions = sum(trade.get("commission", 0.0) for trade in trades)
    net_pnl = sum(trade.get("net_realised_pnl", 0.0) for trade in trades)
    win_rate = (wins / total) if total else 0.0
    avg_pnl = (net_pnl / total) if total else 0.0
    return {
        "total_trades": total,
        "wins": wins,
        "losses": losses,
        "flats": flats,
        "win_rate": win_rate,
        "gross_pnl": gross_pnl,
        "total_commissions": total_commissions,
        "net_pnl": net_pnl,
        "avg_pnl_per_trade": avg_pnl,
    }


def _build_buckets(trades: list[dict[str, Any]], key: str) -> dict[str, dict[str, float | int]]:
    buckets: dict[str, dict[str, float | int]] = {}
    for trade in trades:
        bucket_key = trade.get(key, "UNKNOWN")
        bucket = buckets.setdefault(
            bucket_key,
            {
                "total_trades": 0,
                "wins": 0,
                "losses": 0,
                "flats": 0,
                "gross_pnl": 0.0,
                "total_commissions": 0.0,
                "net_pnl": 0.0,
                "win_rate": 0.0,
                "avg_pnl_per_trade": 0.0,
            },
        )
        bucket["total_trades"] += 1
        bucket["gross_pnl"] += trade.get("gross_realised_pnl", 0.0)
        bucket["total_commissions"] += trade.get("commission", 0.0)
        bucket["net_pnl"] += trade.get("net_realised_pnl", 0.0)
        outcome = trade.get("outcome")
        if outcome == "WIN":
            bucket["wins"] += 1
        elif outcome == "LOSS":
            bucket["losses"] += 1
        elif outcome == "FLAT":
            bucket["flats"] += 1
    for bucket in buckets.values():
        total = bucket["total_trades"]
        bucket["win_rate"] = (bucket["wins"] / total) if total else 0.0
        bucket["avg_pnl_per_trade"] = (bucket["net_pnl"] / total) if total else 0.0
    return buckets


def _grouped_report(trades: list[dict[str, Any]], period: str) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for trade in trades:
        timestamp = trade.get("closed_at")
        if not timestamp:
            continue
        try:
            trade_dt = datetime.fromisoformat(timestamp)
        except ValueError:
            continue
        if period == "daily":
            key = trade_dt.date().isoformat()
        else:
            iso_year, iso_week, _ = trade_dt.isocalendar()
            key = f"{iso_year}-W{iso_week:02d}"
        grouped.setdefault(key, []).append(trade)
    report: dict[str, dict[str, Any]] = {}
    for key, group_trades in sorted(grouped.items()):
        summary = _summarize_trades(group_trades)
        report[key] = {
            "summary": summary,
            "summary_text": _format_summary_text(key, summary),
        }
    return report


def _format_summary_text(label: str, summary: dict[str, float | int]) -> str:
    return (
        f"{label} | total={summary['total_trades']} "
        f"wins={summary['wins']} losses={summary['losses']} "
        f"flats={summary['flats']} win_rate={summary['win_rate']:.2f} "
        f"net_pnl={summary['net_pnl']:.2f} avg_pnl={summary['avg_pnl_per_trade']:.2f}"
    )


def _exit_category_distribution(snapshot: dict[str, Any] | None) -> dict[str, int]:
    if not snapshot:
        return {}
    outcomes = snapshot.get("trade_outcomes")
    if not isinstance(outcomes, list):
        return {}
    distribution: dict[str, int] = {}
    for trade in outcomes:
        if not isinstance(trade, dict):
            continue
        category = trade.get("exit_category", "UNKNOWN")
        distribution[category] = distribution.get(category, 0) + 1
    return distribution


def _rule_adherence(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    if not snapshot:
        return {}
    rule_adherence = snapshot.get("rule_adherence")
    return rule_adherence if isinstance(rule_adherence, dict) else {}
