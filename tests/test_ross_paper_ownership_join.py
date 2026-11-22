import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("join", "scripts/diagnostics/ross_paper_ownership_join.py")
join = importlib.util.module_from_spec(spec)
spec.loader.exec_module(join)


class OfflineJoin(unittest.TestCase):
    def test_collection_to_aliased_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot = root / "first.sqlite"
            db = sqlite3.connect(snapshot)
            db.execute("CREATE TABLE execution_results(status,payload_json)")
            db.execute("INSERT INTO execution_results VALUES (?,?)",
                       ("SIMULATED", json.dumps({"client_order_id": join.ROSS_REF + "synthetic-ref"})))
            db.execute("CREATE TABLE runs(run_id,run_mode)")
            db.execute("INSERT INTO runs VALUES ('fixture-run','PAPER')")
            db.execute("CREATE TABLE events(event_type,payload_json)")
            callback = {"execution": {"execId": "ACTUAL-E", "acctNumber": "PRIVATE-ACCT", "shares": 2,
                                       "side": "BOT", "price": 3, "permId": 101},
                        "contract": {"conId": 2}}
            order = {"account": "PRIVATE-ACCT", "permId": 101, "orderRef": join.ROSS_REF + "actual-ref"}
            db.execute("INSERT INTO events VALUES (?,?)", ("openOrder", json.dumps({"order": order})))
            db.executemany("INSERT INTO events VALUES (?,?)", [("execDetails", json.dumps(callback))] * 2)
            db.commit()
            db.close()
            duplicate = root / "second.sqlite"
            shutil.copyfile(snapshot, duplicate)
            snapshot_hash = join.sha256(snapshot)
            (root / "PRIVATE_MANIFEST.json").write_text(json.dumps({"databases": [
                {"alias": "D001", "snapshot_path": duplicate.name, "snapshot_sha256": snapshot_hash},
                {"alias": "D002", "snapshot_path": snapshot.name, "snapshot_sha256": snapshot_hash},
                {"alias": "D003", "snapshot_path": snapshot.name, "snapshot_sha256": "a" * 64}
            ]}))
            broker = root / "broker.csv"
            broker.write_text(
                "Open Positions,Header,Account,Conid,Quantity\n"
                + "".join(f"Open Positions,Data,PRIVATE-ACCT,{n},2\n" for n in [9, 2, 3, 4, 5])
                + "Trades,Header,Account,Conid,Quantity,T. Price,Exec ID,Order Ref,Is API Order\n"
                + "Trades,Data,PRIVATE-ACCT,2,2,3,ACTUAL-E,,Yes\n" * 2
                + f"Trades,Data,PRIVATE-ACCT,3,2,3,SIM-E,{join.ROSS_REF}synthetic-ref,Yes\n"
                + "Trades,Data,PRIVATE-ACCT,6,2,3,PREDECESSOR-E,,Yes\n"
                + "Corporate Actions,Header,Account,Conid,Action ID,Quantity\n"
                + "Corporate Actions,Data,PRIVATE-ACCT,6,CA-1,-2\n"
                + "Corporate Actions,Data,PRIVATE-ACCT,9,CA-1,2\n"
            )
            (root / "PRIVATE_CONTRACT_BINDINGS.json").write_text(json.dumps({"P01": {
                "document_reference": "fixture-doc",
                "predecessor": ["PRIVATE-ACCT", "6"], "successor": ["PRIVATE-ACCT", "9"],
            }}))
            share = join.run(root, broker, join.sha256(broker))
            self.assertEqual(join.sha256(snapshot), snapshot_hash)
            self.assertEqual(share["snapshots"]["D001"], {"same_image_as": "D002"})
            self.assertIn("runs lacks effective_run_mode.", share["snapshots"]["D002"]["schema_gaps"])
            self.assertEqual(share["snapshots"]["D003"]["gap"], "Snapshot SHA256 mismatch.")
            self.assertEqual(share["positions"]["P01"]["corporate_action_continuity"], "paired_broker_action_legs_supported")
            self.assertEqual(share["positions"]["P02"]["ross_attribution"], "supported_for_all_matching_acquisitions")
            self.assertEqual(share["positions"]["P03"]["broker_acquisition"], "reported")
            self.assertEqual(share["positions"]["P03"]["ross_attribution"], "unresolved")
            self.assertEqual(share["positions"]["P04"]["broker_acquisition"], "unresolved")
            self.assertNotIn("PRIVATE-ACCT", json.dumps(share))
            self.assertNotIn("ACTUAL-E", json.dumps(share))
            private = json.loads(next(root.glob("ownership-join-*/PRIVATE_JOIN.json")).read_text())
            self.assertEqual(len(private["positions"]["P02"]["matched_acquisitions"]), 1)
            self.assertEqual(share["PAPER_READY"], "NO")
            with self.assertRaisesRegex(join.EvidenceError, "SHA256 mismatch"):
                join.run(root, broker, hashlib.sha256(b"other").hexdigest())

    def test_conflict_and_activity_contract_lookup(self):
        sections = join.broker_sections(
            "Financial Instrument Information,Header,Asset Category,Symbol,Conid\n"
            "Financial Instrument Information,Data,Stocks,FAKE,123\n"
            "Trades,Header,Asset Category,Symbol,Currency,Quantity,Exec ID,Account,T. Price\n"
            "Trades,Data,Stocks,FAKE,USD,2,E1,LOCAL,3\n"
            "Trades,Data,Stocks,FAKE,USD,2,E1,LOCAL,4\n"
        )
        join.bind_report_contracts(sections)
        self.assertEqual(join.contract(sections["trades"][0]), ("LOCAL", "123"))
        variants = join.index_broker_trades(sections["trades"], "")
        self.assertEqual(len(variants), 1)
        self.assertEqual(len(next(iter(variants.values()))), 2)

    def test_committed_lifecycle_requires_execution_link(self):
        row = {"event_type": "ENTRY_FILL", "execution_id": "E", "run_id": "R",
               "lifecycle_trade_id": "T", "symbol": "FAKE", "quantity": 2, "price": 3, "order_id": "10",
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
