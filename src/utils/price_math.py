from decimal import Decimal, ROUND_HALF_UP, getcontext

# Configure global decimal context for monetary calculations.
getcontext().rounding = ROUND_HALF_UP


def to_decimal(value) -> Decimal:
    """
    Convert input to Decimal safely using string casting to preserve precision.
    None or invalid inputs return Decimal('0').
    """

    if isinstance(value, Decimal):
        return value
    if value is None:
        return Decimal("0")
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


def q_money(value, places: str = "0.01") -> Decimal:
    """Quantize a monetary value to the specified places (default cents)."""

    quantizer = Decimal(places)
    return to_decimal(value).quantize(quantizer)


def q_price(value, places: str = "0.01") -> Decimal:
    """Quantize a price value to the specified places (default cents)."""

    return q_money(value, places)


def q_qty(value, places: str = "1") -> Decimal:
    """Quantize quantity; default to whole units."""

    quantizer = Decimal(places)
    return to_decimal(value).quantize(quantizer)


def safe_div(numerator, denominator, default: Decimal = Decimal("0")) -> Decimal:
    """Division helper that avoids ZeroDivisionError and quantizes to cents."""

    denom_decimal = to_decimal(denominator)
    if denom_decimal == 0:
        return default
    return q_money(to_decimal(numerator) / denom_decimal)


def deterministic_spread(symbol: str, tick: int, trader_type: str) -> Decimal:
    """
    Deterministic, hash-free spread generator.

    Uses ordinal sums and modular arithmetic to guarantee replayable spreads.
    """

    key = f"{symbol}|{tick}|{trader_type}|SPREAD"
    r = sum(ord(c) for c in key) % 10
    if r in (0, 1, 2):
        spread = Decimal("0.01")
    elif r in (3, 4, 5):
        spread = Decimal("0.02")
    elif r in (6, 7):
        spread = Decimal("0.03")
    elif r == 8:
        spread = Decimal("0.05")
    else:
        spread = Decimal("0.08")
    return q_price(spread)


def apply_spread_mid_to_quote(mid: Decimal, spread: Decimal) -> tuple[Decimal, Decimal]:
    """
    Convert a mid price and spread into bid/ask quotes.

    Ensures bid/ask are quantized to cents and bid is never below $0.01.
    """

    half = spread / Decimal("2")
    bid = q_price(mid - half)
    ask = q_price(mid + half)
    minimum_price = Decimal("0.01")
    if bid < minimum_price:
        bid = minimum_price
    if ask <= bid:
        ask = q_price(bid + Decimal("0.01"))
    return bid, ask


def choose_execution_reference_price(direction: str, bid: Decimal, ask: Decimal) -> Decimal:
    normalized_direction = (direction or "").upper()
    if normalized_direction == "LONG":
        return ask
    if normalized_direction == "SHORT":
        return bid
    raise ValueError(f"Unknown direction for reference price: {direction}")


def apply_slippage(
    reference_price: Decimal, slippage: Decimal, direction: str
) -> tuple[Decimal, Decimal]:
    """
    Apply slippage to a reference price based on direction.

    Returns the execution price and the slippage applied (signed).
    """

    normalized_direction = (direction or "").upper()
    slippage_abs = q_price(slippage)
    if normalized_direction == "SHORT":
        execution = q_price(reference_price - slippage_abs)
        applied = q_price(execution - reference_price)
        return execution, applied
    execution = q_price(reference_price + slippage_abs)
    applied = q_price(execution - reference_price)
    return execution, applied
