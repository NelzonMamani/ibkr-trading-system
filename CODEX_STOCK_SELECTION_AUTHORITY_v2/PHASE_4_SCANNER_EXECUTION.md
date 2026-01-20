PHASE 4 — SCANNER EXECUTION LOGIC

Files:
src/scanner/scanner.py
src/scanner/scanner_runner.py
src/scanner/filters.py

Actions:
- Replace 'ross_5_pillars' language with 'mechanical_stock_selection_gates'
- Apply gates strictly from policy
- Enforce:
  - allow empty
  - log drop reasons
  - no padding

News:
- Diagnostics only
- Must NOT force entries
