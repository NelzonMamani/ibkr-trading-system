"""Offline review of collector snapshots and a locally verified IBKR report.

Uses the SQLiteStore and StorageEngine read-side column contracts without
importing application modules. The review never authorizes position adoption.
"""
import argparse
from collections import defaultdict
from contextlib import closing
import csv
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
from pathlib import Path
import re
import sqlite3
import sys
import uuid


BROKER_SHA256 = "195bbf42d305a029618412c65933190faa8734ef9add6b634275857054bf236c"
ROSS_REF = "TRADING_OS|ROSS_MOMENTUM|"
ROSS = {"ROSS_MOMENTUM", "ROSS_CAMERON_MOMENTUM"}
JOURNAL = {
    "runs": ("run_id", "effective_run_mode"),
    "execution_results": ("run_id", "status", "payload_json"),
    "events": ("run_id", "event_type", "payload_json"),
    "trade_lifecycle_events": ("run_id", "execution_id", "payload_json"),
    "trade_lifecycle_trades": ("run_id", "strategy_name", "source_execution_ids_json"),
    "position_lifecycle_transitions": ("entry_order_id", "strategy_owner"),
    "capital_owner_execution": ("scope", "identity", "payload"),
    "trade_records": ("run_id", "cycle_id", "execution_output_json"),
    "trades": ("run_id", "symbol"),
}
SNAPSHOT_ALIAS = re.compile(r"D[0-9]{3}")


class EvidenceError(Exception):
    """Message must be safe for the shareable error output."""


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, default=str)


def value(mapping, *keys):
    for key in keys:
        item = mapping.get(key)
        if item is not None and not isinstance(item, (dict, list, bool)):
            result = str(item).strip()
            if result and result not in {"-", "--", "N/A"}:
                return result
    return ""


def obj(value):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return {}
    return value if isinstance(value, dict) else {}


def sha256(path):
    with path.open("rb") as stream:
        digest = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
        return digest.hexdigest()


def decimal(value):
    try:
        number = Decimal(str(value).replace(",", ""))
        return number if number.is_finite() else None
    except InvalidOperation:
        return None


def positive(value):
    number = decimal(value)
    return number if number is not None and number > 0 else None


def header_key(value):
    return re.sub(r"[^a-z0-9]", "", value.lower())


def broker_sections(report):
    sections = defaultdict(list)
    headers = {}
    for row in csv.reader(io.StringIO(report, newline=""), strict=True):
        if len(row) < 3:
            continue
        name, kind = map(header_key, row[:2])
        if kind == "header":
            headers[name] = [header_key(column) for column in row[2:]]
        elif kind == "data" and name in headers:
            if len(headers[name]) != len(row[2:]):
                raise EvidenceError("Broker report contains a section row with a mismatched header width.")
            fields = {}
            for key, item in zip(headers[name], row[2:]):
                if key and key in fields:
                    raise EvidenceError("Broker report contains ambiguous section columns.")
                fields[key] = item.strip()
            sections[name].append(fields)
    return sections


def contract(row, default_account=""):
    account = value(row, "clientaccountid", "accountid", "account", "acctid") or default_account
    return account, value(row, "conid", "contractid", "reportinstrumentconid")


def bind_report_contracts(sections):
    """Resolve Activity CSV instrument labels against the report's instrument table."""
    instruments = defaultdict(set)
    for row in sections.get("financialinstrumentinformation", []):
        identifier = value(row, "conid", "contractid")
        category = value(row, "assetcategory", "assetclass")
        currency = value(row, "currency")
        # The report can list multiple labels for a single contract.
        for symbol in value(row, "symbol").split(","):
            if symbol.strip() and identifier and category:
                instruments[(category, symbol.strip())].add((currency, identifier))
    for section in ("openpositions", "trades", "corporateactions"):
        for row in sections.get(section, []):
            if contract(row)[1]:
                continue
            category = value(row, "assetcategory", "assetclass")
            symbol = value(row, "symbol")
            currency = value(row, "currency")
            matches = {identifier for candidate_currency, identifier in instruments[(category, symbol)]
                       if not candidate_currency or candidate_currency == currency}
            if len(matches) == 1:
                row["reportinstrumentconid"] = matches.pop()


def trade_side(row):
    side = value(row, "buysell", "side").upper()
    if side:
        return {"BOT": "BUY", "SLD": "SELL"}.get(side, side)
    quantity = decimal(value(row, "quantity"))
    if quantity:
        return "BUY" if quantity > 0 else "SELL"
    return ""


