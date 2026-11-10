from pathlib import Path

import pytest

from src.e21.harness import run_harness


@pytest.mark.parametrize("hold_fetch",[False,True],ids=["immediate_external_fact","held_external_fact"])
def test_harness_reports(tmp_path: Path, monkeypatch,hold_fetch):
    from threading import Event
    from src.market_data.float_provider import FloatProvider
    from src.market_data.float_discovery_worker import shutdown_float_discovery_workers
    # Reports use synthetic E21A/E21B symbols. Keep the actual scanner/worker/
    # cache/report/cleanup owners, but never start optional real provider work.
    facts={'E21A':12_000_000,'E21B':8_000_000}
    completed=Event();entered=Event();release=Event()
    if not hold_fetch:release.set()
    written=[]
    record=FloatProvider.record_discovery
    def external_float(self,symbol):
        assert symbol in facts
        entered.set()
        assert release.wait(timeout=3),'Synthetic external float was not released'
        return facts[symbol],'SYNTHETIC_EXTERNAL_FACT'
    def unexpected_fallback(self,symbol):
        raise AssertionError('Synthetic primary float must not use another provider')
    def observe_record(self,*args,**kwargs):
        result=record(self,*args,**kwargs)
        written.append(kwargs['symbol'])
        completed.set()  # Real cache/persistence completion, not fetch admission.
        return result
    monkeypatch.setattr(FloatProvider,'provider_yahoo',external_float)
    monkeypatch.setattr(FloatProvider,'provider_finviz',unexpected_fallback)
    monkeypatch.setattr(FloatProvider,'record_discovery',observe_record)
    try:
        report = run_harness(tmp_path)
        assert entered.wait(timeout=3),'Actual discovery worker never reached the external boundary'
        if hold_fetch:
            assert not completed.is_set()  # Fetch admission is not a completed cache write.
            release.set()
        assert completed.wait(timeout=3),'Actual synthetic float cache write did not complete'
        assert written and set(written)<=set(facts)
    finally:
        release.set()  # Always release the synthetic provider before bounded owner cleanup.
        assert shutdown_float_discovery_workers(timeout=3),'Owned E21 float worker did not shut down'

    assert report["verdict"] in {"PASS", "FAIL"}
    assert (tmp_path / "harness_report.json").exists()
    assert (tmp_path / "harness_report.md").exists()
    assert (tmp_path / "E21_CERTIFICATION_REPORT.md").exists()
    assert (tmp_path / "E21_EVIDENCE_INDEX.json").exists()
    assert (tmp_path / "E21_MODE_PARITY_MATRIX.md").exists()
    assert (tmp_path / "E21_SCENARIO_COVERAGE.md").exists()
    assert (tmp_path / "E21_FAILURE_DRILLS_REPORT.md").exists()
    assert (tmp_path / "E21_NON_INTERFERENCE_PROOF.md").exists()
