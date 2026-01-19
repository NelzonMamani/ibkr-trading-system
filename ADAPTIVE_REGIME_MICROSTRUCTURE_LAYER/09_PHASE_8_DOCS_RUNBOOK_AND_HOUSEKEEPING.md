# Phase 8 — Docs, Runbook, and Housekeeping
Last updated: 2026-01-19

## Objective
Make the layer operable and understandable, and keep repo hygiene.

## Deliverables
1) Docs
Create a layer doc explaining:
- Purpose
- Pipeline position
- How to enable in SIM and LIVE_READ_ONLY
- How to read regime events and stored artifacts

2) Runbook entry
Update RUNBOOK.md (if present) with commands:
- SIM with layer enabled (policy off)
- SIM with policy on
- LIVE_READ_ONLY with layer enabled (policy off)
- LIVE_READ_ONLY with policy on (optional; safe)

3) Config documentation
Add config keys to the config reference (or create docs/config/ADAPTIVE_REGIME_LAYER.md).

4) Housekeeping note
Create HOUSEKEEPING.md listing which instruction folders can be deleted later after implementation is merged and verified.

## Acceptance criteria
- A new contributor can enable the layer without reading code.
