# Orchestrator Event Flow

The orchestrator is a pure event consumer.

## Responsibilities
- Trigger scanner cycles
- Consume scanner and prep events
- Delegate symbol sets to strategies

## Event Handling
- SCANNER_WATCHLIST_K_READY → Strategy evaluation
- SCANNER_MOMENTUM_SPIKE → On-demand prep
- PREP_UPDATED → Mark symbol ready

No polling.
No implicit state.