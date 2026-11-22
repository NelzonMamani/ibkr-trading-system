"""Offline review of collector snapshots and a locally verified IBKR report.

Uses the SQLiteStore and StorageEngine read-side column contracts without
importing application modules. The review never authorizes position adoption.
"""
import argparse
from collections import defaultdict
from contextlib import closing
import csv
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
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
FLEX_SECTIONS = {"POST": "openpositions", "TRNT": "trades", "CORP": "corporateactions", "TRFR": "transfers"}
FLEX_COLUMNS = {
    "POST": {"clientaccountid", "conid", "quantity", "reportdate"},
    "TRNT": {"clientaccountid", "conid", "quantity", "iborderid", "ibexecid", "orderreference"},
    "CORP": {"clientaccountid", "conid", "quantity", "actionid", "transactionid", "type",
             "datetime", "reportdate", "actiondescription"},
}
SPLITS = {"P01": ("20261002", 8), "P02": ("20261113", 9)}
PAPER_RUN_PROVENANCE = {"paper_effective_mode", "paper_legacy_run_mode"}
CALLBACK_SOURCES = {"ibkr", "ibkrclient", "ibkrbroker", "ibkrlivebroker"}


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


def flex_date(text):
    if not re.fullmatch(r"[0-9]{8}", text):
        raise ValueError("Expected a Flex date")
    return date(int(text[:4]), int(text[4:6]), int(text[6:8]))


def flex_count(text):
    if not re.fullmatch(r"[0-9]+", text):
        raise EvidenceError("Invalid Flex section or row count.")
    return int(text)


def broker_sections(report):
    """Read the Flex CSV envelope. Structural errors carry no report values."""
    reader = csv.reader(io.StringIO(report, newline=""), strict=True)
    bof = next(reader, [])
    if len(bof) < 6 or bof[0] != "BOF" or not bof[1].strip() or not bof[2].strip():
        raise EvidenceError("Flex BOF record is missing or invalid.")
    count = flex_count(bof[3])
    try:
        valid_period = flex_date(bof[4]) <= flex_date(bof[5])
    except ValueError:
        valid_period = False
    if not valid_period:
        raise EvidenceError("Flex BOF statement period is invalid.")

    sections = {}
    for _ in range(count):
        bos = next(reader, [])
        if (len(bos) < 3 or bos[0] != "BOS"
                or not re.fullmatch(r"[A-Z0-9]+", bos[1]) or not bos[2].strip()):
            raise EvidenceError("Expected Flex BOS section record.")
        code = bos[1]
        section = FLEX_SECTIONS.get(code, code)
        if section in sections:
            raise EvidenceError("Flex section code is repeated.")
        header = next(reader, [])
        columns = [header_key(column) for column in header]
        if (not columns or header[0] in {"BOF", "BOS", "EOS", "EOF"}
                or not all(columns) or len(set(columns)) != len(columns)
                or not FLEX_COLUMNS.get(code, set()).issubset(columns)):
            raise EvidenceError("Flex section column headers are missing, invalid or ambiguous.")
        rows = []
        for row in reader:
            if row and row[0] == "EOS":
                if len(row) < 3 or row[1] != code or flex_count(row[2]) != len(rows):
                    raise EvidenceError("Flex EOS section code or row count disagrees with its section.")
                break
            if len(row) != len(columns) or row[0] in {"BOF", "BOS", "EOF"}:
                raise EvidenceError("Flex section data width or framing is invalid.")
            rows.append(dict(zip(columns, (item.strip() for item in row))))
        else:
            raise EvidenceError("Flex EOS section record is missing.")
        sections[section] = rows

    eof = next(reader, [])
    if not eof or eof[0] != "EOF" or next(reader, None) is not None:
        raise EvidenceError("Flex EOF is missing, misplaced or followed by extra records.")
    if not set(FLEX_SECTIONS.values()).issubset(sections):
        raise EvidenceError("Flex report lacks a required position, trade, action or transfer section.")
    if any(value(row, "clientaccountid") != bof[1].strip() for row in sections["openpositions"]):
        raise EvidenceError("Open Positions account disagrees with Flex BOF account.")
    sections["statement"] = {"account": bof[1].strip(), "from": bof[4], "to": bof[5]}
    return sections


def contract(row):
    return value(row, "clientaccountid"), value(row, "conid")


