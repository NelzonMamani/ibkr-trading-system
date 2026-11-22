from contextlib import closing
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/diagnostics/ross_paper_ownership_join.py"
spec = importlib.util.spec_from_file_location("join", SCRIPT)
join = importlib.util.module_from_spec(spec)
spec.loader.exec_module(join)

FLEX = """BOF,FIXTURE-ACCOUNT,Fixture,4,20260525,20261120
BOS,POST,Open Positions
ClientAccountID,Conid,Symbol,Quantity,ReportDate
FIXTURE-ACCOUNT,201,FIX-A,2,20261120
FIXTURE-ACCOUNT,202,FIX-B,1,20261120
FIXTURE-ACCOUNT,203,FIX-C,3,20261120
FIXTURE-ACCOUNT,204,FIX-D,4,20261120
FIXTURE-ACCOUNT,205,FIX-E,5,20261120
EOS,POST,5
BOS,TRNT,Trades
ClientAccountID,Conid,Symbol,Quantity,ReportDate,IBOrderID,IBExecID,OrderReference,TradePrice
EOS,TRNT,0
BOS,CORP,Corporate Actions
ClientAccountID,Conid,Symbol,Quantity,ActionID,TransactionID,Type,Date/Time,Report Date,ActionDescription
FIXTURE-ACCOUNT,101,FIX-A-OLD,-16,FIX-SPLIT-A,FIX-T-A1,RS,20261002;093000,20261005,Reverse split 1 for 8
FIXTURE-ACCOUNT,201,FIX-A,2,FIX-SPLIT-A,FIX-T-A2,RS,20261002;093000,20261005,Reverse split 1 for 8
FIXTURE-ACCOUNT,102,FIX-B-OLD,-9,FIX-SPLIT-B,FIX-T-B1,RS,20261113;093000,20261116,Reverse split 1 for 9
FIXTURE-ACCOUNT,202,FIX-B,1,FIX-SPLIT-B,FIX-T-B2,RS,20261113;093000,20261116,Reverse split 1 for 9
EOS,CORP,4
BOS,TRFR,Transfers
ClientAccountID,Conid,Symbol,Quantity,ReportDate
EOS,TRFR,0
EOF
"""


def snapshot_entry(alias, digest):
    return {"alias": alias, "source_path": "PRIVATE-FIXTURE-PATH", "references": [],
            "historical_startup_modes": ["READ_ONLY"], "sidecars_present": [],
            "tables": ["events", "runs"], "paper_runs": {"run_mode": 1},
            "paper_native_state_rows": 0, "status": "verified",
            "sha256": digest, "snapshot": f"{alias}.sqlite3"}


def write_journal(path, events):
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("CREATE TABLE runs(run_id,run_mode)")
        db.executemany("INSERT INTO runs VALUES (?,?)", [("R", "PAPER"), ("RO", "READ_ONLY"), ("S", "SIM")])
        db.execute("CREATE TABLE events(run_id,event_type,source,payload_json)")
        db.executemany("INSERT INTO events VALUES (?,?,?,?)", events)
        db.execute("CREATE TABLE execution_results(run_id,status,payload_json)")
        db.execute("INSERT INTO execution_results VALUES (?,?,?)",
                   ("R", "SIMULATED", json.dumps({"client_order_id": join.ROSS_REF + "synthetic-ref"})))


def exec_row(conid, execution_id, run_id="R", source="IBKR", reference=""):
    callback = {"execution": {"execId": execution_id, "acctNumber": "FIXTURE-ACCOUNT", "shares": 2,
                              "side": "BOT", "price": 3, "permId": conid, "orderRef": reference},
                "contract": {"conId": conid}}
    return run_id, "execDetails", source, json.dumps(callback)


