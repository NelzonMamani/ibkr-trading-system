from __future__ import annotations

import importlib.abc
import importlib.machinery
import sys
from datetime import datetime, timezone
from typing import Any

from src.core.time.trading_windows import TradingWindowDecision

_INSTALLED = False
_LAST_MANUAL_FOCUS_SYMBOLS: list[str] = []


def _normalize_symbol(value: Any) -> str:
    return str(value or "").strip().upper()


def _candidate_field(candidate: Any, name: str, default: Any = None) -> Any:
    if isinstance(candidate, dict):
        return candidate.get(name, default)
    return getattr(candidate, name, default)


def _is_manual_focus_candidate(candidate: Any) -> bool:
    promotion_reason = str(_candidate_field(candidate, "promotion_reason") or "").strip().lower()
    watchlist_source = str(_candidate_field(candidate, "watchlist_source") or "").strip().lower()
    return promotion_reason == "manual_focus" or "manual" in watchlist_source


def _patch_orchestrator_module(module) -> None:
    global _LAST_MANUAL_FOCUS_SYMBOLS

    cls = module.CoreOrchestrator
    if getattr(cls, "_codex_pr1024_manual_focus_patch", False):
        return

    def _manual_focus_candidate(symbol: str, session_phase: str):
        phase = str(session_phase or "PRE").strip().upper() or "PRE"
        return module.CandidateMetrics(
            symbol=symbol,
            con_id=None,
            exchange=None,
            session_label=phase,
            session_phase=phase,
            last_price=None,
            prev_close=None,
            ref_close_rth=None,
            reference_price=None,
            reference_label=None,
            reference_source=None,
            reference_quality_tier=None,
            reference_resolved=None,
            gap_pct=None,
            pct_change=None,
            pct_change_resolved=None,
            pct_change_qualification_usable=None,
            pct_change_execution_usable=None,
            pct_change_source_quality=None,
            pct_change_degraded=None,
            pct_change_synthetic=None,
            pct_change_failure_reason=None,
            gap_pct_resolved=None,
            gap_source=None,
            context_status=None,
            execution_ready=None,
            prep_only=None,
            live_rvol_deferred=None,
            prep_seeded=None,
            live_confirmation_pending=None,
            watchlist_source="MANUAL_FOCUS",
            promotion_reason="manual_focus",
            ibkr_change_pct=None,
            pct_source=None,
            open_relative_pct_change=None,
            hod_pct=None,
            rvol=None,
            rvol_discovery=None,
            rvol_phase=None,
            phase_volume_ratio=None,
            relative_volume=None,
            avg_volume_20d=None,
            adv20_resolved=None,
            degraded_adv20=None,
            adv20_source=None,
            rvol_status=None,
            rvol_failure_reason=None,
            rvol_degraded=None,
            rvol_qualification_usable=None,
            rvol_execution_usable=None,
            degraded_rvol_gate_bypass=None,
            float_shares=None,
            float_source=None,
            float_asof=None,
            float_cache_hit=None,
            float_millions=None,
            volume=None,
            premarket_volume=None,
            dollar_volume=None,
            bid=None,
            ask=None,
            spread=None,
            spread_pct=None,
            halted=None,
            ssr=None,
            catalyst_present=None,
            catalyst_summary=None,
            news_count=None,
            fresh_news_count=None,
            stale_news_count=None,
            top_news_title=None,
            top_news_age_hours=None,
            top_news_catalyst_tag=None,
            news_source_mode=None,
            news_asof=None,
            data_quality_ok=True,
            eligibility_reason_codes=[
                "USER_SELECTED_SYMBOL",
                "MANUAL_BYPASS_PRICE_FILTER",
                "MANUAL_BYPASS_FLOAT_FILTER",
                "MANUAL_BYPASS_RVOL_FILTER",
                "MANUAL_BYPASS_CATALYST_FILTER",
            ],
            data_quality_flags=[],
            drop_reasons=[],
            rank_score=None,
            rank_components=None,
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            gate_checks={
                "stock_selection_bypass": True,
                "auto_selection_required": False,
                "setup_detection_required": True,
                "risk_required": True,
                "execution_required": True,
            },
            selection_rationale={
                "source": "MANUAL_FOCUS",
                "stock_selection_bypass": True,
                "setup_detection_required": True,
                "risk_required": True,
                "execution_required": True,
            },
        )

    def _resolve_manual_focus_candidates(self, manual_symbols: list[str], session_phase: str):
        global _LAST_MANUAL_FOCUS_SYMBOLS

        accepted = []
        rejected = []
        seen: set[str] = set()
        for raw_symbol in manual_symbols:
            symbol = _normalize_symbol(raw_symbol)
            if symbol in seen:
                continue
            seen.add(symbol)
            rejection_reason = self._manual_focus_rejection_reason(symbol)
            if rejection_reason:
                print(f"[MANUAL_FOCUS][REJECT] symbol={symbol or '<EMPTY>'} reason={rejection_reason}")
                print(
                    "[ROSS][MANUAL_FOCUS_AUTHORITY] "
                    f"symbol={symbol or '<EMPTY>'} accepted=false stock_selection_bypass=true "
                    f"setup_detection_required=true reason={rejection_reason}"
                )
                rejected.append((symbol, rejection_reason))
                continue
            print(
                "[MANUAL_FOCUS][ACCEPT] "
                f"symbol={symbol} reason=USER_SELECTED_WATCH_CANDIDATE "
                "stock_selection_bypass=True setup_detection_required=True"
            )
            print(
                "[ROSS][MANUAL_FOCUS_AUTHORITY] "
                f"symbol={symbol} accepted=true stock_selection_bypass=true setup_detection_required=true"
            )
            accepted.append(_manual_focus_candidate(symbol, session_phase))
        _LAST_MANUAL_FOCUS_SYMBOLS = [row.symbol for row in accepted]
        return accepted, rejected

    def _resolve_tha_decisions(self, *, strategy_inputs, now_utc):
        decisions = {}
        for candidate in strategy_inputs or []:
            symbol = _normalize_symbol(_candidate_field(candidate, "symbol"))
            if not symbol:
                continue
            trading_hours = (
                _candidate_field(candidate, "trading_hours")
                or _candidate_field(candidate, "ibkr_trading_hours")
            )
            liquid_hours = (
                _candidate_field(candidate, "liquid_hours")
                or _candidate_field(candidate, "ibkr_liquid_hours")
            )
            timezone_id = (
                _candidate_field(candidate, "timeZoneId")
                or _candidate_field(candidate, "timezone")
                or _candidate_field(candidate, "timezone_id")
            )
            if _is_manual_focus_candidate(candidate) and not trading_hours and not liquid_hours:
                session_token = str(
                    _candidate_field(candidate, "session_label")
                    or _candidate_field(candidate, "session_phase")
                    or ""
                ).strip().upper()
                allow_entries = cls._session_execution_allowed(session_token)
                tha_decision = TradingWindowDecision(
                    symbol=symbol,
                    source="MANUAL_FOCUS_SESSION_FALLBACK",
                    in_window=allow_entries,
                    allow_entries=allow_entries,
                    force_flat=not allow_entries,
                )
                decisions[symbol] = tha_decision
                print(
                    "[THA][SOURCE] "
                    f"symbol={symbol} source=MANUAL_FOCUS_SESSION_FALLBACK segments=1"
                )
                print(
                    "[PIPELINE][THA_GATE] "
                    f"symbol={symbol} in_window={tha_decision.in_window} "
                    f"allow_entries={tha_decision.allow_entries} force_flat={tha_decision.force_flat}"
                )
                continue
            policy = module.build_trading_window_policy(
                symbol=symbol,
                now=now_utc,
                run_mode=self.run_mode.value,
                trading_hours=trading_hours,
                liquid_hours=liquid_hours,
                timezone=timezone_id,
            )
            print(
                module.format_tha_source_log(
                    symbol=symbol,
                    source=policy.source,
                    segments=policy.segments,
                )
            )
            tha_decision = module.resolve_trading_window_decision(policy=policy, now=now_utc)
            if tha_decision.in_window and not tha_decision.allow_entries:
                raise RuntimeError("THA contradiction: inside window but entries blocked")
            decisions[symbol] = tha_decision
            print(
                "[PIPELINE][THA_GATE] "
                f"symbol={symbol} in_window={tha_decision.in_window} "
                f"allow_entries={tha_decision.allow_entries} force_flat={tha_decision.force_flat}"
            )
        return decisions

    cls._manual_focus_candidate = staticmethod(_manual_focus_candidate)
    cls._resolve_manual_focus_candidates = _resolve_manual_focus_candidates
    cls._resolve_tha_decisions = _resolve_tha_decisions
    cls._codex_pr1024_manual_focus_patch = True