def trade_side(row):
    side = value(row, "buysell", "side").upper()
    if side:
        return {"BOT": "BUY", "SLD": "SELL"}.get(side, side)
    quantity = decimal(value(row, "quantity"))
    if quantity:
        return "BUY" if quantity > 0 else "SELL"
    return ""


def index_broker_trades(rows):
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
            account, _ = contract(row)
            execution = value(row, "ibexecid", "ibexecutionid", "execid", "executionid")
            transaction = value(row, "tradeid", "transactionid")
            identity = (("execution", account, execution) if execution else
                        ("trade", account, transaction) if transaction else ("row", canonical(row)))
        signature = (
            contract(row), trade_side(row),
            decimal(value(row, "quantity")), decimal(value(row, "tradeprice", "tprice", "price")),
            value(row, "datetime", "tradedatetime", "tradedate"),
            value(row, "orderreference", "orderref"), value(row, "iborderid", "brokerorderid"),
        )
        by_identity[identity][signature] = row
    return by_identity


def validate_manifest(manifest):
    if (not isinstance(manifest, dict) or not {"databases", "gaps", "broker_report"} <= manifest.keys()
            or not isinstance(manifest["databases"], list) or not isinstance(manifest["gaps"], list)):
        raise EvidenceError("Collector manifest lacks databases, gaps or broker report status.")
    entries = {}
    for entry in manifest["databases"]:
        alias = entry.get("alias") if isinstance(entry, dict) else None
        if not isinstance(alias, str) or not SNAPSHOT_ALIAS.fullmatch(alias) or alias in entries:
            raise EvidenceError("Collector manifest has invalid or repeated snapshot aliases.")
        status = entry.get("status")
        if status == "refused" and isinstance(entry.get("gap"), str) and entry["gap"].strip():
            entries[alias] = entry
            continue
        if (status != "verified" or entry.get("snapshot") != f"{alias}.sqlite3"
                or not isinstance(entry.get("sha256"), str)
                or not re.fullmatch(r"[a-fA-F0-9]{64}", entry["sha256"])
                or any(key not in entry for key in (
                    "source_path", "references", "historical_startup_modes", "sidecars_present",
                    "tables", "paper_runs", "paper_native_state_rows"))
                or not isinstance(entry["source_path"], str)
                or not isinstance(entry["historical_startup_modes"], list)
                or not isinstance(entry["tables"], list) or not isinstance(entry["paper_runs"], dict)
                or (entry["paper_native_state_rows"] is not None
                    and (type(entry["paper_native_state_rows"]) is not int or entry["paper_native_state_rows"] < 0))):
            raise EvidenceError(f"{alias} violates the collector manifest entry contract.")
        entries[alias] = entry
    if "D002" not in entries:
        raise EvidenceError("Collector manifest is missing D002.")
    return entries


def has_sidecars(path):
    return any(path.with_name(path.name + ext).exists() for ext in ("-wal", "-journal", "-shm"))


def selected_snapshots(root, manifest):
    entries = validate_manifest(manifest)
    for alias in sorted(entries, key=lambda alias: (alias != "D002", alias)):
        entry = entries[alias]
        if entry["status"] == "refused":
            yield alias, None, "Collector refused this snapshot. See private manifest for the reason."
            continue
        expected = entry["sha256"].lower()
        try:
            path = (root / entry["snapshot"]).resolve(strict=True)
            if path.parent != root or not path.is_file() or has_sidecars(path):
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
    fields = ("status", "source", "event_type", "mode", "run_mode", "effective_run_mode",
              "fill_status", "gateway_decision")
    return any(
        any(record.get(flag) is True for flag in ("simulated", "synthetic", "replayed"))
        or any(re.search(r"SIMULAT|SYNTH|MOCK|TEST_FILL|DRY_RUN|REPLAY", value(record, field).upper())
               for field in fields)
        for record in (row, payload)
    )


def run_provenance(row, runs):
    run = runs.get(value(row, "run_id"), {})
    effective = value(run, "effective_run_mode").upper()
    declared = value(run, "run_mode").upper()
    if (simulated(run, run) or simulated(row, row)
            or any(mode in {"SIM", "TEST", "BACKTEST"} for mode in (effective, declared))):
        return "simulated"
    if effective and declared and effective != declared:
        return "conflicting_modes"
    mode = effective or declared
    if mode == "PAPER":
        return "paper_effective_mode" if effective else "paper_legacy_run_mode"
    if mode == "READ_ONLY":
        return "read_only_observation"
    if mode:
        return "other_run_mode"
    return "run_mode_unavailable"