def index_broker_trades(rows, default_account):
    """Keep one projection per exact execution identity and surface conflicts."""
    by_identity = defaultdict(dict)
    for row in rows:
        discriminator = value(row, "datadiscriminator", "levelofdetail").upper()
        if discriminator in {"SUMMARY", "ORDERSUMMARY", "SYMBOLSUMMARY", "LOT", "CLOSEDLOT"}:
            continue
        if discriminator == "ORDER" and not value(row, "tradeid", "transactionid", "ibexecid", "execid", "executionid"):
            # An Activity order-level row can evidence a broker-reported trade.
            # It cannot establish individual execution identity.
            identity = ("order_row", canonical(row))
        else:
            account, _ = contract(row, default_account)
            execution = value(row, "ibexecid", "ibexecutionid", "execid", "executionid")
            transaction = value(row, "tradeid", "transactionid")
            identity = (("execution", account, execution) if execution else
                        ("trade", account, transaction) if transaction else ("row", canonical(row)))
        signature = (
            contract(row, default_account), trade_side(row),
            decimal(value(row, "quantity")), decimal(value(row, "tradeprice", "tprice", "price")),
            value(row, "datetime", "tradedatetime", "tradedate"),
            value(row, "orderreference", "orderref"), value(row, "iborderid", "brokerorderid"),
        )
        by_identity[identity][signature] = row
    return by_identity


def selected_snapshots(root, manifest):
    entries = manifest.get("databases", manifest.get("snapshots"))
    if not isinstance(entries, list):
        raise EvidenceError("Collector manifest snapshot list is absent or unsupported.")
    entries = [{header_key(key): item for key, item in entry.items()} if isinstance(entry, dict) else {}
               for entry in entries]
    seen = set()
    for entry in entries:
        alias = entry.get("alias") if isinstance(entry, dict) else None
        if not isinstance(alias, str) or not SNAPSHOT_ALIAS.fullmatch(alias) or alias in seen:
            raise EvidenceError("Collector manifest has invalid or repeated snapshot aliases.")
        seen.add(alias)
    if "D002" not in seen:
        raise EvidenceError("Collector manifest is missing D002.")
    for entry in sorted(entries, key=lambda item: (item["alias"] != "D002", item["alias"])):
        alias = entry["alias"]
        if value(entry, "status").lower() not in {"", "verified"} or entry.get("verified") is False:
            yield alias, None, "Collector reports an unverified snapshot."
            continue
        nested = entry.get("snapshot")
        nested = {header_key(key): item for key, item in nested.items()} if isinstance(nested, dict) else {}
        image = (value(entry, "snapshotpath", "snapshot", "relativepath", "snapshotrelativepath", "snapshotfile")
                 or value(nested, "path", "relativepath", "file"))
        expected = (value(entry, "snapshotsha256", "sha256") or value(nested, "sha256")).lower()
        if not image or not re.fullmatch(r"[a-f0-9]{64}", expected):
            yield alias, None, "Snapshot path or expected hash absent."
            continue
        try:
            path = (root / image).resolve(strict=True)
            path.relative_to(root)
            if not path.is_file() or any(path.with_name(path.name + ext).exists()
                                        for ext in ("-wal", "-journal", "-shm")):
                raise ValueError
            if sha256(path) != expected:
                yield alias, None, "Snapshot SHA256 mismatch."
                continue
        except (OSError, ValueError):
            yield alias, None, "Snapshot unavailable inside collection or SQLite sidecar present."
            continue
        yield alias, (path, expected), None


def journal_rows(path):
    uri = path.as_uri() + "?mode=ro&immutable=1"
    with closing(sqlite3.connect(uri, uri=True)) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        db.execute("PRAGMA trusted_schema=OFF")
        tables = {row[0] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND lower(sql) LIKE 'create table%'"
        )}
        data = {}
        gaps = []
        for table, required in JOURNAL.items():
            if table not in tables:
                gaps.append(f"{table} absent.")
                continue
            cursor = db.execute(f'SELECT * FROM "{table}"')
            columns = {item[0] for item in cursor.description}
            missing = [column for column in required if column not in columns]
            if missing:
                gaps.append(f"{table} lacks {', '.join(missing)}.")
            data[table] = [dict(row) for row in cursor]
        return data, gaps