def _patch_strategy_runner_module(module) -> None:
    cls = module.StrategyRunner
    if getattr(cls, "_codex_pr1024_manual_focus_patch", False):
        return

    original_process = cls.process

    def process(
        self,
        *,
        strategy_key: str,
        watchlist,
        snapshots,
        session_label: str,
        timestamp_utc: str,
        mode,
        session_phase: str,
        execution_allowed=None,
        execution_ready=None,
        prep_only=None,
    ):
        snapshot_symbols = {
            _normalize_symbol(symbol)
            for symbol in getattr(self, "last_watchlist_symbols", [])
            if _normalize_symbol(symbol)
        }
        manual_symbols = [
            symbol for symbol in _LAST_MANUAL_FOCUS_SYMBOLS if symbol in snapshot_symbols
        ]
        resolved_execution_allowed = True if execution_allowed is None else bool(execution_allowed)
        resolved_prep_only = bool(prep_only) if prep_only is not None else False
        if (
            str(strategy_key or "").strip().lower() == "ross_momentum"
            and not list(watchlist or [])
            and manual_symbols
        ):
            ross_strategy = next(
                (
                    strategy
                    for strategy in getattr(self, "strategies", [])
                    if getattr(strategy, "name", "") == "RossMomentumStrategyV1"
                ),
                None,
            )
            if ross_strategy is not None:
                ross_strategy.last_evaluated_symbols = list(manual_symbols)
            reason = (
                "MARKET_NOT_EXECUTABLE_BUT_USER_WATCH_ACCEPTED"
                if (resolved_prep_only or not resolved_execution_allowed)
                else "NO_RUNTIME_CANDIDATE_FOR_MANUAL_FOCUS"
            )
            session_token = str(session_label or session_phase or "UNKNOWN").strip().upper() or "UNKNOWN"
            for symbol in manual_symbols:
                if reason == "MARKET_NOT_EXECUTABLE_BUT_USER_WATCH_ACCEPTED":
                    print(
                        "[MANUAL_FOCUS][PREP_ONLY] "
                        f"symbol={symbol} session={session_token} reason={reason}"
                    )
                print(f"[MANUAL_FOCUS][REJECT] symbol={symbol} reason={reason}")
                print(f"[ROSS][MANUAL_FOCUS_NO_SETUP] symbol={symbol} reason={reason}")
            return []
        return original_process(
            self,
            strategy_key=strategy_key,
            watchlist=watchlist,
            snapshots=snapshots,
            session_label=session_label,
            timestamp_utc=timestamp_utc,
            mode=mode,
            session_phase=session_phase,
            execution_allowed=execution_allowed,
            execution_ready=execution_ready,
            prep_only=prep_only,
        )

    cls.process = process
    cls._codex_pr1024_manual_focus_patch = True


