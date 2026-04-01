from __future__ import annotations

try:
    from ibapi.contract import Contract
    from ibapi.order import Order

    IBAPI_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover - optional dependency missing
    IBAPI_AVAILABLE = False
    Contract = None  # type: ignore
    Order = None  # type: ignore
    print("[IBKR][TRANSLATOR] ibapi dependency missing; translation unavailable.")

from src.domain.models.internal_order import InternalOrder


class IbkrOrderTranslator:
    def __init__(
        self,
        order_translation_enabled: bool,
        default_exchange: str = "SMART",
        default_currency: str = "USD",
    ):
        self.order_translation_enabled = order_translation_enabled
        self.default_exchange = default_exchange
        self.default_currency = default_currency

    def translate(self, internal_order: InternalOrder) -> tuple[Contract, Order]:
        self._ensure_enabled()
        self._log_pre_translation(internal_order)
        self.validate(internal_order)

        contract = Contract()
        contract.symbol = str(getattr(internal_order, "symbol", "") or "").upper()
        contract.exchange = str(getattr(internal_order, "exchange", None) or self.default_exchange).upper()
        contract.currency = str(getattr(internal_order, "currency", None) or self.default_currency).upper()
        contract.secType = str(getattr(internal_order, "sec_type", None) or "STK").upper()

        order = Order()
        order.action = self._map_direction(internal_order.direction)
        order.totalQuantity = int(getattr(internal_order, "quantity", 0) or 0)
        order.orderType = self._map_order_type(internal_order.order_type)
        order.tif = self._map_time_in_force(internal_order.time_in_force)
        order.eTradeOnly = False
        order.firmQuoteOnly = False

        if order.orderType in {"LMT", "LIMIT"}:
            limit_price = getattr(internal_order, "limit_price", None)
            try:
                normalized_limit_price = float(limit_price)
            except (TypeError, ValueError):
                normalized_limit_price = 0.0
            if normalized_limit_price <= 0:
                order.orderType = "MKT"
                try:
                    order.lmtPrice = None
                except Exception:
                    pass
            else:
                order.lmtPrice = normalized_limit_price

        # Keep outside regular trading hours enabled in translated orders.
        # IBKR may still emit warning 2109 for certain destinations/order
        # combinations, but that warning is handled by execution verification
        # logic and must not be treated as an order rejection.
        order.outsideRth = True

        self.log_translation(contract, order)
        return contract, order

    def validate(self, internal_order: InternalOrder) -> None:
        self._ensure_enabled()

        symbol = str(getattr(internal_order, "symbol", "") or "").strip()
        if not symbol:
            raise RuntimeError("Symbol is required")

        direction = str(getattr(internal_order, "direction", "") or "").upper().strip()
        if direction not in {"LONG", "BUY", "SHORT", "SELL"}:
            raise ValueError("INVALID_DIRECTION")

    def log_translation(self, contract: Contract, order: Order) -> None:
        print(
            "[IBKR][ORDER_TRANSLATION] Translated Contract: "
            f"symbol={contract.symbol} exchange={contract.exchange} "
            f"currency={contract.currency} secType={contract.secType}"
        )
        order_log = (
            f"[IBKR][ORDER_TRANSLATION] Translated Order: action={order.action} "
            f"orderType={order.orderType} totalQuantity={order.totalQuantity} "
            f"tif={order.tif} outsideRth={getattr(order, 'outsideRth', None)}"
        )
        if getattr(order, "lmtPrice", None) is not None:
            order_log += f" lmtPrice={order.lmtPrice}"
        print(order_log)

    def _log_pre_translation(self, internal_order: InternalOrder) -> None:
        print(
            "[IBKR][ORDER_TRANSLATION] Preparing translation for "
            f"client_order_id={internal_order.client_order_id} "
            f"symbol={internal_order.symbol} "
            f"direction={internal_order.direction} "
            f"quantity={internal_order.quantity}"
        )

    def _ensure_enabled(self) -> None:
        if not self.order_translation_enabled:
            raise RuntimeError("IBKR order translation disabled by config.")
        if not IBAPI_AVAILABLE:
            raise RuntimeError("ibapi dependency missing; IBKR translation unavailable.")

    @staticmethod
    def _map_direction(direction: str) -> str:
        normalized_direction = str(direction or "").upper().strip()
        if normalized_direction in {"LONG", "BUY"}:
            return "BUY"
        if normalized_direction in {"SHORT", "SELL"}:
            return "SELL"
        raise ValueError("INVALID_DIRECTION")

    @staticmethod
    def _map_order_type(order_type: str) -> str:
        normalized_order_type = str(order_type or "MKT").upper().strip()
        if normalized_order_type == "LIMIT":
            normalized_order_type = "LMT"
        if normalized_order_type == "":
            normalized_order_type = "MKT"
        if normalized_order_type == "MKT":
            return "MKT"
        if normalized_order_type == "LMT":
            return "LMT"
        raise RuntimeError(f"Unsupported order type: {order_type}")

    @staticmethod
    def _map_time_in_force(time_in_force: str) -> str:
        normalized_tif = str(time_in_force or "DAY").upper().strip()
        if normalized_tif == "":
            normalized_tif = "DAY"
        if normalized_tif == "DAY":
            return "DAY"
        if normalized_tif == "GTC":
            return "GTC"
        if normalized_tif == "IOC":
            return "IOC"
        raise RuntimeError(f"Unsupported time in force: {time_in_force}")
