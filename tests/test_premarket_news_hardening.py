from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.prep.premarket_prep import _float_classification, _float_state, PreMarketPrepEngine


def test_float_classification_and_unknown_state() -> None:
    assert _float_classification(None) == "UNKNOWN_FLOAT"
    assert _float_classification(8_000_000) == "LOW_FLOAT"
    assert _float_classification(20_000_000) == "ROSS_SWEET_SPOT"
    assert _float_classification(40_000_000) == "MID_FLOAT"
    assert _float_classification(80_000_000) == "HIGH_FLOAT"


def test_float_state_age_buckets() -> None:
    now = datetime.now(timezone.utc)
    assert _float_state(None, None) == "FLOAT_UNKNOWN"
    assert _float_state(10_000_000, None) == "FLOAT_ESTIMATED"
    assert _float_state(10_000_000, now - timedelta(days=2)) == "FLOAT_CONFIRMED"
    assert _float_state(10_000_000, now - timedelta(days=20)) == "FLOAT_ESTIMATED"


def test_artifact_payload_contains_hardened_packets_and_is_deterministic() -> None:
    engine = PreMarketPrepEngine()
    symbols = ["AAA", "BBB"]
    engine.update_from_universe(
        symbols,
        last_price_by_symbol={"AAA": 12.5, "BBB": 7.2},
        float_by_symbol={"AAA": 12_000_000, "BBB": None},
        prior_close_by_symbol={"AAA": 10.0, "BBB": 7.1},
        gap_pct_by_symbol={"AAA": 25.0, "BBB": 1.0},
        persisted_pct_change_by_symbol={"AAA": 25.0, "BBB": 1.0},
        persisted_rvol_by_symbol={"AAA": 3.5, "BBB": 0.8},
        persisted_volume_by_symbol={"AAA": 900_000, "BBB": 20_000},
        reason="TEST_HARDENING",
    )

    payload_1 = engine.build_artifact_payload(symbols)
    payload_2 = engine.build_artifact_payload(symbols)
    rows_1 = payload_1["symbols"]
    rows_2 = payload_2["symbols"]

    assert [r["symbol"] for r in rows_1] == [r["symbol"] for r in rows_2]
    assert all("catalyst_packet" in row for row in rows_1)
    assert all("premarket_structure_packet" in row for row in rows_1)
    assert all("score_breakdown" in row for row in rows_1)
    assert all("terminal_state" in row for row in rows_1)
    assert all("watchlist_rank" in row for row in rows_1)

    by_symbol = {row["symbol"]: row for row in rows_1}
    assert by_symbol["BBB"]["float_state"] == "FLOAT_UNKNOWN"
    assert by_symbol["BBB"]["terminal_state"] in {"NOT_READY_NO_CATALYST", "NOT_READY_FLOAT_UNKNOWN"}
