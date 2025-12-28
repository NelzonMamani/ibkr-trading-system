# PHASE 9 — SYSTEM HARDENING
## STEP 9.10 — EVENT SCHEMA FINAL CLOSURE (ABC CLEANUP)

You are Codex operating on the IBKR Trading System repository.

This step performs **final closure of the ABC transition** by resolving the
last remaining event schema inconsistency observed during runtime.

This step is REQUIRED before proceeding to Phase 10.

---

## CONTEXT

During execution, the following warning appears repeatedly:

[SCHEMA] event=TRADE_CLOSED has extra keys: tick

This indicates that the TRADE_CLOSED event payload includes a `tick` field
that is not declared in the event schema validator.

This is NOT a logic error, but it must be resolved to:
- Fully seal Phase 9
- Remove all teaching-era artifacts
- Ensure schema authority is absolute
- Guarantee replay integrity under strict validation

---

## OBJECTIVE

You will:

- Align TRADE_CLOSED event payloads with the declared schema
- Preserve deterministic replay behavior
- Maintain TradeExitEngine as the sole trade-closing authority
- Remove the last ABC-era ambiguity
- Ensure no schema warnings remain during execution

---

## FILES TO MODIFY (ONLY)

You must modify **only** the following file:

- `src/events/event_schema.py`  
  (or the file where TRADE_CLOSED schema is defined)

Do NOT modify any engine, orchestrator, or runtime logic.

---

## STEP 1 — LOCATE TRADE_CLOSED SCHEMA

Locate the schema definition for the `TRADE_CLOSED` event.

It will resemble one of the following patterns:

- A dictionary of allowed keys
- A dataclass / TypedDict
- A validation rule listing expected fields

---

## STEP 2 — ADD `tick` AS AN EXPLICITLY ALLOWED FIELD

Update the TRADE_CLOSED schema to explicitly include:

- `tick` (integer)

This field represents the authoritative clock tick at which the trade was closed.

Do NOT remove or rename any existing fields.

Example (illustrative only — adapt to actual structure):

```python
"TRADE_CLOSED": {
    "symbol",
    "trader_type",
    "strategy_name",
    "entry_tick",
    "exit_tick",
    "tick",              # ← ADD THIS
    "entry_price",
    "exit_price",
    "realised_pnl",
    "mode",
}
