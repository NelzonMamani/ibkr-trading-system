"""Native cumulative stock volume and the Ross PAPER entry volume gate."""

from collections.abc import Mapping
from math import isfinite

from src.domain.quote_freshness import quote_time_rejection

VERIFIED_SHARE_UNIT = "SHARES"
READ_ONLY_VOLUME_DIAGNOSTIC = "VOLUME_UNVERIFIED_READ_ONLY_DIAGNOSTIC"
SHARE_UNIT_SOURCE = "TWS_WATCHLIST_SHARE_COMPARISON"
US_PRIMARY_EXCHANGES = frozenset({
    "NYSE", "NASDAQ", "ISLAND", "AMEX", "NYSEAMERICAN", "ARCA", "NYSEARCA",
    "BATS", "CBOE", "IEX", "MEMX", "LTSE", "NASDAQ.NMS", "NASDAQ.NGM", "NASDAQ.NCM",
})


def native_stock_volume_rejection(evidence, *, client_id=None, connection_epoch=None,
                                  con_id=None, symbol=None, now=None):
    """Check callback ownership and freshness independently from unit evidence."""
    if not isinstance(evidence, Mapping):
        return "ROSS_VOLUME_EVIDENCE_MISSING"
    if (evidence.get("source") != "IBKR_NATIVE_TICK_SIZE"
            or evidence.get("sdk_distribution") != "9.81.1.post1"
            or evidence.get("session_basis") != "IBKR_CURRENT_TRADING_DAY_CUMULATIVE"
            or evidence.get("security_type") != "STK" or evidence.get("currency") != "USD"
            or evidence.get("primary_exchange") not in US_PRIMARY_EXCHANGES):
        return "ROSS_VOLUME_SOURCE_UNSUPPORTED"
    if (evidence.get("market_data_status") != "LIVE" or evidence.get("tick_type") != 8
            or evidence.get("mixed_volume_tick_types") or evidence.get("nonlive_type_observed")
            or evidence.get("broker_error_observed")):
        return "ROSS_VOLUME_DATA_NOT_LIVE"
    if (any(type(evidence.get(field)) is not int or evidence[field] < minimum
            for field, minimum in (("con_id", 1), ("request_id", 0), ("client_id", 0),
                                   ("connection_epoch", 0), ("server_version", 1)))
            or (client_id is not None and evidence["client_id"] != client_id)
            or (connection_epoch is not None and evidence["connection_epoch"] != connection_epoch)
            or (con_id is not None and evidence["con_id"] != con_id)
            or (symbol is not None and evidence.get("symbol") != symbol)):
        return "ROSS_VOLUME_SCOPE_MISMATCH"
    if (quote_time_rejection(evidence.get("market_timestamp_utc"), "LAST_TRADE", now=now)
            or quote_time_rejection(evidence.get("received_at_utc"), "LAST_TRADE", now=now)):
        return "ROSS_VOLUME_STALE_OR_UNTIMED"
    raw = evidence.get("raw_value")
    if not _valid_raw_volume(raw):
        return "ROSS_VOLUME_VALUE_INVALID"
    return None


def _valid_raw_volume(value):
    return (type(value) is int or (type(value) is float and isfinite(value))) and value >= 0


def verified_volume_shares(evidence):
    """The supported source sends shares directly. Conversion is unnecessary."""
    if (isinstance(evidence, Mapping) and evidence.get("unit") == VERIFIED_SHARE_UNIT
            and evidence.get("unit_source") == SHARE_UNIT_SOURCE):
        raw, shares = evidence.get("raw_value"), evidence.get("shares")
        if _valid_raw_volume(raw) and type(shares) in (int, float) and shares == raw:
            return shares
    return None


def ross_entry_volume_rejection(intent, mode, *, client_id=None, connection_epoch=None, con_id=None):
    if str(getattr(mode, "value", mode)).upper() != "PAPER":
        return None
    read = intent.get if isinstance(intent, Mapping) else lambda key, default=None: getattr(intent, key, default)
    if str(read("strategy_name", "")).lower() not in {
        "rossmomentumstrategyv1", "ross_momentum", "rossmomentumstrategy",
    }:
        return None
    evidence = read("volume_evidence")
    source_rejection = native_stock_volume_rejection(
        evidence, client_id=client_id, connection_epoch=connection_epoch, con_id=con_id,
        symbol=str(read("symbol", "")).upper(),
    )
    if source_rejection:
        return source_rejection
    shares = verified_volume_shares(evidence)
    if shares is None:
        return "ROSS_VOLUME_UNIT_UNVERIFIED"
    from src.market_data.session_pct_change import normalize_session_label
    from src.strategies.ross_momentum.strategy_policy import RossMomentumPolicy, stock_selection_policy_for_session_phase

    session = normalize_session_label(str(evidence.get("scanner_session") or ""))
    # Scanner/strategy handoff can carry the finer operational clock phases
    # instead of the market-data session labels. Both clocks classify these as RTH.
    if session in {"RTH_OPEN", "RTH_MID", "RTH_LATE", "OPENING_0_30", "MORNING"}:
        stock_policy = stock_selection_policy_for_session_phase(RossMomentumPolicy(), session)
        if shares < stock_policy.min_volume:
            return "ROSS_VOLUME_BELOW_STOCK_SELECTION_MINIMUM"
    elif session not in {"PRE", "PREMARKET", "AH"}:
        return "ROSS_VOLUME_SESSION_UNSUPPORTED"
    if evidence.get("scanner_execution_eligible") is not True:
        return "ROSS_VOLUME_SCANNER_EXECUTION_INELIGIBLE"
    return None
