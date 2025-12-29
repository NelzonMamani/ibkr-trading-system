from decimal import Decimal, getcontext, ROUND_HALF_UP

# Global precision for money
getcontext().prec = 12

MONEY_QUANT = Decimal("0.01")


def D(value) -> Decimal:
    """Convert value safely to Decimal."""
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def quantize_money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)
