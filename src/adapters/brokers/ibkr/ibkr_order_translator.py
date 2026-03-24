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
        contract.symbol = internal_order.symbol
        contract.exchange = self.default_exchange
        contract.currency = self.default_currency
        contract.secType = "STK"

        order = Order()
        order.action = self._map_direction(internal_order.direction)
        order.totalQuantity = internal_order.quantity
        order.orderType = self._map_order_type(internal_order.order_type)
        order.tif = self._map_time_in_force(internal_order.time_in_force)
        order.eTradeOnly = False
        order.firmQuoteOnly = False

        if order.orderType == "LMT":
            order.lmtPrice = internal_order.limit_price

        # Keep outside regular trading hours enabled in translated orders.
        # IBKR may still emit warning 2109 for certain destinations/order
        # combinations, but that warning is handled by execution verification
        # logic and must not be treated as an order rejection.
        order.outsideRth = True

        self.log_translation(contract, order)
        return contract, order

    def validate(self, internal_order: InternalOrder) -> None:
        self._ensure_enabled()

        if internal_order.direction not in {"LONG", "SHORT"}:
            raise RuntimeError(f"Unsupported direction: {internal_order.direction}")

        if internal_order.quantity <= 0:
            raise RuntimeError(f"Quantity must be positive. Received: {internal_order.quantity}")

        if internal_order.order_type not in {"MKT", "LMT"}:
            raise RuntimeError(f"Unsupported order type: {internal_order.order_type}")

        if internal_order.order_type == "LMT" and internal_order.limit_price is None:
            raise RuntimeError("Limit price required for LMT orders.")

        if internal_order.time_in_force not in {"DAY", "IOC"}:
            raise RuntimeError(f"Unsupported time in force: {internal_order.time_in_force}")

    def log_translation(self, contract: Contract, order: Order) -> None:
        print(
            "[IBKR][ORDER_TRANSLATION] Translated Contract: "
            f"symbol={contract.symbol} exchange={contract.exchange} "
            f"currency={contract.currency} secType={contract.secType}"
        )
        order_log = (
            f"[IBKR][ORDER_TRANSLATION] Translated Order: action={order.action} "
            f"orderType={order.orderType} totalQuantity={order.totalQuantity} "
            f"tif={order.tif}"
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
        if direction == "LONG":
            return "BUY"
        if direction == "SHORT":
            return "SELL"
        raise RuntimeError(f"Unsupported direction: {direction}")

    @staticmethod
    def _map_order_type(order_type: str) -> str:
        if order_type == "MKT":
            return "MKT"
        if order_type == "LMT":
            return "LMT"
        raise RuntimeError(f"Unsupported order type: {order_type}")

    @staticmethod
    def _map_time_in_force(time_in_force: str) -> str:
        if time_in_force == "DAY":
            return "DAY"
        if time_in_force == "IOC":
            return "IOC"
        raise RuntimeError(f"Unsupported time in force: {time_in_force}")
