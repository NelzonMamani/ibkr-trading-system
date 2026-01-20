PHASE 2 — SCANNER CONTRACT ALIGNMENT

File:
src/scanner/contracts.py

Actions:
- StockSelectionPolicy must mirror StockSelectionSpec 1:1
- Field order must be deterministic
- No duplicate fields
- policy_from_config() ONLY for non-strategy runs

Add Test:
test_stock_selection_policy_fields_unique_and_ordered