class OfflineJoin(unittest.TestCase):
    def test_account_wrapped_flex_matches_unwrapped_report(self):
        wrapped = FLEX.replace("BOS,POST", "BOA,FIXTURE-ACCOUNT\nBOS,POST", 1).replace(
            "EOF\n", "EOA,FIXTURE-ACCOUNT\nEOF\n", 1)
        self.assertEqual(join.broker_sections(wrapped), join.broker_sections(FLEX))

    def test_account_wrapper_pairing_and_identity_refuse(self):
        wrapped = FLEX.replace("BOS,POST", "BOA,FIXTURE-ACCOUNT\nBOS,POST", 1).replace(
            "EOF\n", "EOA,FIXTURE-ACCOUNT\nEOF\n", 1)
        for old, new in [
            ("BOA,FIXTURE-ACCOUNT", "BOA,OTHER-ACCOUNT"),
            ("BOA,FIXTURE-ACCOUNT", "BOA"),
            ("BOA,FIXTURE-ACCOUNT", "BOA,FIXTURE-ACCOUNT,EXTRA"),
            ("BOA,FIXTURE-ACCOUNT\n", ""),
            ("BOA,FIXTURE-ACCOUNT\n", "BOA,FIXTURE-ACCOUNT\nBOA,FIXTURE-ACCOUNT\n"),
            ("EOA,FIXTURE-ACCOUNT", "EOA,OTHER-ACCOUNT"),
            ("EOA,FIXTURE-ACCOUNT", "EOA"),
            ("EOA,FIXTURE-ACCOUNT", "EOA,FIXTURE-ACCOUNT,EXTRA"),
            ("EOA,FIXTURE-ACCOUNT\n", ""),
            ("EOA,FIXTURE-ACCOUNT\n", "EOA,FIXTURE-ACCOUNT\nEOA,FIXTURE-ACCOUNT\n"),
            ("EOA,FIXTURE-ACCOUNT\nEOF\n", "EOF\nEOA,FIXTURE-ACCOUNT\n"),
        ]:
            with self.subTest(old=old, new=new), self.assertRaises(join.EvidenceError):
                join.broker_sections(wrapped.replace(old, new, 1))

    def test_flex_envelope_and_empty_sections(self):
        report = join.broker_sections(FLEX)
        self.assertEqual([len(report[key]) for key in join.FLEX_SECTIONS.values()], [5, 0, 4, 0])
        self.assertEqual(report["statement"]["from"], "20260525")
        self.assertEqual(report["statement"]["to"], "20261120")
        self.assertEqual(report["openpositions"][0]["conid"], "201")

    def test_invalid_flex_framing(self):
        for old, new in [
            ("BOF,", "BOG,"), ("Fixture,4,", "Fixture,3,"), ("20260525,", "20261325,"),
            ("BOS,TRNT", "BOS,POST"), ("EOS,TRNT,0", "EOS,TRNT,1"), ("EOS,TRFR,0", "EOS,TRNT,0"),
            ("EOS,CORP,4\n", ""), ("FIX-A,2,20261120", "FIX-A,2"),
            ("Symbol,Quantity,ReportDate", "Quantity,Quantity,ReportDate"),
            ("EOF\n", ""), ("EOF\n", "EOF\n\n"),
        ]:
            with self.subTest(old=old, new=new), self.assertRaises(join.EvidenceError):
                join.broker_sections(FLEX.replace(old, new, 1))

    def test_split_pair_controls(self):
        report = join.broker_sections(FLEX)
        for index, alias in enumerate(("P01", "P02")):
            result, gap = join.corporate_action(join.split_pairs(report), report["openpositions"][index], alias)
            self.assertEqual(gap, "")
            self.assertNotEqual(result[0]["reportdate"], result[0]["datetime"][:8])
        for field, replacement in [
            ("quantity", "-2"), ("quantity", "4"), ("conid", "101"), ("actionid", ""),
            ("type", "TC"), ("transactionid", "FIX-T-A1"), ("transactionid", ""),
            ("datetime", "20261002;100000"), ("datetime", "20261005;093000"),
            ("clientaccountid", "OTHER-ACCOUNT"), ("actiondescription", "1 for 9"),
        ]:
            report = join.broker_sections(FLEX)
            report["corporateactions"][1][field] = replacement
            with self.subTest(field=field, replacement=replacement):
                verdict = join.join_positions(report, {}, {}, {})["P01"]
                self.assertEqual(verdict["corporate_action_continuity"], "unresolved")
        report = join.broker_sections(FLEX)
        report["openpositions"][0]["quantity"] = "3"
        self.assertIsNone(join.corporate_action(join.split_pairs(report), report["openpositions"][0], "P01")[0])
        report = join.broker_sections(FLEX)
        report["corporateactions"] += [dict(row, actionid="DUP-ACTION", transactionid=row["transactionid"] + "-2")
                                      for row in report["corporateactions"][:2]]
        self.assertIn("Multiple", join.corporate_action(join.split_pairs(report), report["openpositions"][0], "P01")[1])

    def test_collection_to_aliased_output_without_flex_trades(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot = root / "D002.sqlite3"
            order = {"account": "FIXTURE-ACCOUNT", "permId": 101, "orderRef": join.ROSS_REF + "actual-ref"}
            write_journal(snapshot, [
                ("R", "openOrder", "IBKR", json.dumps({"order": order})),
                exec_row(101, "ACTUAL-E"), exec_row(101, "ACTUAL-E"),
                exec_row(203, "SIM-MODE-E", run_id="S", reference=join.ROSS_REF + "sim-mode"),
                exec_row(203, "SIM-SOURCE-E", source="synthetic", reference=join.ROSS_REF + "sim-source"),
                exec_row(204, "READ-ONLY-E", run_id="RO", reference=join.ROSS_REF + "read-only"),
                exec_row(204, "UNKNOWN-SOURCE-E", source="unverified", reference=join.ROSS_REF + "unknown"),
            ])
            shutil.copyfile(snapshot, root / "D001.sqlite3")
            later = root / "D004.sqlite3"
            write_journal(later, [exec_row(101, "ACTUAL-E"), exec_row(205, "OTHER-E")])
            digest = join.sha256(snapshot)
            manifest = {"databases": [
                snapshot_entry("D001", digest), snapshot_entry("D002", digest),
                {"alias": "D003", "status": "refused", "gap": "PRIVATE-REFUSAL"},
                snapshot_entry("D004", join.sha256(later)), snapshot_entry("D005", "a" * 64),
                snapshot_entry("D006", digest),
            ], "gaps": ["PRIVATE-DISCOVERY-GAP"], "broker_report": "sha256_match"}
            shutil.copyfile(later, root / "D005.sqlite3")
            shutil.copyfile(snapshot, root / "D006.sqlite3")
            (root / "D006.sqlite3-wal").touch()
            (root / "PRIVATE_MANIFEST.json").write_text(json.dumps(manifest))
            broker = root / "broker.csv"
            broker.write_text(FLEX, encoding="utf-8")
            share = join.run(root, broker, join.sha256(broker))
            self.assertEqual(join.sha256(snapshot), digest)
            self.assertEqual(share["snapshots"]["D001"], {"same_image_as": "D002"})
            self.assertIn("runs lacks effective_run_mode.", share["snapshots"]["D002"]["schema_gaps"])
            self.assertEqual(share["snapshots"]["D005"]["gap"], "Snapshot SHA256 mismatch.")
            self.assertIn("refused", share["snapshots"]["D003"]["gap"])
            self.assertIn("sidecar", share["snapshots"]["D006"]["gap"])
            self.assertEqual(share["discovery_gap_count"], 1)
            self.assertEqual(share["broker_trade_rows"], 0)
            p01 = share["positions"]["P01"]
            self.assertEqual(p01["corporate_action_continuity"], "paired_broker_action_legs_supported")
            self.assertEqual(p01["broker_acquisition"], "unresolved")
            self.assertEqual(p01["journal_only_candidates"]["count"], 1)
            self.assertEqual(p01["journal_only_candidates"]["supporting_ross_attribution"], 1)
            self.assertEqual(p01["journal_only_candidates"]["sources"], [
                ("D002", "retained_exec_details", "paper_legacy_run_mode"),
                ("D004", "retained_exec_details", "paper_legacy_run_mode"),
            ])
            self.assertEqual(share["positions"]["P03"]["journal_only_candidates"]["count"], 0)
            self.assertEqual(share["positions"]["P04"]["journal_only_candidates"]["count"], 2)
            self.assertEqual(share["positions"]["P04"]["journal_only_candidates"]["supporting_ross_attribution"], 0)
            self.assertEqual(share["positions"]["P05"]["journal_only_candidates"]["count"], 1)
            for position in share["positions"].values():
                self.assertEqual(position["open_position_ownership"], "unresolved")
            for private in ("FIXTURE-ACCOUNT", "ACTUAL-E", "FIX-A", "PRIVATE-REFUSAL", "PRIVATE-DISCOVERY-GAP"):
                self.assertNotIn(private, json.dumps(share))
            private = json.loads(next(root.glob("ownership-join-*/PRIVATE_JOIN.json")).read_text())
            self.assertEqual(private["positions"]["P01"]["split_legs"][0]["conid"], "101")
            self.assertEqual(share["PAPER_READY"], "NO")
            with self.assertRaisesRegex(join.EvidenceError, "SHA256 mismatch"):
                join.run(root, broker, hashlib.sha256(b"other").hexdigest())

    def test_manifest_contract_refuses_wrong_shapes(self):
        for change in [
            {"snapshot": "../D002.sqlite3"}, {"snapshot": r"C:\Users\fixture\D002.sqlite3"},
            {"snapshot": "D001.sqlite3"}, {"sha256": "wrong"}, {"status": "complete"}, {"references": None, "tables": None},
        ]:
            entry = snapshot_entry("D002", "a" * 64)
            entry.update(change)
            with self.subTest(change=change), self.assertRaises(join.EvidenceError):
                join.validate_manifest({"databases": [entry], "gaps": [], "broker_report": "sha256_match"})
        with self.assertRaises(join.EvidenceError):
            join.validate_manifest({"databases": []})

    def test_broker_trade_confirmation_and_conflicting_duplicates(self):
        report = join.broker_sections(FLEX)
        row = {"clientaccountid": "FIXTURE-ACCOUNT", "conid": "203", "quantity": "2",
               "tradeprice": "3", "ibexecid": "E1", "orderreference": join.ROSS_REF + "synthetic-ref"}
        report["trades"] = [row, row]
        result_sources = {row["orderreference"]: {("D002", True)}}
        private = {}
        p03 = join.join_positions(report, {}, result_sources, private)["P03"]
        self.assertEqual(len(private["P03"]["matched_acquisitions"]), 1)
        self.assertEqual(p03["broker_acquisition"], "reported")
        self.assertEqual(p03["ross_attribution"], "unresolved")
        report["trades"].append(dict(row, tradeprice="4"))
        self.assertEqual(join.join_positions(report, {}, {}, {})["P03"]["broker_acquisition"], "unresolved")

    def test_committed_lifecycle_requires_execution_link(self):
        row = {"event_type": "ENTRY_FILL", "execution_id": "E", "run_id": "R",
               "lifecycle_trade_id": "T", "symbol": "FAKE", "quantity": 2, "price": 3, "order_id": "10",
               "source": "native_cached_fill",
               "payload_json": json.dumps({"native_feedback_committed": True, "native_identity": {
                   "account": "A", "con_id": 1, "symbol": "FAKE", "native_order_id": "10",
                   "strategy_name": "ROSS_MOMENTUM"}})}
        trade = {"run_id": "R", "lifecycle_trade_id": "T", "strategy_name": "ROSS_MOMENTUM"}
        tables = {"trade_lifecycle_events": [row], "trade_lifecycle_trades": [trade]}
        self.assertEqual(list(join.journal_fills(tables)), [])
        trade["source_execution_ids_json"] = '["E"]'
        self.assertTrue(list(join.journal_fills(tables))[0]["native"])
        row["source"] = "synthetic"
        self.assertEqual(list(join.journal_fills(tables)), [])


if __name__ == "__main__":
    unittest.main()
