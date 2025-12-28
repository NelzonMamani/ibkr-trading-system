from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from core.event_collector import EventCollector
from core.events import SystemEvent


def _dummy_event(event_type: str) -> SystemEvent:
    return SystemEvent(
        event_type=event_type,
        source="TestSuite",
        payload={},
    )


def test_cycle_clear_does_not_clear_all():
    collector = EventCollector()
    collector.record(_dummy_event("E1"))
    collector.record(_dummy_event("E2"))

    assert len(collector.snapshot_cycle()) == 2
    assert len(collector.snapshot_all()) == 2

    collector.clear_cycle()

    assert len(collector.snapshot_cycle()) == 0
    assert len(collector.snapshot_all()) == 2


def test_record_appends_to_both_stores():
    collector = EventCollector()
    collector.record(_dummy_event("E1"))

    assert len(collector.snapshot_cycle()) == 1
    assert len(collector.snapshot_all()) == 1


def test_multiple_cycles_accumulate_all_but_not_cycle():
    collector = EventCollector()

    collector.clear_cycle()
    collector.record(_dummy_event("A1"))
    collector.record(_dummy_event("A2"))
    assert len(collector.snapshot_cycle()) == 2
    assert len(collector.snapshot_all()) == 2

    collector.clear_cycle()
    collector.record(_dummy_event("B1"))
    collector.record(_dummy_event("B2"))
    collector.record(_dummy_event("B3"))
    assert len(collector.snapshot_cycle()) == 3
    assert len(collector.snapshot_all()) == 5
