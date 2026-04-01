#!/usr/bin/env python3
"""Compact lifecycle verifier from runtime logs."""

from __future__ import annotations

import argparse
import re
from collections import defaultdict


ORDER_RE = re.compile(r"order_id=(\d+)")
SYMBOL_RE = re.compile(r"symbol=([A-Z]+)")
FILLED_RE = re.compile(r"filled=(\d+)")
REMAINING_RE = re.compile(r"remaining=(\d+)")
STATE_RE = re.compile(r"to=([A-Z_]+)")
QTY_RE = re.compile(r"qty=(\d+)")


def _extract(pattern: re.Pattern[str], line: str, default: str = "") -> str:
    m = pattern.search(line)
    return m.group(1) if m else default


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("log_file")
    args = parser.parse_args()
    rows: dict[str, dict[str, str]] = defaultdict(dict)
    with open(args.log_file, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if "order_id=" not in line:
                continue
            order_id = _extract(ORDER_RE, line)
            if not order_id:
                continue
            symbol = _extract(SYMBOL_RE, line, rows[order_id].get("symbol", ""))
            if symbol:
                rows[order_id]["symbol"] = symbol
            filled = _extract(FILLED_RE, line)
            remaining = _extract(REMAINING_RE, line)
            state = _extract(STATE_RE, line, rows[order_id].get("state", "UNKNOWN"))
            if filled:
                rows[order_id]["filled_qty"] = filled
            if remaining:
                rows[order_id]["remaining_qty"] = remaining
            rows[order_id]["state"] = state
            if "[LIFECYCLE][POSITION]" in line and symbol:
                rows[order_id]["open_position_qty"] = _extract(QTY_RE, line, rows[order_id].get("open_position_qty", "0"))
    print("symbol,order_id,state,filled_qty,remaining_qty,pending_entry,open_position_qty,final_disposition")
    for order_id, row in sorted(rows.items(), key=lambda x: int(x[0])):
        filled_qty = row.get("filled_qty", "0")
        remaining_qty = row.get("remaining_qty", "0")
        pending_entry = "true" if int(remaining_qty) > 0 else "false"
        final_disposition = "WORKING" if int(remaining_qty) > 0 else "TERMINAL"
        print(
            f"{row.get('symbol', 'UNK')},{order_id},{row.get('state', 'UNKNOWN')},{filled_qty},"
            f"{remaining_qty},{pending_entry},{row.get('open_position_qty', '0')},{final_disposition}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
