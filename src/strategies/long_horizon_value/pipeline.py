"""Phase pipeline implementation for Long Horizon Value strategy."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict
from pathlib import Path
from statistics import mean, pstdev
from typing import Dict, Iterable, List, Mapping, Sequence

from src.config.runtime_config import RunMode
from src.models.data_models import TradeIntent
from src.strategies.long_horizon_value import config, strategy_policy
from src.strategies.long_horizon_value.contracts.dividends import (
    DividendEvent,
    DividendReport,
)
from src.strategies.long_horizon_value.contracts.economics import EconomicsProfile
from src.strategies.long_horizon_value.contracts.fundamentals import (
    DataQualityFlags,
    FundamentalsDataset,
    FundamentalsRecord,
    FundamentalsSeries,
)
from src.strategies.long_horizon_value.contracts.intrinsic_value import (
    IntrinsicValueRange,
    SensitivityPoint,
)
from src.strategies.long_horizon_value.contracts.monitoring import MonitoringReport
from src.strategies.long_horizon_value.contracts.portfolio import PortfolioPlan
from src.strategies.long_horizon_value.contracts.quality import QualityGateResult
from src.strategies.long_horizon_value.contracts.ranking import (
    FocusEntry,
    MarginOfSafetyResult,
)
from src.strategies.long_horizon_value.contracts.types import SymbolRef
from src.strategies.long_horizon_value.contracts.universe import UniverseSnapshot


def _stable_int(value: str, salt: str = "") -> int:
    digest = hashlib.sha256(f"{value}:{salt}".encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def _series_growth(base: float, growth: float, periods: int) -> List[float]:
    return [round(base * ((1 + growth) ** idx), 2) for idx in range(periods)]


def _default_symbol_ref(symbol: str) -> SymbolRef:
    return SymbolRef(symbol=symbol, exchange="SMART", currency="USD", country="US")


def discover_universe(context: Mapping[str, object]) -> UniverseSnapshot:
    mode = str(context.get("input_mode") or config.INPUT_MODE)
    timestamp_utc = str(context.get("timestamp_utc") or "")
    symbols: List[SymbolRef] = []
    counts_by_market: Dict[str, int] = {}
    if mode == "MANUAL_SYMBOL_LIST":
        manual_symbols = list(
            dict.fromkeys(
                context.get("manual_symbols")
                or config.MANUAL_SYMBOL_LIST
                or context.get("watchlist_symbols")
                or []
            )
        )
        symbols = [_default_symbol_ref(symbol) for symbol in manual_symbols]
        counts_by_market = {"MANUAL": len(symbols)}
    else:
        market_map: Dict[str, Sequence[str]] = {
            key: tuple(context.get("market_symbols", {}).get(key, []))
            for key in config.MARKET_PRIORITY_ORDER
        }
        for market in config.MARKET_PRIORITY_ORDER:
            market_symbols = list(dict.fromkeys(market_map.get(market, [])))
            counts_by_market[market] = len(market_symbols)
            symbols.extend(_default_symbol_ref(symbol) for symbol in market_symbols)
    symbols = sorted(symbols, key=lambda ref: ref.symbol)
    return UniverseSnapshot(
        mode=mode,
        symbols=symbols,
        counts_by_market=counts_by_market,
        timestamp_utc=timestamp_utc,
    )


def _cache_path(run_id: str, symbol: str) -> Path:
    cache_dir = Path("data") / "cache" / "long_horizon_value"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{run_id}_{symbol}_fundamentals_v2.json"


def _build_fundamentals_series(symbol: str, as_of_year: int) -> FundamentalsSeries:
    seed = _stable_int(symbol)
    base_revenue = 500 + (seed % 500)
    growth = 0.03 + ((seed % 5) / 100)
    years = list(range(as_of_year - 9, as_of_year + 1))
    revenue = _series_growth(base_revenue, growth, len(years))
    operating_cashflow = [round(value * 0.2, 2) for value in revenue]
    capex = [round(value * 0.05, 2) for value in revenue]
    net_debt_to_ebitda = round(2.0 + ((seed % 5) / 10), 2)
    interest_coverage = round(5.0 + ((seed % 20) / 10), 2)
    shares_outstanding = round(100 + (seed % 200), 2)
    dividends = [round(value * 0.01, 2) for value in revenue[-3:]]
    return FundamentalsSeries(
        years=years,
        revenue=revenue,
        operating_cashflow=operating_cashflow,
        capex=capex,
        net_debt_to_ebitda=net_debt_to_ebitda,
        interest_coverage=interest_coverage,
        shares_outstanding=shares_outstanding,
        dividends=dividends,
    )


def assemble_fundamentals(
    symbols: Sequence[SymbolRef],
    *,
    run_id: str,
    as_of_year: int,
    missing_symbols: Iterable[str] = (),
) -> FundamentalsDataset:
    records: Dict[str, FundamentalsRecord] = {}
    cache_hits: List[str] = []
    missing_set = set(missing_symbols)
    for ref in symbols:
        cache_path = _cache_path(run_id, ref.symbol)
        if cache_path.exists():
            with cache_path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            series = FundamentalsSeries(**payload["series"])
            data_quality = DataQualityFlags(flags=list(payload.get("flags", [])))
            cache_hits.append(ref.symbol)
        else:
            series = _build_fundamentals_series(ref.symbol, as_of_year)
            flags: List[str] = []
            if ref.symbol in missing_set:
                flags.append("missing_financials")
            if len(series.years) < strategy_policy.MIN_OPERATING_YEARS:
                flags.append("insufficient_history")
            data_quality = DataQualityFlags(flags=flags)
            payload = {"series": asdict(series), "flags": list(data_quality.flags)}
            with cache_path.open("w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
        records[ref.symbol] = FundamentalsRecord(
            symbol=ref.symbol,
            currency=ref.currency,
            series=series,
            data_quality=data_quality,
        )
    return FundamentalsDataset(records=records, generated_at=str(run_id), cache_hits=cache_hits)


def evaluate_quality(
    fundamentals: FundamentalsDataset,
    *,
    market_confidence: Mapping[str, str],
    banned_symbols: Iterable[str] = (),
) -> Dict[str, QualityGateResult]:
    banned_set = set(banned_symbols)
    results: Dict[str, QualityGateResult] = {}
    for symbol, record in fundamentals.records.items():
        reasons: List[str] = []
        if symbol in banned_set:
            reasons.append("banned_symbol")
        if not record.data_quality.ok:
            reasons.extend(record.data_quality.flags)
        if record.series.interest_coverage < strategy_policy.MIN_INTEREST_COVERAGE:
            reasons.append("low_interest_coverage")
        if record.series.net_debt_to_ebitda > strategy_policy.MAX_NET_DEBT_TO_EBITDA:
            reasons.append("high_leverage")
        years = len(record.series.years)
        if years < strategy_policy.MIN_OPERATING_YEARS:
            reasons.append("insufficient_operating_history")
        quality_score = max(
            0.0,
            min(
                100.0,
                50.0
                + (record.series.interest_coverage * 2)
                - (record.series.net_debt_to_ebitda * 5)
                + (years - strategy_policy.MIN_OPERATING_YEARS) * 2,
            ),
        )
        confidence = market_confidence.get(symbol, "MEDIUM")
        passed = not reasons
        results[symbol] = QualityGateResult(
            symbol=symbol,
            passed=passed,
            reasons=reasons,
            quality_score=round(quality_score, 2),
            market_confidence=confidence,
        )
    return results


def compute_economics(fundamentals: FundamentalsDataset) -> Dict[str, EconomicsProfile]:
    profiles: Dict[str, EconomicsProfile] = {}
    for symbol, record in fundamentals.records.items():
        series = record.series
        owner_earnings: List[float] = []
        for ocf, capex, revenue in zip(
            series.operating_cashflow,
            series.capex,
            series.revenue,
        ):
            working_capital_adj = revenue * 0.02
            owner_earnings.append(round(ocf - capex - working_capital_adj, 2))
        positive_years = len([value for value in owner_earnings if value > 0])
        negative_years = len(owner_earnings) - positive_years
        avg = mean(owner_earnings) if owner_earnings else 0.0
        volatility = pstdev(owner_earnings) if len(owner_earnings) > 1 else 0.0
        stability = 0.0 if avg <= 0 else max(0.0, 1 - (volatility / abs(avg)))
        reinvestment_rate = 0.0 if avg <= 0 else max(0.0, min(1.0, series.capex[-1] / avg))
        profiles[symbol] = EconomicsProfile(
            symbol=symbol,
            owner_earnings=owner_earnings,
            reinvestment_rate=round(reinvestment_rate, 3),
            stability_score=round(stability * 100, 2),
            negative_years=negative_years,
        )
    return profiles


def estimate_intrinsic_values(
    economics: Mapping[str, EconomicsProfile],
) -> Dict[str, IntrinsicValueRange]:
    results: Dict[str, IntrinsicValueRange] = {}
    for symbol, profile in economics.items():
        base_earnings = mean(profile.owner_earnings[-5:]) if profile.owner_earnings else 0.0
        conservative_multiple = 10
        multiple_value = base_earnings * conservative_multiple
        growth_rates = [0.01, 0.02, 0.03]
        discount_rates = [0.08, 0.1, 0.12]
        sensitivity: List[SensitivityPoint] = []
        dcf_values: List[float] = []
        for growth in growth_rates:
            for discount in discount_rates:
                if discount <= growth:
                    continue
                terminal = base_earnings * (1 + growth) / (discount - growth)
                sensitivity.append(
                    SensitivityPoint(
                        growth=growth,
                        discount=discount,
                        value=round(terminal, 2),
                    )
                )
                dcf_values.append(terminal)
        dcf_base = mean(dcf_values) if dcf_values else 0.0
        low = min(multiple_value, dcf_base)
        high = max(multiple_value, dcf_base)
        base = (low + high) / 2 if (low or high) else 0.0
        results[symbol] = IntrinsicValueRange(
            symbol=symbol,
            low=round(low, 2),
            base=round(base, 2),
            high=round(high, 2),
            method_notes="earnings_multiple + conservative_dcf",
            sensitivity=sensitivity,
        )
    return results


def _snapshot_price(snapshot: object) -> float | None:
    if snapshot is None:
        return None
    for attr in ("last", "ask", "bid"):
        value = getattr(snapshot, attr, None)
        if value:
            return float(value)
    return None


def _synthetic_price(symbol: str) -> float:
    seed = _stable_int(symbol, "price")
    return round(20 + (seed % 180) + ((seed % 17) / 10), 2)


def rank_by_margin_of_safety(
    *,
    intrinsic_values: Mapping[str, IntrinsicValueRange],
    quality: Mapping[str, QualityGateResult],
    economics: Mapping[str, EconomicsProfile],
    price_snapshots: Mapping[str, object],
) -> tuple[List[MarginOfSafetyResult], List[FocusEntry]]:
    results: List[MarginOfSafetyResult] = []
    focus_entries: List[FocusEntry] = []
    for symbol, intrinsic in intrinsic_values.items():
        price = _snapshot_price(price_snapshots.get(symbol)) or _synthetic_price(symbol)
        mos = (
            (intrinsic.base - price) / intrinsic.base
            if intrinsic.base > 0
            else -1.0
        )
        quality_result = quality[symbol]
        required_mos = strategy_policy.required_margin_of_safety(
            quality_result.market_confidence
        )
        state = "WATCHLIST"
        reasons: List[str] = []
        if not quality_result.passed:
            state = "NO"
            reasons.extend(quality_result.reasons)
        elif mos >= required_mos:
            state = "FOCUS"
        else:
            state = "WATCHLIST"
            reasons.append("waiting_for_price")
        results.append(
            MarginOfSafetyResult(
                symbol=symbol,
                price=round(price, 2),
                intrinsic_base=intrinsic.base,
                margin_of_safety=round(mos, 4),
                required_margin_of_safety=round(required_mos, 4),
                state=state,
                reasons=reasons,
                quality_score=quality_result.quality_score,
                stability_score=economics[symbol].stability_score,
                market_confidence=quality_result.market_confidence,
            )
        )
    ranked_focus = sorted(
        [entry for entry in results if entry.state == "FOCUS"],
        key=lambda entry: (
            -entry.margin_of_safety,
            -entry.quality_score,
            -entry.stability_score,
            entry.symbol,
        ),
    )
    for idx, entry in enumerate(ranked_focus, start=1):
        focus_entries.append(
            FocusEntry(
                symbol=entry.symbol,
                priority=idx,
                target_pct=0.0,
                margin_of_safety=entry.margin_of_safety,
                confidence=round(min(1.0, entry.quality_score / 100), 2),
                checklist_summary=[
                    f"quality_score={entry.quality_score}",
                    f"stability_score={entry.stability_score}",
                    f"mos={entry.margin_of_safety}",
                ],
                max_price=entry.intrinsic_base,
                state="FOCUS",
            )
        )
    return results, focus_entries


def build_portfolio_plan(
    focus_entries: List[FocusEntry],
    *,
    available_allocation_pct: float,
) -> PortfolioPlan:
    allocations: Dict[str, float] = {}
    buy_ready: List[str] = []
    blocked: List[str] = []
    notes: List[str] = []
    if not focus_entries:
        return PortfolioPlan(allocations=allocations, total_target_pct=0.0, buy_ready=[], blocked=[], notes=[])
    base_target = min(
        strategy_policy.MAX_SINGLE_POSITION_PCT,
        strategy_policy.MAX_NEW_ALLOCATION_PCT,
        1.0 / len(focus_entries),
    )
    remaining = available_allocation_pct
    for entry in focus_entries:
        target = min(base_target, remaining)
        allocations[entry.symbol] = round(target, 4)
        if remaining >= target and target > 0:
            buy_ready.append(entry.symbol)
            remaining = max(0.0, remaining - target)
        else:
            blocked.append(entry.symbol)
    if blocked:
        notes.append("capital_constrained")
    total_target = round(sum(allocations.values()), 4)
    return PortfolioPlan(
        allocations=allocations,
        total_target_pct=total_target,
        buy_ready=buy_ready,
        blocked=blocked,
        notes=notes,
    )


def build_trade_intents(
    focus_entries: List[FocusEntry],
    plan: PortfolioPlan,
    *,
    mode: RunMode,
    require_manual_approval: bool,
) -> List[TradeIntent]:
    intents: List[TradeIntent] = []
    for entry in focus_entries:
        target_pct = plan.allocations.get(entry.symbol, 0.0)
        state = "FOCUS"
        if entry.symbol in plan.buy_ready:
            state = "BUY_READY"
        elif entry.symbol in plan.blocked:
            state = "BLOCKED_CAPITAL"
        entry.target_pct = target_pct
        entry.state = state
        if state == "BUY_READY":
            intent_state = "READY"
            if require_manual_approval or mode in {RunMode.LIVE_READ_ONLY, RunMode.LIVE_MICRO}:
                intent_state = "AWAITING_APPROVAL"
            intents.append(
                TradeIntent(
                    symbol=entry.symbol,
                    direction="LONG",
                    strategy_name="LongHorizonValue",
                    confidence=entry.confidence,
                    rationale=(
                        f"LHV intent state={intent_state} target_pct={target_pct} "
                        f"max_price={entry.max_price} mos={entry.margin_of_safety}"
                    ),
                    trader_type="VALUE",
                )
            )
    return intents


def build_monitoring_reports(
    focus_entries: List[FocusEntry],
    *,
    cadence_label: str,
) -> List[MonitoringReport]:
    reports: List[MonitoringReport] = []
    for entry in focus_entries:
        reports.append(
            MonitoringReport(
                symbol=entry.symbol,
                action="HOLD",
                reasons=[f"cadence={cadence_label}", "quality_ok"],
            )
        )
    return reports


def build_dividend_report(
    fundamentals: FundamentalsDataset,
    *,
    reinvestment_enabled: bool,
) -> DividendReport:
    events: List[DividendEvent] = []
    for symbol, record in fundamentals.records.items():
        if not record.series.dividends:
            continue
        events.append(
            DividendEvent(
                symbol=symbol,
                amount=record.series.dividends[-1],
                currency=record.currency,
                date="TBD",
            )
        )
    notes = ["reinvestment_enabled" if reinvestment_enabled else "reinvestment_disabled"]
    return DividendReport(events=events, reinvestment_enabled=reinvestment_enabled, notes=notes)


def focus_entries_for_report(entries: Sequence[FocusEntry]) -> List[Dict[str, object]]:
    return [
        {
            "symbol": entry.symbol,
            "priority": entry.priority,
            "target_pct": entry.target_pct,
            "margin_of_safety": entry.margin_of_safety,
            "confidence": entry.confidence,
            "state": entry.state,
            "blocked_reason": entry.blocked_reason,
        }
        for entry in entries
    ]


def mos_results_for_report(results: Sequence[MarginOfSafetyResult]) -> List[Dict[str, object]]:
    return [
        {
            "symbol": entry.symbol,
            "state": entry.state,
            "margin_of_safety": entry.margin_of_safety,
            "required_margin_of_safety": entry.required_margin_of_safety,
            "reasons": entry.reasons,
        }
        for entry in results
    ]