def _patch_ross_strategy_module(module) -> None:
    cls = module.RossMomentumStrategyV1
    if getattr(cls, "_codex_pr1024_manual_focus_patch", False):
        return

    original_process_watchlist = cls.process_watchlist

    def process_watchlist(
        self,
        *,
        watchlist,
        snapshots,
        session_label: str,
        timestamp_utc: str,
        mode,
        session_phase: str,
    ):
        manual_symbols: list[str] = []
        seen: set[str] = set()
        for row in list(watchlist or []):
            symbol = _normalize_symbol(_candidate_field(row, "symbol"))
            if not symbol:
                continue
            if module.infer_symbol_source(row) != "manual_focus" or symbol in seen:
                continue
            seen.add(symbol)
            manual_symbols.append(symbol)
            print(
                "[MANUAL_FOCUS][REVALIDATE] "
                f"symbol={symbol} reason=SESSION_NOW_EXECUTABLE_CHECK_SETUP"
            )
            print(
                "[ROSS][EVALUATION_SOURCE] "
                f"symbol={symbol} source=MANUAL_FOCUS path=USER_SELECTED_TO_SETUP_EVAL"
            )
        intents = original_process_watchlist(
            self,
            watchlist=watchlist,
            snapshots=snapshots,
            session_label=session_label,
            timestamp_utc=timestamp_utc,
            mode=mode,
            session_phase=session_phase,
        )
        intents_by_symbol = {
            _normalize_symbol(getattr(intent, "symbol", None)): intent
            for intent in (intents or [])
            if _normalize_symbol(getattr(intent, "symbol", None))
        }
        for symbol in manual_symbols:
            intent = intents_by_symbol.get(symbol)
            if intent is not None:
                print(
                    "[ROSS][MANUAL_FOCUS_SETUP_READY] "
                    f"symbol={symbol} setup={getattr(intent, 'pattern_name', None) or getattr(intent, 'setup_family_id', None) or 'UNKNOWN'} "
                    f"trigger={getattr(intent, 'trigger_id', None) or 'UNKNOWN'}"
                )
            else:
                print(f"[ROSS][MANUAL_FOCUS_NO_SETUP] symbol={symbol} reason=NO_VALID_SETUP")
        return intents

    cls.process_watchlist = process_watchlist
    cls._codex_pr1024_manual_focus_patch = True


class _PatchLoader(importlib.abc.Loader):
    def __init__(self, original_loader, patcher) -> None:
        self._original_loader = original_loader
        self._patcher = patcher

    def create_module(self, spec):
        create_module = getattr(self._original_loader, "create_module", None)
        if callable(create_module):
            return create_module(spec)
        return None

    def exec_module(self, module) -> None:
        self._original_loader.exec_module(module)
        self._patcher(module)


class _PatchFinder(importlib.abc.MetaPathFinder):
    _targets = {
        "src.core.orchestrator": _patch_orchestrator_module,
        "src.strategy.strategy_runner": _patch_strategy_runner_module,
        "src.strategies.ross_momentum_strategy_v1": _patch_ross_strategy_module,
    }

    def find_spec(self, fullname, path, target=None):
        patcher = self._targets.get(fullname)
        if patcher is None:
            return None
        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if spec is None or spec.loader is None:
            return None
        if isinstance(spec.loader, _PatchLoader):
            return spec
        spec.loader = _PatchLoader(spec.loader, patcher)
        return spec


def install() -> None:
    global _INSTALLED

    if _INSTALLED:
        return

    finder = _PatchFinder()
    sys.meta_path.insert(0, finder)
    for fullname, patcher in finder._targets.items():
        module = sys.modules.get(fullname)
        if module is not None:
            patcher(module)
    _INSTALLED = True