def simulated(row, payload):
    fields = ("status", "source", "event_type", "mode", "fill_status", "gateway_decision")
    return any(re.search(r"SIMULAT|SYNTH|MOCK|TEST_FILL|DRY_RUN|REPLAY", value(record, field).upper())
               for record in (row, payload) for field in fields)


def journal_fills(data):
    """Collect independently usable account, contract and exact execution bindings."""
    trades = {(row.get("run_id"), row.get("lifecycle_trade_id")): row
              for row in data.get("trade_lifecycle_trades", []) if row.get("lifecycle_trade_id")}
    order_refs = defaultdict(set)
    for row in data.get("events", []):
        payload = obj(row.get("payload_json"))
        kind = value(payload, "event_type") or value(row, "event_type")
        if kind not in {"openOrder", "completedOrder"} or simulated(row, payload):
            continue
        order = obj(payload.get("order"))
        account = value(order, "account")
        permanent_id = value(order, "permId")
        reference = value(order, "orderRef")
        if account and permanent_id.isdecimal() and int(permanent_id) > 0 and reference:
            order_refs[(account, permanent_id)].add(reference)

    for row in data.get("events", []):
        payload = obj(row.get("payload_json"))
        kind = value(payload, "event_type") or value(row, "event_type")
        if kind != "execDetails" or simulated(row, payload):
            continue
        execution = obj(payload.get("execution"))
        security = obj(payload.get("contract"))
        account = value(execution, "acctNumber") or value(payload, "account")
        refs = set(order_refs.get((account, value(execution, "permId")), set()))
        explicit_ref = value(execution, "orderRef") or value(payload, "orderRef", "order_ref")
        if explicit_ref:
            refs.add(explicit_ref)
        yield {
            "exec": value(execution, "execId", "exec_id") or value(payload, "execId", "exec_id"),
            "account": account,
            "conid": value(security, "conId") or value(payload, "conId", "con_id"),
            "qty": positive(value(execution, "shares") or value(payload, "shares")),
            "price": positive(value(execution, "price") or value(payload, "price")),
            "side": {"BOT": "BUY", "SLD": "SELL"}.get(value(execution, "side") or value(payload, "side"), ""),
            "refs": sorted(refs),
            "native": False,
        }
    for row in data.get("trade_lifecycle_events", []):
        payload = obj(row.get("payload_json"))
        identity = obj(payload.get("native_identity"))
        trade = trades.get((row.get("run_id"), row.get("lifecycle_trade_id")), {})
        if (row.get("event_type") != "ENTRY_FILL" or payload.get("native_feedback_committed") is not True
                or simulated(row, payload) or not trade):
            continue
        try:
            linked = json.loads(trade.get("source_execution_ids_json") or "null")
        except ValueError:
            linked = None
        execution_id = value(row, "execution_id")
        if not execution_id or not isinstance(linked, list) or execution_id not in linked:
            continue
        strategy = header_key(value(trade, "strategy_name"))
        if (strategy != header_key(value(identity, "strategy_name"))
                or value(identity, "symbol") != value(row, "symbol")
                or value(identity, "native_order_id") != value(row, "order_id")):
            continue
        yield {
            "exec": execution_id, "account": value(identity, "account"),
            "conid": value(identity, "con_id"), "qty": positive(row.get("quantity")),
            "price": positive(row.get("price")), "side": "BUY", "refs": [],
            "native": strategy in {header_key(name) for name in ROSS},
        }


def ross_ref(reference):
    return reference.startswith(ROSS_REF) and bool(reference[len(ROSS_REF):].strip())


def collect_journals(root, manifest, private):
    joins = defaultdict(dict)
    results_by_ref = defaultdict(set)
    images = {}
    results = {}
    for alias, image, gap in selected_snapshots(root, manifest):
        if gap:
            results[alias] = {"gap": gap}
            continue
        path, digest = image
        if digest in images:
            results[alias] = {"same_image_as": images[digest]}
            continue
        try:
            rows, gaps = journal_rows(path)
            if sha256(path) != digest:
                raise EvidenceError("Snapshot changed during inspection.")
        except (OSError, sqlite3.Error, EvidenceError):
            results[alias] = {"gap": "Verified image could not be inspected consistently."}
            continue
        images[digest] = alias
        private[alias] = {"path": str(path), "schema_gaps": gaps, "records": rows}
        for fill in journal_fills(rows):
            if fill["account"] and fill["exec"]:
                key = (fill["account"], fill["exec"])
                joins[key].setdefault(canonical(fill), (fill, set()))[1].add(alias)
        for row in rows.get("execution_results", []):
            payload = obj(row.get("payload_json"))
            ref = value(payload, "order_ref", "orderRef", "client_order_id")
            if ref:
                results_by_ref[ref].add((alias, simulated(row, payload)))
        results[alias] = {"schema_gaps": gaps}
    return joins, results_by_ref, results


