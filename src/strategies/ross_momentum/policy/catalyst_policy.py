"""Ross catalyst policy status semantics."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any
import re
import time
from datetime import datetime, timezone

from src.strategies.ross_momentum.strategy_policy import StockSelectionSpec

from .runtime_safety import normalize_run_mode, validation_override_allowed


class CatalystStatus(str, Enum):
    CONFIRMED = "CONFIRMED"
    ABSENT = "ABSENT"
    UNKNOWN = "UNKNOWN"
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
    DISABLED_FOR_VALIDATION = "DISABLED_FOR_VALIDATION"


@dataclass(frozen=True)
class CatalystDecision:
    status: CatalystStatus
    satisfied: bool
    reason: str


@dataclass(frozen=True)
class CatalystPolicy:
    require_catalyst: bool
    statuses: tuple[CatalystStatus, ...] = tuple(CatalystStatus)

    @classmethod
    def from_stock_selection(cls, stock_selection: StockSelectionSpec) -> "CatalystPolicy":
        return cls(require_catalyst=bool(stock_selection.require_catalyst))


def assess_catalyst(
    *,
    mode: Any,
    news_enabled: bool,
    news_available: bool,
    confirmed: bool | None,
    validation_bypass_requested: bool = False,
) -> CatalystDecision:
    if confirmed is True:
        return CatalystDecision(CatalystStatus.CONFIRMED, True, "confirmed")
    if confirmed is False and news_available:
        return CatalystDecision(CatalystStatus.ABSENT, False, "absent")
    if validation_override_allowed(mode, validation_bypass_requested):
        return CatalystDecision(
            CatalystStatus.DISABLED_FOR_VALIDATION,
            True,
            "explicit_validation_bypass",
        )
    if not news_enabled:
        return CatalystDecision(CatalystStatus.DATA_UNAVAILABLE, False, "news_disabled")
    if not news_available:
        return CatalystDecision(CatalystStatus.DATA_UNAVAILABLE, False, "news_unavailable")
    return CatalystDecision(CatalystStatus.UNKNOWN, False, "news_unknown")


def log_catalyst_unavailable(symbol: Any, reason: str = "news_unavailable") -> None:
    print(
        "[ROSS][CATALYST][UNKNOWN] "
        f"symbol={str(symbol or 'UNKNOWN').upper()} reason={reason}"
    )


def log_catalyst_validation_bypass(mode: Any, reason: str) -> None:
    print(
        "[ROSS][CATALYST][VALIDATION_BYPASS] "
        f"mode={normalize_run_mode(mode)} reason={reason}"
    )


def log_catalyst_live_not_satisfied(symbol: Any, reason: str) -> None:
    print(
        "[ROSS][CATALYST][LIVE_NOT_SATISFIED] "
        f"symbol={str(symbol or 'UNKNOWN').upper()} reason={reason}"
    )


CATALYST_KEYWORDS = {
    "earnings": "EARNINGS",
    "guidance": "EARNINGS",
    "fda": "FDA",
    "approval": "FDA",
    "contract": "CONTRACT",
    "partnership": "CONTRACT",
    "upgrade": "ANALYST_ACTION",
    "downgrade": "ANALYST_ACTION",
    "initiates": "ANALYST_ACTION",
    "press release": "PRESS_RELEASE",
    "ai": "TECH_CATALYST",
    "artificial intelligence": "TECH_CATALYST",
    "crypto": "CRYPTO_CATALYST",
    "bitcoin": "CRYPTO_CATALYST",
    "ev": "EV_CATALYST",
    "electric vehicle": "EV_CATALYST",
    "battery": "EV_CATALYST",
    "defense": "DEFENSE_CATALYST",
    "military": "DEFENSE_CATALYST",
    "quantum": "TECH_CATALYST",
    "semiconductor": "TECH_CATALYST",
    "gpu": "TECH_CATALYST",
}
# Preserve ordinary forms recognized by the established event vocabulary
# without treating short abbreviations as arbitrary substrings of prose.
CATALYST_KEYWORD_FORMS = {
    "approval": ("approval", "approvals"),
    "contract": ("contract", "contracts", "contracted", "contracting"),
    "partnership": ("partnership", "partnerships"),
    "upgrade": ("upgrade", "upgrades", "upgraded"),
    "downgrade": ("downgrade", "downgrades", "downgraded"),
    "press release": ("press release", "press releases"),
    "crypto": ("crypto", "cryptos", "cryptocurrency", "cryptocurrencies"),
    "bitcoin": ("bitcoin", "bitcoins"),
    "ev": ("ev", "evs"),
    "electric vehicle": ("electric vehicle", "electric vehicles"),
    "semiconductor": ("semiconductor", "semiconductors"),
    "gpu": ("gpu", "gpus"),
}
DILUTION_KEYWORDS = {
    "offering",
    "dilution",
    "s-1",
    "s1",
    "atm",
    "registered direct",
}


def classify_headline(title: str) -> str | None:
    for keyword, label in CATALYST_KEYWORDS.items():
        forms = "|".join(re.escape(value) for value in CATALYST_KEYWORD_FORMS.get(keyword, (keyword,)))
        if re.search(rf"(?<![a-z0-9])(?:{forms})(?![a-z0-9])", title.lower()):
            return label
    return None


def detect_dilution(title: str) -> bool:
    text = title.lower()
    # Short financing abbreviations must not match ordinary words (treatment,
    # aftermath, etc.). Keep established longer offering/dilution forms intact.
    return any((re.search(r"(?<![a-z0-9])" + re.escape(keyword) + r"(?![a-z0-9])", text)
                if keyword in {"atm", "s1", "s-1"} else keyword in text)
               for keyword in DILUTION_KEYWORDS)


def assess_issuer_event(symbol, item, candidates=()):
    """Conservative title-clause attribution, not semantic event inference.

    A supplied research/legacy classification is never qualification authority.
    Existing event vocabulary is unchanged. Unknown syntax fails closed.
    """
    from src.news.news_fetcher import company_aliases_for_symbol, symbol_relevance_match, _compile_symbol_patterns
    title = str(getattr(item, 'headline', getattr(item, 'title', '')) or '')
    candidate = next((c for c in candidates if c.normalized_symbol == symbol), None)
    metadata = dict(candidate.metadata) if candidate else {}
    metadata['company_name'] = getattr(item, 'company_name', None) or (candidate.company_name if candidate else None) or metadata.get('company_name')
    metadata['aliases'] = (getattr(item, 'aliases', ()), candidate.aliases if candidate else (), metadata.get('aliases', ()))
    published = getattr(item, 'published_at', None)
    timestamp = published.timestamp() if published is not None and published.tzinfo is not None else getattr(item, 'published_ts', None)
    age = time.time() - timestamp if timestamp is not None else None
    kind = classify_headline(title)
    result = {'evidence_id': getattr(item, 'evidence_id', None), 'qualified': False,
              'catalyst_type': kind, 'reason': 'issuer_event_attribution_uncertain', 'age_seconds': age}
    if getattr(item, 'source_tier', None) == 'research':
        result['reason'] = 'research_only_evidence'
        return result
    timestamp_facts = getattr(item, 'timestamp_provenance', None) or dict(getattr(item, 'raw', {}) or {}).get('timestamp_provenance', {})
    if timestamp_facts.get('selected_time_basis') == 'updated':
        result['reason'] = 'publication_time_unverified_update_only'
        return result
    if age is None or age < 0 or age > 21600:
        result['reason'] = 'missing_future_or_stale_publication_time'
        return result
    if symbol_relevance_match(symbol, title=title, summary=str(getattr(item, 'summary', '') or ''), metadata=metadata) is None:
        result['reason'] = 'issuer_match_unverified'
        return result
    if detect_dilution(title):
        result['reason'] = 'dilution_or_offering'
        return result
    if kind is None:
        result['reason'] = 'no_catalyst_classification'
        return result
    if re.search(r'\b(prediction|preview|could|might|may|rumou?r|watchlist|speculat\w*)\b|\?', title, re.I):
        result['reason'] = 'event_assertion_uncertain'
        return result
    aliases = company_aliases_for_symbol(symbol, metadata)
    ticker = _compile_symbol_patterns((symbol,))[symbol]
    def identity_end(text):
        match = ticker.match(text)
        end = match.end() if match else None
        for alias in aliases:
            words = re.findall(r'[A-Z0-9]+', alias.upper())
            match = re.match(r'[^A-Z0-9]*' + r'[^A-Z0-9]+'.join(map(re.escape, words)) + r'(?![A-Z0-9])', text.upper())
            if match:
                end = max(end or 0, match.end())
        return end
    ownership_rejected = False
    # Clause boundaries prevent a later co-mention from inheriting an event.
    # A leading verified issuer may itself be AS (or contain a boundary word).
    # Protect only that identity span; later clauses still cannot inherit it.
    title = title.strip()
    protected_end = identity_end(title) or 0
    boundaries = [m for m in re.finditer(r';|\s+[—–]\s+|\b(?:while|whereas|versus|alongside|after|but|as)\b', title, re.I)
                  if m.start() >= protected_end]
    clauses = []
    start = 0
    for boundary in boundaries:
        clauses.append(title[start:boundary.start()])
        start = boundary.end()
    clauses.append(title[start:])
    for clause in clauses:
        clause = clause.strip()
        clause_kind = classify_headline(clause)
        if clause_kind is None:
            continue
        subject_end = identity_end(clause)
        if subject_end is None:
            continue
        remainder = clause[subject_end:]
        # Multiple coordinated subjects are ambiguous without event binding.
        event = next((m for m in re.finditer(r'\b(?:' + '|'.join(re.escape(form) for keyword in CATALYST_KEYWORDS for form in CATALYST_KEYWORD_FORMS.get(keyword, (keyword,))) + r')\b', remainder, re.I)), None)
        prefix = remainder[:event.start()] if event else remainder
        # Only direct assertions bind the event to this grammatical subject.
        # Unknown syntax (e.g. issuer tracks another company's earnings) fails closed.
        direct = re.match(r"^[\s:,'’()-]*(?:(?:reports?|announces?|raises?|cuts?|receives?|wins?|secures?|launches?|expands?|signs?|posts?|releases?|gets?|obtains?|granted)\b|(?:Q[1-4]\s+)?(?:earnings|guidance|FDA|approval|contract|partnership|AI|GPU|EV|semiconductor)\b)", remainder, re.I)
        asserted = re.match(r"^[\s:,'’()-]*(?:reports?|announces?|raises?|cuts?|receives?|wins?|secures?|launches?|expands?|signs?|posts?|releases?|gets?|obtains?|granted)\b", remainder, re.I)
        nominal_earnings_assertion = re.match(r"^[\s:,'’()-]*(?:Q[1-4]\s+)?(?:earnings|guidance)\s+(?:beats?|miss(?:es)?|rises?|falls?|surges?|tops?|raised|cut)\b", remainder, re.I)
        if not (asserted or nominal_earnings_assertion):
            continue
        if not direct or re.search(r"\b(?:on|about|from|following|amid|rivals?|competitors?)\b|['’]s\s+", prefix, re.I):
            continue
        allowed_prefix = {"report", "reports", "announce", "announces", "raises", "cuts", "receives", "wins", "secures",
                          "launches", "expands", "signs", "posts", "releases", "gets", "obtains", "granted",
                          "its", "a", "an", "the", "new", "major", "record", "quarterly", "annual", "fiscal",
                          "first", "second", "third", "fourth", "quarter", "half", "year", "positive", "strong",
                          "q1", "q2", "q3", "q4", "multi", "million", "billion", "dollar", "supply", "distribution", "manufacturing", "commercial", "government", "definitive", "licensing", "strategic", "collaboration", "purchase", "sales", "service", "services", "long", "term"}
        direct_technology_launch = (clause_kind in {"TECH_CATALYST", "EV_CATALYST", "CRYPTO_CATALYST", "DEFENSE_CATALYST"}
                                    and re.match(r"^[\s:,'’()-]*(?:launches?|expands?)\b", remainder, re.I))
        if not direct_technology_launch and any(token not in allowed_prefix and not token.isdigit() for token in re.findall(r"[a-z0-9]+", prefix.lower())):
            continue
        if re.search(r'\b(?:and|with|vs)\b|&', prefix, re.I):
            continue
        # Subject assertions cannot borrow an event explicitly owned by somebody
        # else. Unknown ownership fails closed; reuse the SAME issuer identity
        # matcher rather than inferring company names or trusting stored tags.
        owner_uncertain = False
        tail = remainder[event.end():] if event else ""
        connectors = r"of|by|belonging\s+to|for|at|from|(?:granted|awarded|issued|assigned|licensed|given)(?:\s+(?:exclusively|solely|jointly))?\s+to"
        consumed_owner_end = -1
        for complement in re.finditer(r"\b(?:" + connectors + r")\s+", tail, re.I):
            if complement.start() < consumed_owner_end:
                continue
            owner = tail[complement.end():].strip()
            end = identity_end(owner)
            period_text = r"(?:the\s+)?(?:fiscal\s+)?(?:Q[1-4]|(?:first|second|third|fourth)\s+quarter)(?:\s+(?:of\s+)?20\d{2})?"
            period = clause_kind == "EARNINGS" and re.fullmatch(period_text + r"[\s.!]*", owner, re.I)
            # A complete dated reporting period is not an issuer owner. Validate
            # the entire tail and calendar date; never swallow a trailing rival.
            ended = re.fullmatch(r"(?:the\s+)?(?:(?:fiscal|first|second|third|fourth)\s+)?quarter\s+ended\s+([A-Za-z]+\s+\d{1,2},\s+20\d{2})[.!]?", owner, re.I)
            if clause_kind == "EARNINGS" and ended:
                try:
                    datetime.strptime(ended.group(1), "%B %d, %Y")
                    period = True
                except ValueError:
                    pass
            # Explicit product/purpose/value/location syntax is not corporate
            # ownership. Keep this grammar bounded and anchored; unknown names,
            # possessive rivals and appended owners still fail closed.
            connector = complement.group(0).strip().lower()
            ordinary_pattern = (
                r"(?:(?:its\s+)?(?:lead\s+|new\s+)?(?:drug|therapy|treatment|candidate)(?:\s+[A-Z]{1,8}-\d{1,6})?"
                r"|(?:cloud|software|manufacturing|supply|healthcare)\s+services"
                r"|hospitals|clinics|patients|(?:its\s+)?(?:US|U\.S\.|European)\s+(?:plant|facility)"
                r"|\$\d+(?:\.\d+)?\s+(?:million|billion))[.!]?")
            ordinary = connector in {"for", "at", "from"} and re.fullmatch(ordinary_pattern, owner, re.I)

            if end is not None:
                consumed_owner_end = complement.end() + end
                # A recognised company followed by 'its rival', a possessive,
                # or another unknown complement is not proof of event ownership.
                suffix = owner[end:]
                same_owner_tail = re.fullmatch(r"[\s,.!]*", suffix)
                same_owner_period = clause_kind == "EARNINGS" and re.fullmatch(
                    r"[\s,]*(?:for|in)\s+" + period_text + r"[\s.!]*", suffix, re.I)
                same_owner_ordinary = re.fullmatch(
                    r"[\s,]*(?:for|at|from)\s+" + ordinary_pattern, suffix, re.I)
                if not same_owner_tail and not same_owner_period and not same_owner_ordinary:
                    owner_uncertain = True
                    break
            elif period or ordinary:
                consumed_owner_end = len(tail)
            else:
                owner_uncertain = True
                break
        if owner_uncertain:
            ownership_rejected = True
            continue
        result.update(qualified=True, catalyst_type=clause_kind, reason='issuer_subject_event_attributed')
        return result
    result['reason'] = 'event_ownership_uncertain_or_other_issuer' if ownership_rejected else 'event_not_attributed_to_requested_issuer'
    return result


def select_qualification_evidence(items, request):
    """Latest presentation slots plus ONE policy witness (veto first).

    Re-evaluated from text/time/provenance on every store/read/merge. Neither
    stored flags nor a larger arbitrary article cap confer qualification.
    """
    display_limit = int(request.metadata['presentation_limit'])
    latest = []
    witness = None
    witness_rank = (-1, -1.0)
    def stamp(item):
        pub = getattr(item, 'published_at', None)
        return pub.timestamp() if pub is not None else float(getattr(item, 'published_ts', 0))
    def key(item):
        return getattr(item, 'evidence_id', None) or (getattr(item, 'title', ''), getattr(item, 'source', ''), getattr(item, 'url', ''))
    for item in items:
        if key(item) not in {key(x) for x in latest}:
            latest.append(item)
            latest.sort(key=stamp, reverse=True)
            del latest[display_limit:]
        symbol = getattr(item, 'symbol', '')
        decision = assess_issuer_event(symbol, item)
        age = time.time() - stamp(item)
        veto = (getattr(item, 'source_tier', None) != 'research' and 0 <= age <= 21600 and detect_dilution(str(getattr(item, 'headline', getattr(item, 'title', '')))))
        rank = (2 if veto else 1 if decision['qualified'] else 0, stamp(item))
        if rank[0] and rank > witness_rank:
            witness, witness_rank = item, rank
    if witness is not None and key(witness) not in {key(x) for x in latest}:
        latest.append(witness)
    return latest


def unresolved_issuer_news(headlines_by_symbol, request):
    """Fallback only for bounded cohorts not already resolved by Ross policy.

    The adapter calls this after complete primary exploration. Source coverage
    stays separate from acquisition and this never turns generic news positive.
    """
    unresolved = []
    for symbol, items in headlines_by_symbol.items():
        positive = any(assess_issuer_event(symbol, item)['qualified'] for item in items)
        veto = any(0 <= time.time() - item.published_ts <= request.freshness_seconds
                   and detect_dilution(item.title) for item in items)
        if not positive and not veto:
            unresolved.append(symbol)
    return unresolved
