# 07_PAPER_TRADING_PARITY_TASKS

Codex must ensure PAPER mode mirrors LIVE semantics:

- Same order lifecycle paths
- Same async timing boundaries
- Same risk gates

Differences must be explicitly documented.

Paper trading must:
- Place real broker orders (paper account)
- Reconcile positions correctly
- Survive reconnects

If PAPER cannot trade end-to-end, LIVE is blocked.