def journal_fills(data):
    """Collect independently usable account, contract and exact execution bindings."""
    runs = {value(row, "run_id"): row for row in data.get("runs", []) if value(row, "run_id")}
    trades = {(row.get("run_id"), row.get("lifecycle_trade_id")): row
              for row in data.get("trade_lifecycle_trades", []) if row.get("lifecycle_trade_id")}
    order_refs = defaultdict(set)
    for row in data.get("events", []):
        payload = obj(row.get("payload_json"))
        kind = value(payload, "event_type") or value(row, "event_type")
        if (kind not in {"openOrder", "completedOrder"} or simulated(row, payload)
                or run_provenance(row, runs) == "simulated"):
            continue
        order = obj(payload.get("order"))
        account = value(order, "account")
        permanent_id = value(order, "permId")
        reference = value(order, "orderRef")
        if account and permanent_id.isdecimal() and int(permanent_id) > 0 and reference:
            order_refs[(value(row, "run_id"), account, permanent_id)].add(reference)

    for row in data.get("events", []):
        payload = obj(row.get("payload_json"))
        kind = value(payload, "event_type") or value(row, "event_type")
        provenance = run_provenance(row, runs)
        execution = obj(payload.get("execution"))
        if kind != "execDetails" or provenance == "simulated" or simulated(row, payload) or simulated(execution, execution):
            continue
        security = obj(payload.get("contract"))
        account = value(execution, "acctNumber") or value(payload, "account")
        refs = set(order_refs.get((value(row, "run_id"), account, value(execution, "permId")), set()))
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
            "native": False, "kind": "retained_exec_details", "run_provenance": provenance,
            "run_id": value(row, "run_id"), "source": value(row, "source") or value(payload, "source"),
            "time": value(execution, "time") or value(payload, "time"),
            "order": value(execution, "orderId") or value(payload, "orderId"),
            "symbol": value(security, "symbol") or value(payload, "symbol"),
        }
    for row in data.get("trade_lifecycle_events", []):
        payload = obj(row.get("payload_json"))
        identity = obj(payload.get("native_identity"))
        trade = trades.get((row.get("run_id"), row.get("lifecycle_trade_id")), {})
        provenance = run_provenance(row, runs)
        if (row.get("event_type") != "ENTRY_FILL" or provenance == "simulated" or payload.get("native_feedback_committed") is not True
                or simulated(row, payload) or not trade or simulated(trade, identity)):
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
            "kind": "committed_native_entry", "run_provenance": provenance,
            "run_id": value(row, "run_id"), "source": value(row, "source"),
            "time": value(row, "timestamp"), "order": value(row, "order_id"),
            "symbol": value(row, "symbol"),
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
            if has_sidecars(path) or sha256(path) != digest:
                raise EvidenceError("Snapshot changed during inspection.")
        except (OSError, sqlite3.Error, EvidenceError):
            results[alias] = {"gap": "Verified image could not be inspected consistently."}
            continue
        images[digest] = alias
        private[alias] = {"path": str(path), "schema_gaps": gaps, "records": rows,
                          "retained_fill_facts": []}
        for fill in journal_fills(rows):
            private[alias]["retained_fill_facts"].append(fill)
            if fill["account"] and fill["exec"]:
                key = (fill["account"], fill["exec"])
                joins[key].setdefault(canonical(fill), (fill, set()))[1].add(alias)
        for row in rows.get("execution_results", []):
            payload = obj(row.get("payload_json"))
            ref = value(payload, "order_ref", "orderRef", "client_order_id")
            if ref:
                results_by_ref[ref].add((alias, simulated(row, payload)))
        results[alias] = {"schema_gaps": gaps, "retained_sources": {
            table: len(rows.get(table, ())) for table in (
                "execution_results", "events", "trade_lifecycle_events", "position_lifecycle_transitions")
        }}
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
    attributable = [fill for fill, _ in complete if fill["run_provenance"] in PAPER_RUN_PROVENANCE]
    committed = any(fill["native"] for fill in attributable)
    callback_reference = any(ross_ref(ref) for fill in attributable
                             if header_key(fill["source"]) in CALLBACK_SOURCES for ref in fill["refs"])
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


