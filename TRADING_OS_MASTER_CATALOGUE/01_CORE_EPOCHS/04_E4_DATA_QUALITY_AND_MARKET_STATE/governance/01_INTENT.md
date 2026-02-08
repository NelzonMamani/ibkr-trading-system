# E4 — Intent

Define and enforce a deterministic, auditable understanding of:
- market session state (PRE / RTH / AH / CLOSED)
- data freshness, completeness, and trustworthiness
- read-only and no-trade conditions driven by data state

E4 is a gating epoch: if data is untrusted, the system must not trade.
