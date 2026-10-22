"""Bounded diagnostic facts, never canonical articles or qualification authority."""
import hashlib

SAMPLES_PER_REASON = 2
TEXT_LIMITS = {'title': 512, 'summary': 1024, 'url': 512}
REASONS = frozenset({'missing_title', 'missing_publication_time', 'future_publication_time',
                     'outside_lookback_window', 'issuer_match_unverified'})


def retain_exclusion(diagnostics, *, reason, entry_index, title, summary, url,
                     date_facts, symbol=None, identity_patterns=()):
    if reason not in REASONS:
        raise ValueError('Unknown exclusion reason')
    state = diagnostics.setdefault('exclusion_evidence', {
        'schema': 'news.rss_exclusions.v1', 'authority': 'diagnostic_only_not_canonical',
        'samples_per_reason': SAMPLES_PER_REASON, 'text_limits': dict(TEXT_LIMITS),
        'counts': {}, 'samples': {}})
    state['counts'][reason] = state['counts'].get(reason, 0) + 1
    samples = state['samples'].setdefault(reason, [])
    if len(samples) >= SAMPLES_PER_REASON:
        return
    from src.ibkr.evidence_safety import sanitize
    original = {'title': str(title or ''), 'summary': str(summary or ''), 'url': str(url or ''),
                'dates': dict(date_facts), 'patterns': list(identity_patterns), 'symbol': symbol}
    safe_input = sanitize(original)  # redact before clipping boundary-crossing tokens
    privacy_redacted = safe_input != original
    identity_patterns = safe_input['patterns']
    date_facts = safe_input['dates']
    record = {'reason': reason, 'entry_index': entry_index,
              'symbol': str(safe_input['symbol'])[:30] if symbol is not None else None,
              'identity_patterns': [str(pattern)[:512] for pattern in identity_patterns[:4]],
              'identity_patterns_truncated': len(identity_patterns) > 4 or any(len(str(p)) > 512 for p in identity_patterns[:4]),
              'timestamp_provenance': {k: (str(v)[:128] if v is not None else None) for k,v in date_facts.items()},
              'timestamp_provenance_truncated': any(v is not None and len(str(v)) > 128 for v in date_facts.values())}
    for key, value in (('title', title), ('summary', summary), ('url', url)):
        value = str(value or '')
        record[key] = safe_input[key][:TEXT_LIMITS[key]]
        record[key + '_truncated'] = len(value) > TEXT_LIMITS[key]
        record[key + '_sha256'] = hashlib.sha256(value.encode('utf-8')).hexdigest()
    # Identity is over the actual normalized fields used at the filter boundary.
    record['article_identity_sha256'] = hashlib.sha256(
        ('\0'.join((str(title), str(url), str(date_facts.get('published_utc'))))).encode('utf-8')).hexdigest()
    record['privacy_redacted'] = privacy_redacted
    samples.append(record)