def evidence_for(row, account, conid, journals, results_by_ref):
    exec_id = value(row, "ibexecid", "ibexecutionid", "execid", "executionid")
    qty = decimal(value(row, "quantity"))
    price = positive(value(row, "tradeprice", "tprice", "price"))
    if qty is None or not qty or price is None or trade_side(row) != "BUY":
        return False, False, "Positive broker acquisition fields are absent."
    candidates = list(journals.get((account, exec_id), {}).values()) if exec_id else []
    signature = (conid, abs(qty), price, "BUY")
    complete = [(fill, aliases) for fill, aliases in candidates
                if fill["conid"] and fill["qty"] and fill["price"] and fill["side"]]
    if any((fill["conid"], fill["qty"], fill["price"], fill["side"]) != signature for fill, _ in complete):
        return True, False, "Retained evidence disagrees on execution facts."
    report_ref = value(row, "orderreference", "orderref")
    refs = {ref for fill, _ in complete for ref in fill["refs"]}
    if report_ref:
        refs.add(report_ref)
    if len(refs) > 1:
        return True, False, "Retained order references disagree."
    committed = any(fill["native"] for fill, _ in complete)
    callback_reference = any(ross_ref(ref) for fill, _ in complete for ref in fill["refs"])
    result_markers = {marker for ref in refs for _, marker in results_by_ref.get(ref, ())}
    if True in result_markers and not (committed or callback_reference):
        return True, False, "Matching order reference appears in simulated execution results without independent retained Ross fill support."
    if committed or callback_reference or ross_ref(report_ref):
        return True, True, ""
    if not exec_id:
        return True, False, "Broker trade lacks an execution ID and a Ross order reference."
    if not complete:
        return True, False, "No retained callback or committed lifecycle row binds the execution to this account and contract."
    return True, False, "Exact execution evidence lacks a Ross order reference or qualifying committed Ross lifecycle record."


def read_bindings(path):
    """Local transcription of documented contracts. See coordinator review notes."""
    bindings = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(bindings, dict) or set(bindings) - {"P01", "P02"}:
        raise EvidenceError("Private contract binding file has an unsupported shape.")
    for binding in bindings.values():
        if (not isinstance(binding, dict) or not value(binding, "document_reference")
                or any(not isinstance(binding.get(key), list) or len(binding[key]) != 2
                       or any(not isinstance(item, str) or not item.strip() for item in binding[key])
                       for key in ("predecessor", "successor"))
                or binding["predecessor"][0] != binding["successor"][0]
                or binding["predecessor"] == binding["successor"]):
            raise EvidenceError("Private contract binding lacks a same-account distinct contract pair or document reference.")
    return bindings


def corporate_action(sections, predecessor, successor, default_account):
    """Identify paired signed movements using an explicit broker action identifier."""
    grouped = defaultdict(dict)
    for row in sections.get("corporateactions", []):
        current = contract(row, default_account)
        if current not in {predecessor, successor}:
            continue
        action = value(row, "corporateactionid", "actionid")
        quantity = decimal(value(row, "quantity"))
        if action and quantity:
            grouped[action][canonical(row)] = (current, quantity)
    for legs in grouped.values():
        if len(legs) != 2:
            continue
        facts = dict(legs.values())
        if facts.get(predecessor, 0) < 0 < facts.get(successor, 0):
            return True
    return False


