# Configuration Authority Matrix

## Canonical precedence (highest to lowest)
1. **In-process overrides** (`set_config_overrides`)
2. **Environment variables**
3. **Config registry defaults / default_factory**

> Effective invariant: **test/runtime override authority > env > registry > default**.

## Authority by function
| Component | Key(s) | Authority behavior |
|---|---|---|
| `config_resolver._resolve_entry` | all | Enforces override-first resolution, then env, then default. |
| `config_resolver.resolve_config` | all | Uses env fingerprint to invalidate cache when env changes between tests/runs. |
| `runtime_config.get_run_mode` | `RUN_MODE_EFFECTIVE` | Uses resolver-derived mode, now respecting override-first authority. |
| `runtime_config.get_execution_enabled` | `EXECUTION_ENABLED_EFFECTIVE` | Uses resolver-derived effective execution semantics. |
| `db_admin._assert_run_mode_safe` | run mode safety checks | Uses `get_run_mode` and therefore resolved override-first mode. |
| `replay_engine.replay_from_storage` | run mode replay guard | Allows replay only in SIM/PAPER based on resolved mode. |

## Mode laws preserved/repaired
- SIM/PAPER replay allowed.
- LIVE/READ_ONLY replay blocked.
- READ_ONLY non-executable.
- PAPER execution provider defaults to paper provider when enabled and provider not supplied.
