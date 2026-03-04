# Execution Admission Gate Verification

Generated at: `2026-03-04T13:51:27.054141+00:00`

Gate contract tested: `intent.executable == False -> blocked` plus platform safety reasons.

| Scenario | Admitted | Reasons |
|---|---:|---|
| manual approval missing | False | INTENT_NOT_EXECUTABLE, MANUAL_APPROVAL_MISSING |
| thesis broken | False | THESIS_BROKEN |
| capital allocation exceeded | False | CAPITAL_ALLOCATION_EXCEEDED |
| healthy scenario | True | NONE |
