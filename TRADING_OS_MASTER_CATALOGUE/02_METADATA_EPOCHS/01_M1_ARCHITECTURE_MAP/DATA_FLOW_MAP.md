# M1 Data Flow Map (Text Diagram)

```
Market Data Providers
        │
        ▼
     Scanner
        │
        ▼
 Watchlist / Focus
        │
        ▼
   Data Hydration
        │
        ▼
 Pattern Detection
        │
        ▼
 Strategy Policy
        │
        ▼
    Risk Engine
        │
        ▼
  Execution Engine
        │
        ▼
   Broker Adapters
        │
        ▼
 Storage & Audit
```

Notes:
- Data flows are unidirectional.
- Each stage emits artifacts consumed by the next stage.
- Storage receives audit events from multiple stages but never feeds control decisions.

END
