"""Broker quote time admission. Receipt/acquisition clocks are never substitutes."""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone

from src.config.config_resolver import get_config

_DATETIME_TYPE = datetime

TIME_REJECTIONS = frozenset({'MD_TIMESTAMP_FUTURE', 'MD_STALE', 'MD_TIMESTAMP_UNKNOWN'})


def quote_time_rejection(timestamp, source, *, now=None):
    """Return a rejection flag or None for the inclusive [0, maximum age] range."""
    if source != 'LAST_TRADE':
        return 'MD_TIMESTAMP_UNKNOWN'
    try:
        stamp = (datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                 if isinstance(timestamp, str) else timestamp)
        if not isinstance(stamp, _DATETIME_TYPE) or stamp.tzinfo is None or stamp.utcoffset() is None:
            return 'MD_TIMESTAMP_UNKNOWN'
        age = ((now if now is not None else datetime.now(timezone.utc)) - stamp).total_seconds()
    except (ValueError, TypeError, OverflowError):
        return 'MD_TIMESTAMP_UNKNOWN'
    if age < 0:
        return 'MD_TIMESTAMP_FUTURE'
    if age > int(get_config('IBKR_SNAPSHOT_MAX_AGE_SECONDS')):
        return 'MD_STALE'
    return None


def quote_evidence(timestamp, source, flags=()):
    # Historical rejection stays attached even if a later clock would admit it.
    return {'timestamp_utc': timestamp.isoformat() if isinstance(timestamp, _DATETIME_TYPE) else timestamp, 'timestamp_source': source,
            'rejection_flags': sorted(TIME_REJECTIONS.intersection(flags or ()))}


def evidence_rejection(evidence, *, now=None):
    if not isinstance(evidence, Mapping):
        return 'MD_TIMESTAMP_UNKNOWN'
    current = quote_time_rejection(evidence.get('timestamp_utc'), evidence.get('timestamp_source'), now=now)
    if current:
        return current
    return next((flag for flag in ('MD_TIMESTAMP_FUTURE', 'MD_STALE', 'MD_TIMESTAMP_UNKNOWN')
                 if flag in (evidence.get('rejection_flags') or ())), None)


def selection_quote_evidence(row, snapshot=None):
    read = row.get if isinstance(row, Mapping) else lambda key, default=None: getattr(row, key, default)
    evidence = read('quote_evidence')
    manual = (str(read('watchlist_source', '')).upper() == 'MANUAL_FOCUS'
              or str(read('promotion_reason', '')).lower() == 'manual_focus')
    if evidence is None and manual and snapshot is not None:
        # User selection owns the stock choice, not market-time authority. Only
        # an actual broker snapshot can supply missing manual-row quote facts.
        return quote_evidence(getattr(snapshot, 'market_timestamp_utc', None),
                              getattr(snapshot, 'timestamp_source', 'UNKNOWN'),
                              getattr(snapshot, 'data_quality_flags', ()))
    return evidence


def filter_quote_rows(rows, *, stage, rejection_reasons=None, snapshots=None):
    accepted = []
    for row in rows:
        read = row.get if isinstance(row, Mapping) else lambda key, default=None: getattr(row, key, default)
        evidence = selection_quote_evidence(row, (snapshots or {}).get(read('symbol')))
        reason = evidence_rejection(evidence)
        if reason is None:
            if read('quote_evidence') is None:
                from copy import copy
                from dataclasses import is_dataclass, replace
                if isinstance(row, Mapping):
                    row = {**row, 'quote_evidence': evidence}
                elif is_dataclass(row):
                    row = replace(row, quote_evidence=evidence)
                else:
                    row = copy(row)
                    row.quote_evidence = evidence
            accepted.append(row)
        else:
            symbol = str(read('symbol') or '').upper()
            print(f'[ROSS][QUOTE][REVALIDATE] stage={stage} symbol={symbol} reason={reason} execution_ineligible=true')
            if rejection_reasons is not None:
                rejection_reasons[symbol] = reason
    return accepted


def ross_intent_quote_rejection(intent, mode):
    """Temporal backstop for active Ross intents, including validation aliases."""
    if str(getattr(mode, 'value', mode)).upper() not in {'READ_ONLY', 'PAPER', 'LIVE'}:
        return None
    if str(getattr(intent, 'strategy_name', '')).lower() not in {'rossmomentumstrategyv1', 'ross_momentum', 'rossmomentumstrategy'}:
        return None
    flags = getattr(intent, 'data_quality_flags', ()) or ()
    retained = next((flag for flag in ('MD_TIMESTAMP_FUTURE', 'MD_STALE', 'MD_TIMESTAMP_UNKNOWN') if flag in flags), None)
    if retained:
        return retained
    evidence = getattr(intent, 'quote_evidence', None)
    if not isinstance(evidence, Mapping):
        return 'MD_TIMESTAMP_UNKNOWN'
    reason = evidence_rejection(evidence.get('selection'))
    if reason is None and evidence.get('snapshot') is not None:
        reason = evidence_rejection(evidence['snapshot'])
    return reason


def filter_ross_quote_intents(intents, mode, *, stage, rejection_reasons=None):
    accepted = []
    for intent in intents:
        reason = ross_intent_quote_rejection(intent, mode)
        if reason:
            print(f'[ROSS][QUOTE][INTENT_REJECT] stage={stage} symbol={intent.symbol} reason={reason}')
            if rejection_reasons is not None:
                rejection_reasons[str(intent.symbol).upper()] = reason
        else:
            accepted.append(intent)
    return accepted
