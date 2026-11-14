"""Ross event authority survives acquisition degradation, never event expiry.

Only canonical facts are handed off. No cached CONFIRMED flag is authority;
validation performs no HTTP and never writes the canonical store.
"""
from __future__ import annotations

from collections.abc import Mapping
from copy import copy
from dataclasses import is_dataclass, replace
from datetime import datetime, timezone
import time
from src.config.config_resolver import get_config

from src.news.evidence_store import (CanonicalNewsEvidenceStore, evidence_from_mapping, serialize_evidence,
    evidence_max_entries, coalesce_original_publications, original_publication_binding, mark_original_established, canonical_original_facts)
from src.news.issuer_relevance import evidence_issuer_relevance_verified
from src.news.news_intelligence_contract import NewsBatchResult, NewsCandidate, NewsRequest
from .catalyst_policy import (ISSUER_EVENT_MAX_AGE_SECONDS, assess_issuer_event, detect_dilution,
    retained_veto, protected_ross_request, NEXT_SESSION_CONTRACT, fact_binding,
    next_session_request_metadata, ROSS_ISSUER_EVENT_PROFILE, select_qualification_evidence, temporal_binding_matches)
from .runtime_safety import validation_override_allowed, log_validation_override_active


def retained_dilution(items):
    # Preserve the existing final consumer veto, including retained older facts.
    return any(retained_veto(item) for item in items)


def evidence_handoff(symbol, evidence, candidate, *, acquisition_health, acquisition_reason, request=None):
    result = {"schema": "ross_catalyst_evidence_v1", "symbol": symbol,
            "issuer": {"symbol": symbol, "company_name": candidate.company_name if candidate else None,
                       "aliases": list(candidate.aliases) if candidate else []},
            "evidence": [serialize_evidence(item) for item in evidence],
            "publication_max_age_seconds": ISSUER_EVENT_MAX_AGE_SECONDS,
            "acquisition_snapshot": {"health": acquisition_health, "reason": acquisition_reason}}
    if protected_ross_request(request):
        decisions = [assess_issuer_event(symbol, item, (candidate,) if candidate else (), request=request) for item in evidence]
        result.update(next_session_contract=NEXT_SESSION_CONTRACT,
            temporal_bindings={fact_binding(item): row["temporal_authority"] for item, row in zip(evidence, decisions)
                               if row["qualified"] and row.get("temporal_authority")})
    return result