def split_pairs(sections):
    grouped = defaultdict(list)
    for row in sections["corporateactions"]:
        account, _ = contract(row)
        action_id = value(row, "actionid")
        if account and action_id:
            grouped[(account, action_id)].append(row)
    return grouped


def at_reported_precision(expected, reported):
    with localcontext() as context:
        context.prec = max(len(expected.as_tuple().digits), len(reported.as_tuple().digits)) + 16
        try:
            return expected.quantize(Decimal(1).scaleb(reported.as_tuple().exponent),
                                     rounding=ROUND_HALF_UP) == reported
        except InvalidOperation:
            return False


def corporate_action(groups, position, alias):
    date_text, denominator = SPLITS[alias]
    current = contract(position)
    position_qty = positive(value(position, "quantity"))
    if not position_qty or not all(current):
        return None, "Current position lacks exact account, contract or positive quantity."
    eligible = []
    for (account, _), legs in groups.items():
        if account != current[0] or len(legs) != 2:
            continue
        quantities = [decimal(value(row, "quantity")) for row in legs]
        if any(quantity is None or not quantity for quantity in quantities):
            continue
        first, second = sorted(zip(quantities, legs), key=lambda item: item[0])
        removed, predecessor = first
        credited, successor = second
        if (removed >= 0 or credited <= 0 or contract(successor) != current
                or not contract(predecessor)[1] or contract(predecessor) == current):
            continue
        transactions = {value(row, "transactionid") for row in legs}
        timestamps = {value(row, "datetime") for row in legs}
        if (len(transactions) != 2 or "" in transactions or len(timestamps) != 1
                or any(value(row, "type").upper() != "RS" for row in legs)):
            continue
        effective = next(iter(timestamps))
        iso_date = f"{date_text[:4]}-{date_text[4:6]}-{date_text[6:]}"
        if not re.fullmatch(
                rf"(?:{date_text}|{iso_date})[; T](?:[01][0-9]|2[0-3]):?[0-5][0-9]:?[0-5][0-9]",
                effective):
            continue
        ratios = {ratio for row in legs for ratio in re.findall(
            r"(?<![0-9])([0-9]+)\s*(?:-?\s*for\s*-?|:|/)\s*([0-9]+)(?![0-9])",
            value(row, "actiondescription"), flags=re.I)}
        if ratios != {("1", str(denominator))}:
            continue
        with localcontext() as context:
            context.prec = max(len(removed.as_tuple().digits), len(credited.as_tuple().digits)) + 16
            ratio_quantity = -removed / denominator
        if (not at_reported_precision(ratio_quantity, credited)
                or not at_reported_precision(credited, position_qty)):
            continue
        eligible.append((predecessor, successor))
    if len(eligible) == 1:
        return eligible[0], ""
    if len(eligible) > 1:
        return None, "Multiple corporate-action pairs meet the reviewed split contract."
    return None, "No corporate-action pair meets the reviewed account, effective time, ratio and quantity contract."


def acquisition_candidates(journals, related, confirmed):
    candidates = []
    for key, variants in journals.items():
        account, _ = key
        if key in confirmed:
            continue
        facts = list(variants.values())
        if not any((account, fill["conid"]) in related and fill["side"] == "BUY"
                   and fill["qty"] and fill["price"] for fill, _ in facts):
            continue
        signatures = {(fill["conid"], fill["side"], fill["qty"], fill["price"])
                      for fill, _ in facts if all((fill["conid"], fill["side"], fill["qty"], fill["price"]))}
        refs = {ref for fill, _ in facts for ref in fill["refs"]}
        conflict = len(signatures) > 1 or len(refs) > 1
        paper_facts = [fill for fill, _ in facts
                       if fill["run_provenance"] in PAPER_RUN_PROVENANCE
                       and (account, fill["conid"]) in related and fill["side"] == "BUY"
                       and fill["qty"] and fill["price"]]
        ross = not conflict and any(
            fill["native"] or (header_key(fill["source"]) in CALLBACK_SOURCES and any(map(ross_ref, fill["refs"])))
            for fill in paper_facts
        )
        candidates.append({
            "facts": [{"fact": fill, "snapshots": sorted(aliases)} for fill, aliases in facts],
            "conflicting_execution_evidence": conflict,
            "paper_run_link": bool(paper_facts),
            "journal_ross_attribution_supported": ross,
        })
    return candidates


