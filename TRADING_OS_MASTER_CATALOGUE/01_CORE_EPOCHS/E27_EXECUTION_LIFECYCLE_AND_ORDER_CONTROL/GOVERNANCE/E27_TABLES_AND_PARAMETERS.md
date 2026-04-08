# E27 Tables and Parameters

## 1. Entry table

| Setting | Meaning | Default | Notes |
|---|---|---:|---|
| ENTRY_TRIGGER_TYPE | trigger style | `MICRO_PULLBACK_BREAK` | Ross default |
| EXECUTION_TIMEFRAME | execution frame | `10s` | Ross fast execution |
| CONTEXT_TIMEFRAME | higher context | `1m` | validates momentum |
| MICRO_PULLBACK_MAX_CANDLES | max pullback bars | `3` | 2–3 candles |
| REQUIRE_VOLUME_CONFIRMATION | entry requires green volume | `true` | must confirm |
| ENTRY_BLOCK_INTO_MAJOR_LEVEL | block if directly under major level | `true` | no low-upside entries |

## 2. Key levels table

| Level Type | Priority | Use |
|---|---|---|
| WHOLE_DOLLAR | highest | primary target / rejection |
| HALF_DOLLAR | high | primary target / rejection |
| HOD | high | breakout continuation / rejection |
| PREMARKET_HIGH | high | breakout / rejection |
| BREAKOUT_LEVEL | medium | trail reference / retest |

### Level settings

| Setting | Default |
|---|---:|
| WHOLE_DOLLAR_ENABLED | true |
| HALF_DOLLAR_ENABLED | true |
| HOD_ENABLED | true |
| PREMARKET_HIGH_ENABLED | true |
| MIN_ROOM_TO_NEXT_MAJOR_LEVEL_PCT | 0.5% |
| MIN_ROOM_TO_NEXT_MAJOR_LEVEL_ABS | 0.10 |

## 3. Stop-loss table

| Setting | Meaning | Default |
|---|---|---:|
| STOP_MODEL | initial stop model | `STRUCTURE_PULLBACK_LOW` |
| STOP_BUFFER_TICKS | buffer under pullback low | `1-2 ticks` |
| NO_NAKED_ENTRY | forbid entries without stop plan | `true` |

## 4. First target table

| Priority | Target Type | Action |
|---:|---|---|
| 1 | next whole/half dollar | partial |
| 2 | HOD / breakout level | partial |
| 3 | 2R | partial |
| 4 | extension | runner |

### Target settings

| Setting | Default |
|---|---:|
| FIRST_TARGET_MODEL | `LEVEL_FIRST_HOD_2R` |
| R_MULTIPLE_DEFAULT | 2.0 |
| PARTIAL_TAKE_PCT | 0.5 |
| ALLOW_FULL_EXIT_AT_FIRST_TARGET | false |

## 5. Green volume table

| green ratio vs reference | Interpretation | Action |
|---|---|---|
| < 1.0 | weak | no add |
| 1.0–1.2 | normal | hold |
| 1.2–1.5 | strong | hold / trail |
| 1.5–2.0 | very strong | scale possible |
| > 2.0 | aggressive | hold runner / loosen trail |

### Green volume settings

| Setting | Default |
|---|---:|
| GREEN_VOL_REF_MODE | `MAX(last_green, local_avg)` |
| GREEN_STRONG_THRESHOLD | 1.2 |
| GREEN_SCALE_THRESHOLD | 1.5 |
| GREEN_EXTREME_THRESHOLD | 2.0 |
| LOCAL_AVG_WINDOW | 5 |
| MAX_ADDS | 2 |

## 6. Red volume table

| red ratio vs reference | Interpretation | Action |
|---|---|---|
| >= 0.7 | weakness begins | no new entry |
| >= 1.0 | momentum lost | exit |
| >= 1.5 | aggressive selling | exit + pause |
| >= 2.0 | dump | immediate exit + pause |

### Red volume settings

| Setting | Default |
|---|---:|
| RED_VOL_REF_MODE | `MAX(last_green, local_avg)` |
| RED_WEAKNESS_THRESHOLD | 0.7 |
| RED_EXIT_THRESHOLD | 1.0 |
| RED_HARD_EXIT_THRESHOLD | 1.5 |
| RED_EMERGENCY_THRESHOLD | 2.0 |

## 7. Retrace table

| Retrace of active move | Meaning | Action |
|---|---|---|
| < 30% | healthy | hold |
| 30–50% | weakening | tighten |
| > 50% before close | failure | exit + pause |

### Retrace settings

| Setting | Default |
|---|---:|
| RETRACE_REFERENCE_FRAME | `1m` |
| RETRACE_WARNING_THRESHOLD | 0.30 |
| RETRACE_HARD_EXIT_THRESHOLD | 0.50 |
| RETRACE_EVALUATE_BEFORE_CLOSE | true |

## 8. Trailing table

| Condition | Trailing response |
|---|---|
| normal continuation | standard higher-low trail |
| strong green volume | loosen slightly |
| near major level | tighten |
| weakness detected | tighten aggressively |

### Trailing settings

| Setting | Default |
|---|---:|
| TRAIL_MODEL | `STRUCTURE_HIGHER_LOW` |
| TRAIL_BUFFER_TICKS | `1-2 ticks` |
| TRAIL_TIGHTEN_NEAR_MAJOR_LEVEL | true |
| TRAIL_LOOSEN_ON_STRONG_GREEN | true |
| MOVE_TO_BREAKEVEN_AT_R | 1.0 |

## 9. Scale-in table

| Condition | Action |
|---|---|
| first breakout | initial entry |
| next pullback + strong green + room to level | add |
| near major level | no add |
| weakness present | no add |

### Scaling settings

| Setting | Default |
|---|---:|
| MAX_ADDS | 2 |
| REQUIRE_ROOM_FOR_ADD | true |
| REQUIRE_GREEN_FOR_ADD | true |
| BLOCK_ADD_INTO_MAJOR_LEVEL | true |

## 10. Pause / resume table

| Trigger | Action |
|---|---|
| >50% retrace | pause |
| hard red-volume exit | pause |
| strong level rejection | pause |

| Resume condition | Action |
|---|---|
| new valid setup | re-arm |
| structure restored | re-arm |
| momentum resumes | re-arm |

### Pause settings

| Setting | Default |
|---|---:|
| PAUSE_ON_RETRACE_HARD_FAIL | true |
| PAUSE_ON_RED_HARD_EXIT | true |
| PAUSE_ON_LEVEL_REJECTION | true |
| RESUME_REQUIRES_NEW_STRUCTURE | true |
