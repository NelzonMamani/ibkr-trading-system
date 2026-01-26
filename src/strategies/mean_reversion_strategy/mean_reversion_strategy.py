#!/usr/bin/env python3
"""
mean_reversion_strategy_policy.py

Authoritative Mean Reversion Strategy Policy (decision brain)

Key architectural rule:
- Scanner supplies measurements only (facts).
- This policy consumes measurements and decides: trade / no-trade.
- Orchestrator manages lifecycle + scheduling + wiring (NOT decision logic).
- Risk engine is a veto/constraint layer (global + strategy-specific).

This file is deliberately:
- Extensive and explicit
- Deterministic and explainable
- Safe by default (no-trade unless high-confidence gates pass)

You will likely integrate this into your repo under something like:
  src/strategies/mean_reversion/mean_reversion_strategy_policy.py
or keep the filename as-is and import it via your strategy registry.

No external dependencies required beyond stdlib.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Protocol, Tuple
import math
import time


# =============================================================================
# 1) Core Types (minimal contracts; adapt to your project's canonical types)
# =============================================================================

class Side(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"


class TimeInForce(str, Enum):
    DAY = "DAY"
    IOC = "IOC"
    GTC = "GTC"


@dataclass(frozen=True)
class PolicyDecision:
    """
    Primary output of this policy per symbol per cycle.
    """
    allowed: bool
    symbol: str
    reason: str
    setup: Optional[str] = None
    intent: Optional["TradeIntent"] = None
    diagnostics: Dict[str, float] = field(default_factory=dict)
    tags: Dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class TradeIntent:
    """
    What the strategy wants to do (subject to risk-engine + execution acceptance).
    """
    symbol: str
    side: Side

    entry_type: OrderType
    entry_price: Optional[float]  # None for MARKET
    tif: TimeInForce = TimeInForce.DAY

    stop_price: float = 0.0
    target_price: float = 0.0

    # "Risk as $", not shares. Risk sizing is typically done by risk engine.
    # If your system sizes here, add qty/shares; otherwise keep as constraints.
    max_risk_usd: float = 0.0

    # Explanations for auditability
    thesis: str = ""
    notes: str = ""

    created_ts: float = field(default_factory=lambda: time.time())


# =============================================================================
# 2) Inputs from Scanner / Market State (facts, not decisions)
# =============================================================================

@dataclass(frozen=True)
class ScannerFacts:
    """
    Facts provided by the scanner. These must be strategy-agnostic measurements.
    The scanner MUST NOT label setups or decide trades.
    """
    symbol: str

    # Live-ish price
    last: float

    # Means / references
    vwap: Optional[float]
    ema9: Optional[float]
    ema20: Optional[float]

    # Volatility / scaling
    atr: Optional[float]  # ATR in $ (not %)

    # Simple price action context (from scanner or lightweight local calc)
    hod: Optional[float] = None
    lod: Optional[float] = None

    # Microstructure / tape surrogates (optional)
    spread: Optional[float] = None

    # Derived measurements (scanner can provide directly)
    dist_from_vwap: Optional[float] = None      # last - vwap
    dist_from_ema9: Optional[float] = None      # last - ema9
    dist_from_ema20: Optional[float] = None     # last - ema20

    # Momentum/participation proxies (pure facts)
    rvol: Optional[float] = None
    impulse_strength: Optional[float] = None     # e.g., last X bars range / ATR

    # Exhaustion / failure markers as facts (not decisions)
    volume_deceleration_flag: bool = False
    failed_breakout_up_flag: bool = False
    failed_breakout_down_flag: bool = False
    rejection_wick_up_flag: bool = False
    rejection_wick_down_flag: bool = False

    # News / catalyst presence (facts)
    has_fresh_news: bool = False
    halt_flag: bool = False
    ssr_flag: bool = False

    # Market session facts
    is_rth: bool = True
    minutes_since_open: Optional[int] = None

    # Optional slope proxies (scanner can compute a simple recent VWAP slope)
    vwap_slope: Optional[float] = None  # $ per minute (signed)


@dataclass(frozen=True)
class MarketRegimeFacts:
    """
    Global context facts (from market module / index tracker).
    Policy consumes them and decides 'permission'.
    """
    # Broad index trend proxies (facts)
    spy_trending_up: bool = False
    spy_trending_down: bool = False
    qqq_trending_up: bool = False
    qqq_trending_down: bool = False

    # Volatility regime (facts)
    high_volatility_day: bool = False

    # News / event regime (facts)
    major_macro_event_window: bool = False


# =============================================================================
# 3) Risk/Execution integration points (Protocols, adapt to your system)
# =============================================================================

class RiskEngine(Protocol):
    """
    Strategy policy produces an intent; risk engine can veto/modify (in your system).
    Here, we only model veto capability as an example.
    """
    def validate_intent(self, intent: TradeIntent, regime: MarketRegimeFacts) -> Tuple[bool, str]:
        ...


# =============================================================================
# 4) Configuration (all tunables live here)
# =============================================================================

@dataclass(frozen=True)
class MeanReversionPolicyConfig:
    """
    Strategy policy config.
    Defaults are conservative; tune per your governance and backtests.

    Units:
    - distances are in ATR multiples or in absolute $ using atr.
    """
    # -----------------------
    # Core "mean" definitions
    # -----------------------
    primary_mean: str = "VWAP"   # "VWAP" or "EMA20" etc.
    allow_secondary_means: bool = True

    # -----------------------
    # Overextension thresholds
    # -----------------------
    min_atr_required: float = 0.05  # $; if ATR absent or too small, skip
    min_ext_atr: float = 1.2        # overextension threshold in ATR multiples
    max_ext_atr: float = 4.0        # beyond this, treat as unstable / skip unless special case

    # -----------------------
    # Exhaustion requirements
    # -----------------------
    require_exhaustion: bool = True
    require_failure_marker: bool = True  # requires at least one "failure" fact flag
    require_volume_deceleration: bool = False  # optional hardening

    # -----------------------
    # Liquidity / tradability
    # -----------------------
    max_spread_pct: float = 0.008   # 0.8% of price; very conservative for small caps
    require_hod_lod: bool = False   # if you want break/fail logic to rely on HOD/LOD

    # -----------------------
    # Regime permission gates
    # -----------------------
    forbid_on_fresh_news: bool = True
    forbid_on_halt: bool = True
    forbid_on_macro_event_window: bool = True

    # Trend-day veto: if broad indices show strong trend, disable mean reversion
    forbid_on_index_trend: bool = True

    # VWAP slope veto: if VWAP is strongly sloped, reversion is lower quality
    max_abs_vwap_slope_atr_per_min: float = 0.05  # slope in ATR/min; above => veto

    # Time-of-day gating (typical mean reversion is better after initial chaos)
    min_minutes_since_open: int = 5
    max_minutes_since_open: int = 360  # 6 hours (RTH); adjust as needed

    # -----------------------
    # Entry & risk shaping
    # -----------------------
    # Stop buffer: add a small buffer beyond structural invalidation
    stop_buffer_atr: float = 0.15

    # Targets: default is "mean touch" minus a small cushion
    target_cushion_atr: float = 0.10

    # Risk asymmetry requirements
    min_rr: float = 1.2           # require at least this R:R (target_distance / stop_distance)
    max_stop_atr: float = 1.0     # if stop larger than this, skip

    # Strategy-level daily protections (enforced here as an extra belt; risk engine should also enforce)
    max_trades_per_symbol_per_day: int = 2
    max_consecutive_losses: int = 2  # require external tracking to enforce fully

    # -----------------------
    # Setup enablement
    # -----------------------
    enable_vwap_extension_snapback: bool = True
    enable_ema_stretch_reversion: bool = True
    enable_failed_breakout_reversion: bool = True
    enable_exhaustion_spike_time_reversion: bool = True


# =============================================================================
# 5) Setup identifiers
# =============================================================================

class SetupName(str, Enum):
    VWAP_EXTENSION_SNAPBACK = "VWAP_EXTENSION_SNAPBACK"
    EMA_STRETCH_REVERSION = "EMA_STRETCH_REVERSION"
    FAILED_BREAKOUT_REVERSION = "FAILED_BREAKOUT_REVERSION"
    EXHAUSTION_SPIKE_TIME_REVERSION = "EXHAUSTION_SPIKE_TIME_REVERSION"


# =============================================================================
# 6) Mean Reversion Strategy Policy (the decision brain)
# =============================================================================

class MeanReversionStrategyPolicy:
    """
    This class is the "pilot" for mean reversion.

    Inputs:
    - ScannerFacts per symbol
    - MarketRegimeFacts (global)
    - Optional risk engine hook

    Output:
    - PolicyDecision (trade intent or explicit no-trade reason)
    """

    def __init__(self, cfg: MeanReversionPolicyConfig, risk_engine: Optional[RiskEngine] = None):
        self.cfg = cfg
        self.risk_engine = risk_engine

        # Minimal state: you will likely replace with your canonical storage module.
        # Used only to enforce "max trades per symbol/day" if you wire it.
        self._symbol_trade_counts: Dict[str, int] = {}

    # -----------------------
    # Public API
    # -----------------------

    def evaluate_symbol(self, facts: ScannerFacts, regime: MarketRegimeFacts) -> PolicyDecision:
        """
        Single-symbol evaluation. Deterministic. Explainable.

        This function encodes the 8-condition contract:
        1) Clear overextension
        2) Verified exhaustion
        3) Defined, relevant mean
        4) Structural entry
        5) Hard stop
        6) Predefined target
        7) Regime permission
        8) Risk asymmetry
        """
        # 0) Basic sanity
        if not facts.symbol or facts.last <= 0:
            return self._deny(facts, "INVALID_PRICE_OR_SYMBOL")

        # 7) Regime permission (early veto)
        ok, reason = self._regime_permission(facts, regime)
        if not ok:
            return self._deny(facts, reason)

        # Minimal liquidity sanity
        ok, reason = self._liquidity_gate(facts)
        if not ok:
            return self._deny(facts, reason)

        # Enforce minimal ATR availability
        atr = facts.atr
        if atr is None or atr < self.cfg.min_atr_required:
            return self._deny(facts, "NO_VALID_ATR")

        # Trade frequency guard (optional, stateful)
        if self._symbol_trade_counts.get(facts.symbol, 0) >= self.cfg.max_trades_per_symbol_per_day:
            return self._deny(facts, "MAX_TRADES_PER_SYMBOL_REACHED")

        # 3) Define a valid mean (primary, optionally secondary)
        mean_price, mean_name = self._select_mean(facts)
        if mean_price is None or mean_price <= 0:
            return self._deny(facts, "NO_VALID_MEAN_REFERENCE")

        # 1) Clear overextension (distance from mean)
        ext_atr = self._extension_atr(facts.last, mean_price, atr)
        if ext_atr < self.cfg.min_ext_atr:
            return self._deny(
                facts,
                "NOT_OVEREXTENDED",
                diagnostics={"ext_atr": ext_atr, "atr": atr, "mean": mean_price},
                tags={"mean": mean_name},
            )
        if ext_atr > self.cfg.max_ext_atr:
            return self._deny(
                facts,
                "EXTENSION_TOO_EXTREME_UNSTABLE",
                diagnostics={"ext_atr": ext_atr, "atr": atr, "mean": mean_price},
                tags={"mean": mean_name},
            )

        # Determine direction: if price above mean => look for SHORT reversion; below mean => LONG
        side = Side.SHORT if facts.last > mean_price else Side.LONG

        # 2) Verified exhaustion (requires at least one failure marker)
        ok, reason, exhaustion_score = self._exhaustion_gate(facts, side)
        if not ok:
            return self._deny(
                facts,
                reason,
                diagnostics={"ext_atr": ext_atr, "exhaustion_score": exhaustion_score},
                tags={"mean": mean_name, "side": side.value},
            )

        # Choose setup type (optional but useful for audit and later tuning)
        setup = self._classify_setup(facts, side, mean_name)

        # 4) Structural entry (confirmation-based)
        entry_type, entry_price, entry_reason = self._structural_entry(facts, side, atr, setup)
        if entry_type is None:
            return self._deny(
                facts,
                "NO_STRUCTURAL_ENTRY",
                diagnostics={"ext_atr": ext_atr, "exhaustion_score": exhaustion_score},
                tags={"mean": mean_name, "side": side.value, "setup": setup},
            )

        # 5) Hard stop (structural invalidation)
        stop_price = self._compute_stop(facts, side, atr, setup)
        if stop_price <= 0:
            return self._deny(facts, "INVALID_STOP_PRICE")

        # Stop sanity: stop distance must be bounded
        stop_dist = abs((facts.last if entry_price is None else entry_price) - stop_price)
        stop_atr = stop_dist / atr if atr > 0 else math.inf
        if stop_atr > self.cfg.max_stop_atr:
            return self._deny(
                facts,
                "STOP_TOO_WIDE",
                diagnostics={"stop_atr": stop_atr, "stop_dist": stop_dist, "atr": atr},
                tags={"mean": mean_name, "side": side.value, "setup": setup},
            )

        # 6) Predefined target (the mean, with cushion)
        target_price = self._compute_target(mean_price, side, atr)
        if target_price <= 0:
            return self._deny(facts, "INVALID_TARGET_PRICE")

        # 8) Risk asymmetry (R:R)
        target_dist = abs(target_price - (facts.last if entry_price is None else entry_price))
        rr = (target_dist / stop_dist) if stop_dist > 0 else 0.0
        if rr < self.cfg.min_rr:
            return self._deny(
                facts,
                "INSUFFICIENT_RR",
                diagnostics={"rr": rr, "stop_dist": stop_dist, "target_dist": target_dist},
                tags={"mean": mean_name, "side": side.value, "setup": setup},
            )

        # Build trade intent (sizing is typically handled by risk engine)
        intent = TradeIntent(
            symbol=facts.symbol,
            side=side,
            entry_type=entry_type,
            entry_price=entry_price,
            stop_price=stop_price,
            target_price=target_price,
            max_risk_usd=0.0,  # Let risk engine size; set if you want a cap here
            thesis=f"Mean reversion toward {mean_name}: overextension={ext_atr:.2f} ATR; exhaustion_score={exhaustion_score:.2f}",
            notes=f"{setup} | {entry_reason}",
        )

        # Risk engine veto (optional)
        if self.risk_engine is not None:
            ok, veto_reason = self.risk_engine.validate_intent(intent, regime)
            if not ok:
                return self._deny(
                    facts,
                    f"RISK_ENGINE_VETO:{veto_reason}",
                    diagnostics={"rr": rr, "ext_atr": ext_atr, "exhaustion_score": exhaustion_score},
                    tags={"mean": mean_name, "side": side.value, "setup": setup},
                )

        # Mark trade count (optional state; production should be persisted)
        self._symbol_trade_counts[facts.symbol] = self._symbol_trade_counts.get(facts.symbol, 0) + 1

        return PolicyDecision(
            allowed=True,
            symbol=facts.symbol,
            reason="APPROVED",
            setup=setup,
            intent=intent,
            diagnostics={
                "ext_atr": ext_atr,
                "exhaustion_score": exhaustion_score,
                "rr": rr,
                "stop_atr": stop_atr,
            },
            tags={"mean": mean_name, "side": side.value, "setup": setup},
        )

    # =============================================================================
    # 7) Regime permission gates
    # =============================================================================

    def _regime_permission(self, facts: ScannerFacts, regime: MarketRegimeFacts) -> Tuple[bool, str]:
        # Session window
        if facts.minutes_since_open is not None:
            if facts.minutes_since_open < self.cfg.min_minutes_since_open:
                return False, "TOO_EARLY_AFTER_OPEN"
            if facts.minutes_since_open > self.cfg.max_minutes_since_open:
                return False, "TOO_LATE_IN_SESSION"

        # News / halts
        if self.cfg.forbid_on_halt and facts.halt_flag:
            return False, "HALT_FLAG"
        if self.cfg.forbid_on_fresh_news and facts.has_fresh_news:
            return False, "FRESH_NEWS_REGIME_VETO"

        # Macro window
        if self.cfg.forbid_on_macro_event_window and regime.major_macro_event_window:
            return False, "MACRO_EVENT_WINDOW_VETO"

        # Index trend veto
        if self.cfg.forbid_on_index_trend:
            if regime.spy_trending_up or regime.spy_trending_down or regime.qqq_trending_up or regime.qqq_trending_down:
                return False, "INDEX_TREND_DAY_VETO"

        # VWAP slope veto (if we have slope + ATR)
        if facts.vwap_slope is not None and facts.atr is not None and facts.atr > 0:
            slope_atr_per_min = abs(facts.vwap_slope) / facts.atr
            if slope_atr_per_min > self.cfg.max_abs_vwap_slope_atr_per_min:
                return False, "VWAP_SLOPE_VETO"

        return True, "OK"

    # =============================================================================
    # 8) Liquidity gates
    # =============================================================================

    def _liquidity_gate(self, facts: ScannerFacts) -> Tuple[bool, str]:
        if facts.spread is None or facts.spread <= 0:
            # If spread unknown, allow but annotate; you can hard-gate if preferred
            return True, "OK_SPREAD_UNKNOWN"

        spread_pct = facts.spread / facts.last if facts.last > 0 else math.inf
        if spread_pct > self.cfg.max_spread_pct:
            return False, "SPREAD_TOO_WIDE"
        return True, "OK"

    # =============================================================================
    # 9) Mean selection (valid, relevant mean)
    # =============================================================================

    def _select_mean(self, facts: ScannerFacts) -> Tuple[Optional[float], str]:
        """
        Select the 'mean' reference price.

        Policy rule:
        - Prefer VWAP if present and primary_mean == VWAP
        - Otherwise EMA20 (or EMA9) as a micro mean
        """
        if self.cfg.primary_mean.upper() == "VWAP":
            if facts.vwap is not None and facts.vwap > 0:
                return facts.vwap, "VWAP"
            if self.cfg.allow_secondary_means:
                if facts.ema20 is not None and facts.ema20 > 0:
                    return facts.ema20, "EMA20"
                if facts.ema9 is not None and facts.ema9 > 0:
                    return facts.ema9, "EMA9"
            return None, "NONE"

        if self.cfg.primary_mean.upper() == "EMA20":
            if facts.ema20 is not None and facts.ema20 > 0:
                return facts.ema20, "EMA20"
            if self.cfg.allow_secondary_means and facts.vwap is not None and facts.vwap > 0:
                return facts.vwap, "VWAP"
            return None, "NONE"

        if self.cfg.primary_mean.upper() == "EMA9":
            if facts.ema9 is not None and facts.ema9 > 0:
                return facts.ema9, "EMA9"
            if self.cfg.allow_secondary_means and facts.vwap is not None and facts.vwap > 0:
                return facts.vwap, "VWAP"
            return None, "NONE"

        # Unknown mean type
        return None, "NONE"

    # =============================================================================
    # 10) Overextension
    # =============================================================================

    @staticmethod
    def _extension_atr(price: float, mean: float, atr: float) -> float:
        if atr <= 0:
            return 0.0
        return abs(price - mean) / atr

    # =============================================================================
    # 11) Exhaustion gate (verified exhaustion)
    # =============================================================================

    def _exhaustion_gate(self, facts: ScannerFacts, side: Side) -> Tuple[bool, str, float]:
        """
        Exhaustion is treated as a score composed of evidence flags.
        This keeps the policy explainable and tunable.
        """
        score = 0.0
        reasons: List[str] = []

        # Volume deceleration
        if facts.volume_deceleration_flag:
            score += 1.0
        else:
            reasons.append("NO_VOLUME_DECELERATION")

        # Rejection wicks aligned with expected reversal direction
        if side == Side.SHORT:
            if facts.rejection_wick_up_flag:
                score += 1.0
            else:
                reasons.append("NO_UP_REJECTION_WICK")
        else:
            if facts.rejection_wick_down_flag:
                score += 1.0
            else:
                reasons.append("NO_DOWN_REJECTION_WICK")

        # Failed breakout markers (either direction can support exhaustion, but prefer aligned)
        fb_aligned = False
        if side == Side.SHORT and facts.failed_breakout_up_flag:
            fb_aligned = True
        if side == Side.LONG and facts.failed_breakout_down_flag:
            fb_aligned = True

        if fb_aligned:
            score += 1.0
        else:
            # Still accept other failure evidence; this is not always present
            reasons.append("NO_ALIGNED_FAILED_BREAKOUT")

        # Enforce exhaustion requirements
        if not self.cfg.require_exhaustion:
            return True, "OK", score

        if self.cfg.require_volume_deceleration and not facts.volume_deceleration_flag:
            return False, "EXHAUSTION_FAIL:VOLUME_DECELERATION_REQUIRED", score

        if self.cfg.require_failure_marker:
            # Require at least one of: wick rejection or failed breakout (aligned), plus optionally volume decel
            has_failure = (
                (facts.rejection_wick_up_flag if side == Side.SHORT else facts.rejection_wick_down_flag)
                or fb_aligned
            )
            if not has_failure:
                return False, "EXHAUSTION_FAIL:NO_FAILURE_MARKER", score

        # Minimal threshold: at least 1.0 score recommended
        if score < 1.0:
            return False, "EXHAUSTION_FAIL:INSUFFICIENT_EVIDENCE", score

        return True, "OK", score

    # =============================================================================
    # 12) Setup classification (for auditability, not required for correctness)
    # =============================================================================

    def _classify_setup(self, facts: ScannerFacts, side: Side, mean_name: str) -> str:
        # Failed breakout is highest confidence if aligned markers exist
        if self.cfg.enable_failed_breakout_reversion:
            if side == Side.SHORT and facts.failed_breakout_up_flag:
                return SetupName.FAILED_BREAKOUT_REVERSION.value
            if side == Side.LONG and facts.failed_breakout_down_flag:
                return SetupName.FAILED_BREAKOUT_REVERSION.value

        # VWAP extension snapback
        if self.cfg.enable_vwap_extension_snapback and mean_name == "VWAP":
            return SetupName.VWAP_EXTENSION_SNAPBACK.value

        # EMA stretch
        if self.cfg.enable_ema_stretch_reversion and mean_name in {"EMA9", "EMA20"}:
            return SetupName.EMA_STRETCH_REVERSION.value

        # Exhaustion spike / time reversion
        if self.cfg.enable_exhaustion_spike_time_reversion and facts.volume_deceleration_flag:
            return SetupName.EXHAUSTION_SPIKE_TIME_REVERSION.value

        # Default fallback label (still valid)
        return "GENERIC_MEAN_REVERSION"

    # =============================================================================
    # 13) Structural entry
    # =============================================================================

    def _structural_entry(
        self, facts: ScannerFacts, side: Side, atr: float, setup: str
    ) -> Tuple[Optional[OrderType], Optional[float], str]:
        """
        Mean reversion entries are confirmation-based:
        - Prefer limit entries after rejection/failure
        - Avoid market chasing by default

        This policy uses facts flags (wick rejection, failed breakout, volume decel)
        and constructs a conservative entry suggestion.
        """
        # If we have an aligned failed breakout marker, we can accept a market entry (fast trap unwind).
        if setup == SetupName.FAILED_BREAKOUT_REVERSION.value:
            return OrderType.MARKET, None, "FAILED_BREAKOUT_CONFIRMATION"

        # If we have rejection wick, prefer a limit entry slightly better than last (avoid chasing)
        if side == Side.SHORT and facts.rejection_wick_up_flag:
            # short: try to sell slightly below last (pullback from spike)
            entry = max(facts.last - 0.05 * atr, 0.01)
            return OrderType.LIMIT, entry, "UP_REJECTION_WICK_LIMIT_ENTRY"
        if side == Side.LONG and facts.rejection_wick_down_flag:
            entry = max(facts.last - 0.05 * atr, 0.01)  # long: buy a touch lower if possible
            return OrderType.LIMIT, entry, "DOWN_REJECTION_WICK_LIMIT_ENTRY"

        # If only volume deceleration is present, require more conservative entry (limit)
        if facts.volume_deceleration_flag:
            entry = max(facts.last - (0.10 * atr if side == Side.LONG else 0.05 * atr), 0.01)
            return OrderType.LIMIT, entry, "VOLUME_DECELERATION_LIMIT_ENTRY"

        # No structural confirmation
        return None, None, "NO_CONFIRMATION"

    # =============================================================================
    # 14) Hard stop computation
    # =============================================================================

    def _compute_stop(self, facts: ScannerFacts, side: Side, atr: float, setup: str) -> float:
        """
        Stops are structural invalidation points.

        Conservative structural rules:
        - If HOD/LOD exists, use it (plus buffer).
        - Otherwise, use last ± buffer*ATR as a fallback (still bounded).
        """
        buf = self.cfg.stop_buffer_atr * atr

        if side == Side.SHORT:
            # Invalidate if price makes meaningfully higher highs (use HOD if known)
            if facts.hod is not None and facts.hod > 0:
                return facts.hod + buf
            return facts.last + buf

        # LONG
        if facts.lod is not None and facts.lod > 0:
            return max(facts.lod - buf, 0.01)
        return max(facts.last - buf, 0.01)

    # =============================================================================
    # 15) Target computation (predefined target)
    # =============================================================================

    def _compute_target(self, mean_price: float, side: Side, atr: float) -> float:
        """
        Target is the mean with a cushion (avoid requiring perfect touch).
        For SHORT reversion (price above mean), target is slightly ABOVE mean.
        For LONG reversion (price below mean), target is slightly BELOW mean.
        """
        cushion = self.cfg.target_cushion_atr * atr

        if side == Side.SHORT:
            # target down toward mean; take profit a bit above the mean
            return max(mean_price + cushion, 0.01)

        # LONG
        return max(mean_price - cushion, 0.01)

    # =============================================================================
    # 16) Helpers
    # =============================================================================

    def _deny(
        self,
        facts: ScannerFacts,
        reason: str,
        diagnostics: Optional[Dict[str, float]] = None,
        tags: Optional[Dict[str, str]] = None,
    ) -> PolicyDecision:
        return PolicyDecision(
            allowed=False,
            symbol=facts.symbol if facts.symbol else "UNKNOWN",
            reason=reason,
            diagnostics=diagnostics or {},
            tags=tags or {},
        )


# =============================================================================
# 17) Example usage (for local sanity checks)
# =============================================================================

def _example():
    cfg = MeanReversionPolicyConfig()
    policy = MeanReversionStrategyPolicy(cfg=cfg, risk_engine=None)

    facts = ScannerFacts(
        symbol="XYZ",
        last=10.50,
        vwap=9.80,
        ema9=10.10,
        ema20=9.95,
        atr=0.50,
        hod=10.70,
        lod=9.60,
        spread=0.03,
        volume_deceleration_flag=True,
        rejection_wick_up_flag=True,
        failed_breakout_up_flag=False,
        has_fresh_news=False,
        halt_flag=False,
        minutes_since_open=45,
        vwap_slope=0.005,  # $/min
    )

    regime = MarketRegimeFacts(
        spy_trending_up=False,
        spy_trending_down=False,
        qqq_trending_up=False,
        qqq_trending_down=False,
        major_macro_event_window=False,
    )

    decision = policy.evaluate_symbol(facts, regime)
    return decision


if __name__ == "__main__":
    d = _example()
    print(d.allowed, d.reason, d.setup)
    if d.intent:
        print(d.intent)