def join_positions(sections, journals, results_by_ref, private):
    positions = sections["openpositions"]
    if len(positions) != 5:
        raise EvidenceError("Expected five Open Positions data rows in original report order.")
    trades = index_broker_trades(sections["trades"])
    action_groups = split_pairs(sections)
    verdicts = {}
    for index, position in enumerate(positions, 1):
        alias = f"P{index:02}"
        current = contract(position)
        related = {current}
        continuity = "not_required_for_direct_contract_match"
        gaps = set()
        split = None
        if alias in SPLITS:
            split, gap = corporate_action(action_groups, position, alias)
            continuity = "paired_broker_action_legs_supported" if split else "unresolved"
            if split:
                related.add(contract(split[0]))
            else:
                gaps.add(gap)
        matched = []
        accepted = []
        confirmed = set()
        supporting = []
        for variants in trades.values():
            matching_rows = [row for row in variants.values() if contract(row) in related]
            if len(variants) > 1 and matching_rows:
                gaps.add("Conflicting broker trade records share one identity.")
                continue
            for row in matching_rows:
                account, conid = contract(row)
                if not account or not conid or trade_side(row) != "BUY":
                    continue
                acquired, attributed, gap = evidence_for(row, account, conid, journals, results_by_ref)
                if gap:
                    gaps.add(gap)
                if acquired:
                    matched.append(row)
                    accepted.append(attributed)
                    execution = value(row, "ibexecid")
                    if execution:
                        confirmed.add((account, execution))
                    supporting.append({
                        "broker_trade": row, "ross_attribution_supported": attributed,
                        "journal_facts": [{"facts": fill, "snapshots": sorted(aliases)}
                                          for fill, aliases in journals.get((account, execution), {}).values()],
                        "exact_reference_result_sources": sorted(
                            results_by_ref.get(value(row, "orderreference", "orderref"), set())),
                        "gap": gap,
                    })
        journal_only = acquisition_candidates(journals, related, confirmed)
        if not all(current):
            gaps.add("Open Positions row lacks exact account or contract ID.")
        if not sections["trades"]:
            gaps.add("Flex Trades section contains zero rows for the declared period.")
        elif not matched:
            gaps.add("No broker acquisition matched by exact account and contract ID.")
        if not journal_only and not matched:
            gaps.add("No retained account- and contract-bound acquisition candidate was found.")
        if any(candidate["conflicting_execution_evidence"] for candidate in journal_only):
            gaps.add("Retained candidate facts conflict for an execution identity.")
        if any(not candidate["paper_run_link"] for candidate in journal_only):
            gaps.add("Some journal-only candidates lack a qualifying PAPER run link.")
        gaps.add("Open-lot attribution requires complete quantity, disposition and continuity evidence.")
        private[alias] = {"position": position, "matched_acquisitions": matched, "join_evidence": supporting,
                          "split_legs": split, "journal_only_candidates": journal_only}
        verdicts[alias] = {
            "broker_acquisition": "reported" if matched else "unresolved",
            "ross_attribution": "supported_for_all_matching_acquisitions" if accepted and all(accepted)
                                else "supported_for_some_matching_acquisitions" if any(accepted) else "unresolved",
            "journal_only_candidates": {
                "count": len(journal_only),
                "supporting_ross_attribution": sum(item["journal_ross_attribution_supported"] for item in journal_only),
                "sources": sorted({(source_alias, observation["fact"]["kind"],
                                    observation["fact"]["run_provenance"])
                                   for candidate in journal_only for observation in candidate["facts"]
                                   for source_alias in observation["snapshots"]}),
            },
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
    report = broker.read_bytes()
    if hashlib.sha256(report).hexdigest() != expected_hash:
        raise EvidenceError("Broker CSV SHA256 mismatch.")
    sections = broker_sections(report.decode("utf-8-sig"))
    private = {"manifest": manifest, "broker_path": str(broker.resolve()), "broker_sections": sections,
               "snapshots": {}, "positions": {}}
    journals, results_by_ref, snapshots = collect_journals(root, manifest, private["snapshots"])
    positions = join_positions(sections, journals, results_by_ref, private["positions"])
    share = {"PAPER_READY": "NO", "positions": positions, "snapshots": snapshots,
             "broker_trade_rows": len(sections["trades"]), "discovery_gap_count": len(manifest["gaps"]),
             "operative_paper_path_verified": False}
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
