# E27 Ross Execution Policy Profile

## 1. Purpose
This file describes how Ross Momentum consumes the shared E27 execution lifecycle.

Ross does not own order plumbing. Ross provides the policy profile that E27 consumes.

## 2. Ross-specific execution identity

Ross is a momentum-continuation strategy family with:
- breakout entries
- micro pullback execution refinement
- strong dependence on key levels
- structure-based stops
- rapid weakness exits
- repeatable re-entry behavior

## 3. Ross micro pullback execution doctrine

### 3.1 Entry model
Primary fast-execution pattern:
- 10-second micro pullback
- 2–3 small pullback candles
- break of micro high
- volume confirmation
- not directly into a major level

### 3.2 Initial stop
Structure-based:
- below the micro pullback low
- plus configurable small buffer

### 3.3 First target
Priority:
1. nearest half-dollar / whole-dollar level
2. HOD / fresh breakout level
3. 2R if it lands before the above

### 3.4 Breakeven protection
Default recommendation:
- at 1R, move stop to breakeven or slightly positive

### 3.5 Partial profit
Default recommendation:
- first target: take partial
- leave runner for structure trail

### 3.6 Trailing
Primary trailing model:
- structure-based
- stop moves beneath each confirmed new higher low

### 3.7 Hard-fail conditions
Immediate exit:
- 1-minute retrace exceeds 50% before close
- red-volume dominance reaches exit threshold
- clear level rejection after breakout
- micro-structure failure

### 3.8 Pause / resume
Pause symbol after:
- >50% retrace
- hard rejection at key level
- aggressive red-volume reversal

Resume only when:
- new clean setup forms
- momentum re-establishes
- structure resets

## 4. Ross-specific state machine extensions

State overlays used by Ross policy:
- ACTIVE
- WARNING
- PAUSED
- RE_ARMED

These are symbol-management states, not broker order states.

## 5. Ross scaling doctrine

Default:
- max adds: 2
- add only when:
  - structure intact
  - green volume strong
  - sufficient room remains before next major level
- no add directly into whole/half-dollar or HOD resistance

## 6. Ross level doctrine

Priority levels:
- whole dollar
- half dollar
- HOD
- premarket high
- recent breakout level

Use levels for:
- entry filtering
- first target selection
- exit confirmation
- trail tightening

## 7. Ross volume doctrine

### Green volume
Used for:
- hold confidence
- add permission
- trail looseness

### Red volume
Used for:
- entry block
- exit trigger
- pause trigger

## 8. Ross execution profile summary

For Ross, the recommended default E27 policy is:

- entry: marketable breakout
- stop: structure-based
- first target: nearest of level/HOD/2R
- first management: breakeven at 1R
- partial at first target
- runner trail by higher-low structure
- hard exit on >50% retrace or red-volume dominance
