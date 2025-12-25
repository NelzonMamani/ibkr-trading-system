"""
Storage engine skeleton responsible for persisting system activity.
"""

from models.data_models import TradeRecord


class StorageEngine:
    """Skeleton storage engine that logs storage attempts without persistence."""

    def __init__(self) -> None:
        print("[BOOT] StorageEngine instantiated — skeleton only")

    def store_trade_record(self, trade_record: TradeRecord) -> bool:
        """Store a TradeRecord placeholder; always returns True in skeleton."""

        print("[STORAGE] Skeleton storage invoked — no persistence performed")
        return True
