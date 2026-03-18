from __future__ import annotations

import asyncio
from typing import Any


def qualify_contracts_resilient(client: Any, *contracts: Any, timeout_seconds: float | None = None, log_prefix: str = "[EXECUTION][QUALIFY]") -> list[Any]:
    qualified: list[Any] = []
    sync_qualify = getattr(client, "qualifyContracts", None)
    async_qualify = getattr(client, "qualifyContractsAsync", None)
    for contract in contracts:
        if contract is None:
            continue
        symbol = str(getattr(contract, "symbol", None) or "UNKNOWN").upper()
        print(f"{log_prefix}[START] symbol={symbol}")
        result = None
        if callable(async_qualify):
            print(f"{log_prefix}[ASYNC_ATTEMPT] symbol={symbol}")
            try:
                awaitable = async_qualify(contract)
                if timeout_seconds is not None:
                    awaitable = asyncio.wait_for(awaitable, timeout=timeout_seconds)
                result = client.run(awaitable) if hasattr(client, "run") else asyncio.run(awaitable)
            except Exception as exc:
                print(f"{log_prefix}[ASYNC_FAILED] symbol={symbol} reason={exc}")
                result = None
        if not result and callable(sync_qualify):
            try:
                print(f"{log_prefix}[SYNC_FALLBACK] symbol={symbol}")
                result = sync_qualify(contract)
            except Exception as exc:
                print(f"{log_prefix}[FAILED] symbol={symbol} reason={exc}")
                result = None
        if result:
            qualified_contract = result[0]
            print(f"{log_prefix}[OK] symbol={symbol} conId={getattr(qualified_contract, 'conId', None)}")
            qualified.append(qualified_contract)
        else:
            print(f"{log_prefix}[FAILED] symbol={symbol} reason=NO_QUALIFIED_CONTRACT")
    return qualified
