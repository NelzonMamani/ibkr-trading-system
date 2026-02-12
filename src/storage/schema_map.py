"""Schema mapping declarations for metadata and storage epochs."""

SCHEMA_VERSION = "EPOCH5_V1"

DATA_PROVENANCE_LEDGER_SCHEMA_VERSION = "M10_V1"
DATA_PROVENANCE_LEDGER_REQUIRED_FIELDS = (
    "event_id",
    "symbol",
    "data_type",
    "timeframe_scope",
    "timeframe_resolution",
    "source_id",
    "mode",
    "session_state",
    "timestamp_observed",
    "timestamp_used",
    "freshness_class",
    "confidence_level",
    "known_limitations",
    "checksum_or_fingerprint",
    "linkage",
)
