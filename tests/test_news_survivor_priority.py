"""Offline issuer-query allocation regression."""
from types import SimpleNamespace as NS
from src.scanner import scanner_runner as scanner

def test_news_priority_retains_all_coverage_and_identity(monkeypatch):
    rows = [dict(symbol=s, company_name=s+' FULL ISSUER', con_id=n) for n, s in enumerate(['REJECT1','REJECT2','ELIG1','ELIG2','ELIG3','ELIG4','ELIG5'], 100)]
    monkeypatch.setattr(scanner, 'RossPolicy', lambda: NS(issuer_query_enabled=True))
    ordered = scanner._news_acquisition_order(rows, rows[2:])
    metadata = scanner._news_symbol_metadata_for_contexts(ordered)
    queries = sorted(metadata, key=lambda symbol: metadata[symbol]['priority_rank'])[:4]
    assert queries == ['ELIG1','ELIG2','ELIG3','ELIG4']
    assert len(metadata) == len(rows)
    assert metadata['REJECT1']['company_name'] == 'REJECT1 FULL ISSUER'
    assert metadata['ELIG1']['con_id'] == 102
    assert [row['symbol'] for row in rows][:2] == ['REJECT1','REJECT2']