def join_positions(sections, journals, results_by_ref, private, bindings=None):
    bind_report_contracts(sections)
    positions = sections.get("openpositions", [])
    if len(positions) != 5:
        raise EvidenceError("Expected five Open Positions data rows in original report order.")
    account_rows = sections.get("accountinformation", [])
    accounts = {(value(row, "account", "accountid", "clientaccountid")
                 or (value(row, "fieldvalue") if header_key(value(row, "fieldname")) in
                     {"account", "accountid", "accountnumber"} else "")) for row in account_rows}
    accounts.discard("")
    default_account = min(accounts) if len(accounts) == 1 else ""
    trades = index_broker_trades(sections.get("trades", []), default_account)
    verdicts = {}
    for index, position in enumerate(positions, 1):
        alias = f"P{index:02}"
        current = contract(position, default_account)
        related = {current}
        continuity = "not_required_for_direct_contract_match"
        gaps = set()
        if index <= 2:
            continuity = "unresolved"
            predecessor = (bindings or {}).get(alias)
            if predecessor and tuple(predecessor["successor"]) == current:
                old = tuple(predecessor["predecessor"])
                related.add(old)
                if corporate_action(sections, old, current, default_account):
                    continuity = "paired_broker_action_legs_supported"
                else:
                    continuity = "documented_contracts_matched_action_legs_unverified"
                    gaps.add("No paired broker action identifier with signed predecessor and successor legs.")
            else:
                gaps.add("Documented predecessor/successor contract binding unavailable.")
        matched = []
        accepted = []
        supporting = []
        for variants in trades.values():
            candidates = [row for row in variants.values() if contract(row, default_account) in related]
            if len(variants) > 1 and candidates:
                gaps.add("Conflicting broker trade records share one identity.")
                continue
            for row in candidates:
                account, conid = contract(row, default_account)
                if not account or not conid:
                    continue
                if trade_side(row) != "BUY":
                    continue
                acquired, attributed, gap = evidence_for(row, account, conid, journals, results_by_ref)
                if gap:
                    gaps.add(gap)
                if acquired:
                    matched.append(row)
                    accepted.append(attributed)
                    execution = value(row, "ibexecid", "ibexecutionid", "execid", "executionid")
                    supporting.append({
                        "broker_trade": row, "ross_attribution_supported": attributed,
                        "journal_facts": [{"facts": fill, "snapshots": sorted(aliases)}
                                          for fill, aliases in journals.get((account, execution), {}).values()],
                        "exact_reference_result_sources": sorted(
                            results_by_ref.get(value(row, "orderreference", "orderref"), set())),
                        "gap": gap,
                    })
        if not all(current):
            gaps.add("Open Positions row lacks exact account or contract ID.")
        if not matched:
            gaps.add("No broker acquisition matched by exact account and contract ID.")
        gaps.add("Open-lot attribution requires complete quantity, disposition and continuity evidence.")
        private[alias] = {"position": position, "matched_acquisitions": matched, "join_evidence": supporting}
        verdicts[alias] = {
            "broker_acquisition": "reported" if matched else "unresolved",
            "ross_attribution": "supported_for_all_matching_acquisitions" if accepted and all(accepted)
                                else "supported_for_some_matching_acquisitions" if any(accepted) else "unresolved",
            "corporate_action_continuity": continuity,
            "open_position_ownership": "unresolved",
            "gaps": sorted(gaps),
        }
    return verdicts


def write_json(path, data):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(data, stream, indent=2, default=str, ensure_ascii=True)
        stream.write("\n")


def run(root, broker, expected_hash=BROKER_SHA256):
    root = root.resolve(strict=True)
    manifest = json.loads((root / "PRIVATE_MANIFEST.json").read_text(encoding="utf-8-sig"))
    if not isinstance(manifest, dict):
        raise EvidenceError("Collector manifest must be a JSON object.")
    report = broker.read_bytes()
    if hashlib.sha256(report).hexdigest() != expected_hash:
        raise EvidenceError("Broker CSV SHA256 mismatch.")
    sections = broker_sections(report.decode("utf-8-sig"))
    private = {"manifest": manifest, "broker_path": str(broker.resolve()), "broker_sections": sections,
               "snapshots": {}, "positions": {}}
    journals, results_by_ref, snapshots = collect_journals(root, manifest, private["snapshots"])
    binding_file = root / "PRIVATE_CONTRACT_BINDINGS.json"
    bindings = None
    if binding_file.is_file():
        bindings = read_bindings(binding_file)
        private["documented_contract_bindings"] = bindings
    positions = join_positions(sections, journals, results_by_ref, private["positions"], bindings)
    share = {"PAPER_READY": "NO", "positions": positions, "snapshots": snapshots,
             "discovery": "Collector reported ten discovery gaps. Operative PAPER path remains unverified."}
    output = root / ("ownership-join-" + uuid.uuid4().hex)
    output.mkdir(mode=0o700)
    write_json(output / "PRIVATE_JOIN.json", private)
    write_json(output / "SHAREABLE_JOIN.json", share)
    return share


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--broker-csv", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = run(args.input_dir, args.broker_csv)
    except EvidenceError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except (OSError, ValueError, sqlite3.Error, csv.Error):
        print("Join stopped while reading local evidence or writing local output.", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
