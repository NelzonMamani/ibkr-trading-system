from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os

from src.learning.models import LearningDataset
from src.learning.policy_proposal import propose_policy, validate_policy_schema
from src.learning.reporting import (
    build_daily_report,
    build_summary_text,
    build_trade_reviews,
    filter_trades_for_range,
    trade_from_row,
)
from src.learning.storage import LearningRunRecord, LearningStorage, compute_hash, parse_json_field
from src.strategies.ross_momentum.strategy_policy import RossMomentumPolicy


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Parallel learning CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    report = sub.add_parser("report", help="Generate report for a specific date.")
    report.add_argument("--date", required=True, help="YYYY-MM-DD")
    report.add_argument("--strategy", default="ROSS_MOMENTUM")
    report.add_argument(
        "--type",
        default="DAILY",
        choices=["DAILY", "WEEKLY", "MONTHLY", "YEARLY"],
        help="Report type",
    )

    propose = sub.add_parser("propose-policy", help="Generate policy proposal.")
    propose.add_argument("--strategy", default="ROSS_MOMENTUM")
    propose.add_argument("--min-trades", type=int, default=30)

    summarise = sub.add_parser("summarise", help="Summarise latest reports.")
    summarise.add_argument("--last", type=int, default=5)
    summarise.add_argument("--strategy", default=None)

    backfill = sub.add_parser("backfill", help="Backfill daily reports.")
    backfill.add_argument("--from", dest="start_date", required=True)
    backfill.add_argument("--to", dest="end_date", required=True)
    backfill.add_argument("--strategy", default="ROSS_MOMENTUM")

    list_props = sub.add_parser("list-proposals", help="List policy proposals.")
    list_props.add_argument("--strategy", default=None)

    show_prop = sub.add_parser("show-proposal", help="Show proposal details.")
    show_prop.add_argument("--id", required=True)

    approve = sub.add_parser("approve", help="Approve proposal.")
    approve.add_argument("--id", required=True)
    approve.add_argument("--by", required=True)

    reject = sub.add_parser("reject", help="Reject proposal.")
    reject.add_argument("--id", required=True)
    reject.add_argument("--reason", required=True)

    return parser.parse_args()


