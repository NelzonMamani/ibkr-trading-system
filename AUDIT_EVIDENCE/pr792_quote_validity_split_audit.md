## Final Hardening Adjustments (PR #793 Follow-up)

- Preserved IBKR `quote_integrity_state` (no information loss).
- Introduced `quote_usability_state` (scanner vs momentum vs execution separation).
- Fixed incorrect mapping of `data_integrity_flags`.
- Eliminated duplicate quote contract computation (anti-drift).
- Tightened RTH degraded scanner rules.
- Restored THA evaluation independence from `execution_enabled`.

### Outcome

- IBKR truth remains strict and auditable.
- Scanner continuity preserved without fabrication.
- Execution safety unchanged.
- System ready for LIVE validation.
