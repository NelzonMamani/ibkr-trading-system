## Reality Audit Checklist (YES/NO with evidence)

1. Is there a DB admin utility (status / backup / hard reset)?
2. Are DB files clearly located (repo-root data/, src/data/, etc.)?
3. Is there a safe reset that recreates schema and allows clean boot?
4. Are trace/event logs written in predictable locations?
5. Are there utilities to purge logs/artefacts safely?
6. Are legacy folders documented (e.g. XXX TRADING_OS_MASTER_CATALOGUE)?
7. Are destructive operations gated by mode (LIVE vs READ_ONLY)?
8. Are all ops logged (action, timestamp, operator)?

Write an audit summary and list gaps.