# E27 Verification Authority

E27 is not complete until the following evidence exists.

## 1. Required verification domains

1. Entry submission
2. Broker acknowledgement
3. Entry fill
4. Stop execution
5. Target execution
6. Trailing update
7. Partial fill handling
8. Duplicate prevention
9. Restart recovery
10. Reconciliation authority
11. Ross-specific red/green volume management
12. Retrace hard-fail handling
13. Key-level target behavior

## 2. Evidence matrix

| Capability | Required evidence |
|---|---|
| entry submitted | `[EXECUTION][SUBMIT]` + broker order id |
| broker acknowledged | `[IBKR][ACK]` / working status |
| entry filled | `execDetails` or equivalent fill event |
| stop attached | explicit stop child or synthetic protection event |
| target attached | explicit target child or synthetic protection event |
| trailing updated | `[EXECUTION][TRAIL_UPDATE]` |
| partial take | `[EXECUTION][PARTIAL_TAKE]` |
| >50% retrace exit | `[EXECUTION][EXIT_REASON=RETRACE_FAILURE]` |
| red volume exit | `[EXECUTION][EXIT_REASON=RED_VOLUME]` |
| level take-profit | `[EXECUTION][EXIT_REASON=LEVEL_TARGET]` |
| duplicate prevention | `[EXECUTION][DUPLICATE_WORKING_ORDER_BLOCK]` |
| restart recovery | startup reconciliation logs |
| orphan repair | explicit repair or escalation logs |

## 3. Minimum Ross verification scenarios

### Scenario A — fast continuation
- micro pullback entry
- green continuation
- partial at first target
- trail remainder

### Scenario B — immediate weakness
- entry
- equal or larger red bar
- exit triggered

### Scenario C — 1-minute >50% retrace
- entry
- retrace breaches threshold before close
- immediate exit + pause

### Scenario D — major level rejection
- entry into approach to whole/half/HOD
- rejection appears
- partial/full exit triggered

### Scenario E — restart during working order
- restart with active working order
- recovery rebuilds state
- no duplicate order issued

## 4. Verification completion criterion

E27 is considered verified only when:
- at least one end-to-end entry→fill→managed exit path is proven
- at least one stop path is proven
- at least one target path is proven
- at least one trailing path is proven
- recovery has been proven after restart