def _write_report_files(strategy: str, asof_date: str, report: dict, report_type: str) -> None:
    dt = datetime.strptime(asof_date, "%Y-%m-%d")
    year = dt.strftime("%Y")
    month = dt.strftime("%m")
    base_dir = os.path.join("data", "reports", strategy, year, month)
    os.makedirs(base_dir, exist_ok=True)
    suffix = report_type.lower()
    json_path = os.path.join(base_dir, f"{asof_date}_{suffix}.json")
    md_path = os.path.join(base_dir, f"{asof_date}_{suffix}.md")
    with open(json_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
    summary_text = build_summary_text(report)
    with open(md_path, "w", encoding="utf-8") as handle:
        handle.write(f"# Daily Report {asof_date}\n\n")
        handle.write(f"Strategy: {strategy}\n\n")
        handle.write(summary_text + "\n")


def _handle_report(args: argparse.Namespace) -> None:
    storage = LearningStorage()
    trades_raw = storage.fetch_trade_outcomes(strategy_name=args.strategy)
    trades = [trade_from_row(row) for row in trades_raw]
    start_date, end_date = _resolve_period_range(args.date, args.type)
    trades = filter_trades_for_range(trades, start_date, end_date)
    dataset = LearningDataset(trades=trades)
    reviews = build_trade_reviews(trades)
    watchlists = storage.fetch_watchlists(strategy_name=args.strategy)
    report = build_daily_report(
        asof_date=args.date,
        strategy_name=args.strategy,
        dataset=dataset,
        watchlists=watchlists,
        trade_reviews=reviews,
        report_type=args.type,
    )
    summary_text = build_summary_text(report)
    run_id = compute_hash({"strategy": args.strategy, "date": args.date})
    storage.insert_learning_run(
        LearningRunRecord(
            run_id=run_id,
            started_at_utc=datetime.now(timezone.utc).isoformat(),
            completed_at_utc=datetime.now(timezone.utc).isoformat(),
            ok=True,
            error=None,
            strategy_name=args.strategy,
            window_start_utc=None,
            window_end_utc=None,
            inputs_hash=compute_hash({"strategy": args.strategy, "date": args.date}),
            outputs_hash=compute_hash(report),
        )
    )
    storage.insert_learning_report(
        run_id=run_id,
        report_type=args.type,
        asof_date_ny=args.date,
        strategy_name=args.strategy,
        payload=report,
        summary_text=summary_text,
    )
    _write_report_files(args.strategy, args.date, report, args.type)
    print(f"[LEARNING][REPORT] Generated {args.type.lower()} report")
    print(summary_text)
    storage.close()


def _handle_propose(args: argparse.Namespace) -> None:
    storage = LearningStorage()
    trades_raw = storage.fetch_trade_outcomes(strategy_name=args.strategy)
    trades = [trade_from_row(row) for row in trades_raw]
    dataset = LearningDataset(trades=trades)
    baseline = RossMomentumPolicy()
    proposal, diff, rationale = propose_policy(
        baseline=baseline, dataset=dataset, min_trades=args.min_trades
    )
    if proposal is None:
        print("[LEARNING][PROPOSAL] Insufficient trades; no proposal generated.")
        storage.close()
        return
    if not validate_policy_schema(asdict_like(baseline), proposal):
        raise RuntimeError("Proposal schema does not match baseline policy.")
    proposal_id = storage.insert_policy_proposal(
        strategy_name=args.strategy,
        baseline_policy_version=baseline.version,
        min_trades_required=args.min_trades,
        trades_used=dataset.trade_count(),
        proposal=proposal,
        diff=diff,
        rationale=rationale,
    )
    print(f"[LEARNING][PROPOSAL] Created proposal id={proposal_id}")
    storage.close()


def asdict_like(policy: RossMomentumPolicy) -> dict:
    return json.loads(json.dumps(policy, default=lambda o: o.__dict__))


def _handle_summarise(args: argparse.Namespace) -> None:
    storage = LearningStorage()
    reports = storage.list_reports(strategy_name=args.strategy, limit=args.last)
    for report in reports:
        summary = report.get("summary_text")
        date = report.get("asof_date_ny")
        print(f"{date}: {summary}")
    storage.close()


def _handle_backfill(args: argparse.Namespace) -> None:
    start = datetime.strptime(args.start_date, "%Y-%m-%d")
    end = datetime.strptime(args.end_date, "%Y-%m-%d")
    storage = LearningStorage()
    current = start
    while current <= end:
        date_str = current.strftime("%Y-%m-%d")
        trades_raw = storage.fetch_trade_outcomes(strategy_name=args.strategy)
        trades = [trade_from_row(row) for row in trades_raw]
        trades = filter_trades_for_range(trades, date_str, date_str)
        if trades:
            dataset = LearningDataset(trades=trades)
            reviews = build_trade_reviews(trades)
            watchlists = storage.fetch_watchlists(strategy_name=args.strategy)
            report = build_daily_report(
                asof_date=date_str,
                strategy_name=args.strategy,
                dataset=dataset,
                watchlists=watchlists,
                trade_reviews=reviews,
            )
            _write_report_files(args.strategy, date_str, report, "DAILY")
            storage.insert_learning_report(
                run_id=compute_hash({"strategy": args.strategy, "date": date_str}),
                report_type="DAILY",
                asof_date_ny=date_str,
                strategy_name=args.strategy,
                payload=report,
                summary_text=build_summary_text(report),
            )
            print(f"[LEARNING][BACKFILL] Generated report for {date_str}")
        current += timedelta(days=1)
    storage.close()


def _handle_list_proposals(args: argparse.Namespace) -> None:
    storage = LearningStorage()
    proposals = storage.list_policy_proposals(strategy_name=args.strategy)
    for proposal in proposals:
        print(
            f"{proposal.get('proposal_id')} "
            f"status={proposal.get('status')} "
            f"created_at={proposal.get('created_at_utc')}"
        )
    storage.close()


def _handle_show_proposal(args: argparse.Namespace) -> None:
    storage = LearningStorage()
    proposal = storage.fetch_policy_proposal(args.id)
    if not proposal:
        print("Proposal not found.")
        storage.close()
        return
    proposal["proposal_json"] = parse_json_field(proposal.get("proposal_json"))
    proposal["diff_json"] = parse_json_field(proposal.get("diff_json"))
    proposal["rationale_json"] = parse_json_field(proposal.get("rationale_json"))
    print(json.dumps(proposal, indent=2, sort_keys=True))
    storage.close()


def _handle_approve(args: argparse.Namespace) -> None:
    storage = LearningStorage()
    storage.update_policy_proposal(args.id, status="APPROVED", approved_by=args.by)
    print(f"[LEARNING][PROPOSAL] Approved {args.id}")
    storage.close()


def _handle_reject(args: argparse.Namespace) -> None:
    storage = LearningStorage()
    storage.update_policy_proposal(
        args.id, status="REJECTED", rejection_reason=args.reason
    )
    print(f"[LEARNING][PROPOSAL] Rejected {args.id}")
    storage.close()


def main() -> None:
    args = _parse_args()
    if args.command == "report":
        _handle_report(args)
    elif args.command == "propose-policy":
        _handle_propose(args)
    elif args.command == "summarise":
        _handle_summarise(args)
    elif args.command == "backfill":
        _handle_backfill(args)
    elif args.command == "list-proposals":
        _handle_list_proposals(args)
    elif args.command == "show-proposal":
        _handle_show_proposal(args)
    elif args.command == "approve":
        _handle_approve(args)
    elif args.command == "reject":
        _handle_reject(args)


def _resolve_period_range(date_str: str, report_type: str) -> tuple[str, str]:
    target = datetime.strptime(date_str, "%Y-%m-%d")
    if report_type == "DAILY":
        return date_str, date_str
    if report_type == "WEEKLY":
        start = target - timedelta(days=target.weekday())
        end = start + timedelta(days=6)
        return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
    if report_type == "MONTHLY":
        start = target.replace(day=1)
        next_month = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
        end = next_month - timedelta(days=1)
        return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
    if report_type == "YEARLY":
        start = target.replace(month=1, day=1)
        end = target.replace(month=12, day=31)
        return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
    return date_str, date_str


if __name__ == "__main__":
    main()
