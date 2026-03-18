from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def _normalized_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().upper()
    return text or None


@dataclass(frozen=True)
class CandidateIdentity:
    symbol: str
    con_id: int | None = None
    sec_type: str = "STK"
    exchange: str | None = None
    primary_exchange: str | None = None
    trading_class: str | None = None
    currency: str | None = None
    local_symbol: str | None = None

    @property
    def canonical_symbol(self) -> str:
        return self.symbol

    @property
    def key(self) -> str:
        if self.con_id not in {None, 0}:
            return f"conid:{int(self.con_id)}"
        return "|".join(
            [
                f"symbol:{self.symbol}",
                f"sectype:{self.sec_type or 'NA'}",
                f"exchange:{self.exchange or 'NA'}",
                f"primary:{self.primary_exchange or 'NA'}",
                f"trading:{self.trading_class or 'NA'}",
                f"currency:{self.currency or 'NA'}",
                f"local:{self.local_symbol or 'NA'}",
            ]
        )

    @property
    def aliases(self) -> tuple[str, ...]:
        values = []
        for value in (self.symbol, self.local_symbol, self.trading_class):
            normalized = _normalized_text(value)
            if normalized and normalized not in values:
                values.append(normalized)
        return tuple(values)

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> "CandidateIdentity":
        return cls(
            symbol=_normalized_text(payload.get("symbol") or payload.get("localSymbol") or payload.get("tradingClass") or "") or "NA",
            con_id=_coerce_int(payload.get("conId") or payload.get("con_id")),
            sec_type=_normalized_text(payload.get("secType") or payload.get("sec_type") or "STK") or "STK",
            exchange=_normalized_text(payload.get("exchange")),
            primary_exchange=_normalized_text(payload.get("primaryExchange") or payload.get("primary_exchange")),
            trading_class=_normalized_text(payload.get("tradingClass") or payload.get("trading_class")),
            currency=_normalized_text(payload.get("currency")),
            local_symbol=_normalized_text(payload.get("localSymbol") or payload.get("local_symbol")),
        )

    @classmethod
    def from_contract(cls, contract: Any, *, fallback_symbol: str | None = None) -> "CandidateIdentity":
        return cls(
            symbol=_normalized_text(getattr(contract, "symbol", None) or fallback_symbol or getattr(contract, "localSymbol", None) or getattr(contract, "tradingClass", None) or "") or "NA",
            con_id=_coerce_int(getattr(contract, "conId", None)),
            sec_type=_normalized_text(getattr(contract, "secType", None) or "STK") or "STK",
            exchange=_normalized_text(getattr(contract, "exchange", None)),
            primary_exchange=_normalized_text(getattr(contract, "primaryExchange", None)),
            trading_class=_normalized_text(getattr(contract, "tradingClass", None)),
            currency=_normalized_text(getattr(contract, "currency", None)),
            local_symbol=_normalized_text(getattr(contract, "localSymbol", None)),
        )


def _coerce_int(value: Any) -> int | None:
    try:
        if value in {None, "", 0, "0"}:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def canonical_identity_key(payload: CandidateIdentity | dict[str, Any] | Any, *, fallback_symbol: str | None = None) -> str:
    if isinstance(payload, CandidateIdentity):
        return payload.key
    if isinstance(payload, dict):
        return CandidateIdentity.from_mapping(payload).key
    return CandidateIdentity.from_contract(payload, fallback_symbol=fallback_symbol).key


def bridge_identity_keys(identity: CandidateIdentity) -> tuple[str, ...]:
    keys = [identity.key]
    for alias in identity.aliases:
        alias_key = f"symbol:{alias}"
        if alias_key not in keys:
            keys.append(alias_key)
    return tuple(keys)
