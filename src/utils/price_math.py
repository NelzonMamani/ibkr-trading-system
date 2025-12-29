from decimal import Decimal, getcontext, ROUND_HALF_UP
from typing import Optional, Tuple

# Global precision for money
getcontext().prec = 28

MONEY_QUANT = Decimal("0.01")


def to_decimal(value) -> Optional[Decimal]:
    """Convert a value to Decimal using string conversion for floats."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


# Backwards-compatible alias used throughout the codebase.
D = to_decimal


def q_money(value: Optional[Decimal], places: str = "0.01") -> Optional[Decimal]:
    if value is None:
        return None
    quant = Decimal(places)
    return value.quantize(quant, rounding=ROUND_HALF_UP)


def q_price(value: Optional[Decimal], places: str = "0.01") -> Optional[Decimal]:
    if value is None:
        return None
    quant = Decimal(places)
    return value.quantize(quant, rounding=ROUND_HALF_UP)


# Backwards compatibility for existing imports
quantize_money = q_money


def safe_div(a: Decimal, b: Decimal, default: Decimal = Decimal("0")) -> Decimal:
    if b == 0:
        return default
    return a / b


def deterministic_mod_key(key: str, mod: int) -> int:
    return sum(ord(c) for c in key) % mod


def deterministic_spread(symbol: str, tick: int, trader_type: str) -> Decimal:
    key = f"{symbol}|{tick}|{trader_type}|SPREAD"
    r = deterministic_mod_key(key, 10)
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


def apply_spread_mid_to_quote(mid: Decimal, spread: Decimal) -> Tuple[Decimal, Decimal]:
    half = spread / Decimal("2")
    bid = mid - half
    ask = mid + half
    if bid < Decimal("0.01"):
        bid = Decimal("0.01")
    if ask <= bid:
        ask = bid + Decimal("0.01")
    return q_price(bid), q_price(ask)


def choose_execution_reference_price(direction: str, bid: Decimal, ask: Decimal) -> Decimal:
    normalized = (direction or "").upper()
    if normalized == "SHORT":
        return bid
    return ask


def apply_slippage(reference_price: Decimal, slippage: Optional[Decimal], direction: str) -> Tuple[Decimal, Decimal]:
    slippage = to_decimal(slippage) or Decimal("0")
    normalized = (direction or "").upper()
    if normalized == "SHORT":
        execution_price = reference_price - slippage
    else:
        execution_price = reference_price + slippage
    if execution_price < Decimal("0.01"):
        execution_price = Decimal("0.01")
    return q_price(execution_price), q_price(slippage)
