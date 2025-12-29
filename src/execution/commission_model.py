class CommissionModel:
    """
    Deterministic, per-share commission model.

    Applies a fixed cost per share based on trader type. The calculation is
    intentionally simple to remain replay-safe and free of external
    dependencies.
    """

    COMMISSION_PER_SHARE = {
        "SCALPER": 0.005,
        "MOMENTUM": 0.007,
    }

    @staticmethod
    def calculate_commission(trader_type: str, quantity: int) -> float:
        """
        Return the total round-trip commission for a trade.

        Commission applies on both entry and exit, so the per-share rate is
        multiplied by two. Unknown trader types default to zero commission to
        preserve backwards compatibility.
        """

        per_share = CommissionModel.COMMISSION_PER_SHARE.get(
            (trader_type or "").upper(), 0.0
        )
        try:
            share_count = abs(int(quantity))
        except (TypeError, ValueError):
            share_count = 0
        commission = share_count * per_share * 2
        return round(commission, 4)