def revalidate_handoff(symbol, handoff, *, store=None, request=None):
    """Reclassify original facts and merge current canonical vetoes, read-only.

    Missing/legacy flags fail closed. A missing receipt cannot certify acquisition
    health, but is not itself evidence that a verified event ceased to exist.
    """
    rejected = {"qualified": False, "qualification_reason": "canonical_evidence_missing",
                "evidence_ids": [], "acquisition_health": "unknown",
                "acquisition_reason": "acquisition_not_verified"}
    symbol = str(symbol or "").strip().upper()
    if not isinstance(handoff, Mapping) or handoff.get("schema") != "ross_catalyst_evidence_v1":
        return rejected
    if not isinstance(handoff.get("issuer"), Mapping):
        return {**rejected, "qualification_reason": "canonical_issuer_invalid"}
    if handoff.get("symbol") != symbol or handoff["issuer"].get("symbol") != symbol:
        return {**rejected, "qualification_reason": "canonical_issuer_mismatch"}
    issuer = handoff["issuer"]
    aliases = issuer.get("aliases", ())
    if not isinstance(aliases, (list, tuple)) or not isinstance(handoff.get("evidence"), (list, tuple)):
        return {**rejected, "qualification_reason": "canonical_evidence_invalid"}
    candidate = NewsCandidate(symbol=symbol, company_name=issuer.get("company_name"), aliases=tuple(aliases))
    facts = []
    for row in handoff.get("evidence", ()):
        item = evidence_from_mapping(row)
        if item is not None and item.symbol == symbol and item.evidence_id:
            facts.append(item)
    if not facts:
        return rejected
    # Read the existing bounded presentation+witness cohort without trimming its
    # witness/anchor slots or reselecting away an already-retained older veto.
    read_request = NewsRequest(max_evidence_per_symbol=evidence_max_entries() + 1, metadata={"read_retained_cohort": True})
    current = (store or CanonicalNewsEvidenceStore()).read((candidate,), read_request, include_prep=False)
    if current.diagnostics.get("cache_read_failed"):
        return {**rejected, "qualification_reason": "canonical_store_unreadable"}
    batch = NewsBatchResult(candidates=(candidate,))
    def accepted(item):
        return item.symbol == symbol and evidence_issuer_relevance_verified(symbol, item, batch)
    retained_facts = [item for item in facts if accepted(item)]
    current_facts = [item for item in current.evidence_by_symbol.get(symbol, ()) if accepted(item)]
    canonical_bindings = {fact_binding(item) for item in current_facts}
    facts = retained_facts + current_facts
    if (handoff.get("next_session_contract") == NEXT_SESSION_CONTRACT or any(
            original_publication_binding(item).get("contract") == NEXT_SESSION_CONTRACT for item in facts)):
        # Only the current canonical owner establishes precedence; a retained
        # carrier's marker is data, not original-assertion authority.
        retained = [mark_original_established(item, False) for item in retained_facts]
        canonical = canonical_original_facts(current_facts, NEXT_SESSION_CONTRACT)
        canonical_bindings = {fact_binding(item) for item in canonical}
        facts = coalesce_original_publications(retained + canonical, veto_predicate=retained_veto, contract=NEXT_SESSION_CONTRACT)
    if request is None:
        request = NewsRequest(strategy_id="ross_momentum", metadata={
            "qualification_profile": ROSS_ISSUER_EVENT_PROFILE,
            "presentation_limit": evidence_max_entries(), "retention_selector": select_qualification_evidence,
            **next_session_request_metadata()})
    decisions = [assess_issuer_event(symbol, item, (candidate,), request=request) for item in facts]
    for item, decision in zip(facts, decisions):
        temporal = decision.get("temporal_authority", {})
        if temporal.get("route") == "next_session_opening" and fact_binding(item) not in canonical_bindings:
            stored = handoff.get("temporal_bindings", {}).get(fact_binding(item)) if isinstance(handoff.get("temporal_bindings"), Mapping) else None
            if handoff.get("next_session_contract") != NEXT_SESSION_CONTRACT or not temporal_binding_matches(stored, temporal):
                decision.update(qualified=False, reason="canonical_extra_binding_invalid")
    positive = [row for row in decisions if row["qualified"] and row["evidence_id"]]
    veto = retained_dilution(facts)
    valid_until = max((decision.get("temporal_authority", {}).get("valid_until", item.published_at.timestamp() + ISSUER_EVENT_MAX_AGE_SECONDS)
                       for item, decision in zip(facts, decisions)
                       if decision["qualified"] and decision["evidence_id"] and item.published_at), default=None)
    # Inspect latest persisted acquisition facts without invoking acquisition.
    receipt = current.diagnostics.get("last_retrieval_by_symbol", {}).get(symbol, {})
    health_reason = "cached_handoff_coverage_not_reverified"
    if receipt.get("budget_exhausted"):
        health_reason = "budget_exhausted"
    elif receipt.get("provider_available") is False:
        health_reason = "acquisition_failed:" + str(receipt.get("provider_status") or receipt.get("retrieval_status") or "unavailable")
    else:
        try:
            completed = datetime.fromisoformat(str(receipt.get("completed_at")).replace("Z", "+00:00"))
            if completed.tzinfo is None:
                raise ValueError("naive acquisition receipt")
            interval = float(get_config("NEWS_REFRESH_SECONDS_RTH") or 120)
            if time.time() - completed.timestamp() >= interval:
                health_reason = "acquisition_receipt_expired"
        except (TypeError, ValueError):
            health_reason = "acquisition_receipt_missing_or_invalid"
    historical = handoff.get("acquisition_snapshot")
    historical = historical if isinstance(historical, Mapping) else {}
    # A snapshot's historical health is never advertised as current coverage.
    return {"qualified": bool(positive and not veto),
            "qualification_reason": "retained_dilution_veto" if veto else
                "verified_issuer_event_valid" if positive else "no_valid_canonical_event",
            "evidence_ids": sorted({row["evidence_id"] for row in positive}),
            "qualification_decisions": decisions, "dilution_veto": bool(veto),
            "valid_until_utc": datetime.fromtimestamp(valid_until, timezone.utc).isoformat() if valid_until is not None and not veto else None,
            "acquisition_health": "degraded", "acquisition_reason": health_reason,
            "previous_acquisition_health": historical.get("health", "unknown"),
            "previous_acquisition_reason": historical.get("reason", "acquisition_not_verified")}


def filter_catalyst_rows(rows, *, store=None, request=None, stage="setup_handoff", mode=None, rejection_reasons=None):
    # Preserve the established explicit SIM/PAPER validation override only. It
    # is never a CONFIRMED event and cannot operate in LIVE/READ_ONLY.
    if mode is not None and validation_override_allowed(mode, bool(get_config("ROSS_VALIDATION_OVERRIDE_ENABLED"))):
        log_validation_override_active(mode, "catalyst_handoff_explicit_validation_bypass")
        return list(rows)
    accepted = []
    for row in rows:
        read = row.get if isinstance(row, dict) else lambda key, default=None: getattr(row, key, default)
        # Preserve the existing explicit user-selected manual stock-selection
        # bypass. It does not assert or manufacture a canonical positive event.
        if str(read("watchlist_source", "")).upper() == "MANUAL_FOCUS":
            print(f"[ROSS][CATALYST][MANUAL_AUTHORITY] symbol={read('symbol')} canonical_event_claimed=false")
            accepted.append(row)
            continue
        decision = revalidate_handoff(read("symbol"), read("catalyst_evidence"), store=store, request=request)
        print(f"[ROSS][CATALYST][REVALIDATE] stage={stage} symbol={read('symbol')} "
              f"qualified={decision['qualified']} qualification_reason={decision['qualification_reason']} "
              f"acquisition_health={decision['acquisition_health']} acquisition_reason={decision['acquisition_reason']} "
              f"evidence_ids={decision['evidence_ids']}")
        if decision["qualified"]:
            changes = {"catalyst_qualification_reason": decision["qualification_reason"],
                       "catalyst_valid_until_utc": decision["valid_until_utc"],
                       "news_acquisition_health": decision["acquisition_health"],
                       "news_acquisition_reason": decision["acquisition_reason"]}
            if isinstance(row, dict):
                updated = {**row, **changes}
            elif is_dataclass(row):
                updated = replace(row, **{key: value for key, value in changes.items() if hasattr(row, key)})
            else:
                updated = copy(row)
                for key, value in changes.items():
                    setattr(updated, key, value)
            accepted.append(updated)
        elif rejection_reasons is not None:
            rejection_reasons[str(read("symbol") or "").upper()] = decision["qualification_reason"]
    return accepted
