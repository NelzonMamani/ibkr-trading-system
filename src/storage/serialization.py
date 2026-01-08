from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
import hashlib
import json
from typing import Any, Callable


FallbackHandler = Callable[[Any], None]


def to_jsonable(
    obj: Any,
    *,
    allow_fallback: bool = False,
    fallback_handler: FallbackHandler | None = None,
) -> Any:
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, datetime):
        resolved = obj
        if resolved.tzinfo is None:
            resolved = resolved.replace(tzinfo=timezone.utc)
        return resolved.isoformat()
    if is_dataclass(obj):
        return {
            field.name: to_jsonable(
                getattr(obj, field.name),
                allow_fallback=allow_fallback,
                fallback_handler=fallback_handler,
            )
            for field in fields(obj)
        }
    if isinstance(obj, dict):
        return {
            str(key): to_jsonable(
                value,
                allow_fallback=allow_fallback,
                fallback_handler=fallback_handler,
            )
            for key, value in obj.items()
        }
    if isinstance(obj, (list, tuple, set)):
        return [
            to_jsonable(
                value,
                allow_fallback=allow_fallback,
                fallback_handler=fallback_handler,
            )
            for value in obj
        ]
    if allow_fallback:
        if fallback_handler is not None:
            fallback_handler(obj)
        return str(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def canonical_json(
    obj: Any,
    *,
    allow_fallback: bool = False,
    fallback_handler: FallbackHandler | None = None,
) -> str:
    return json.dumps(
        to_jsonable(
            obj,
            allow_fallback=allow_fallback,
            fallback_handler=fallback_handler,
        ),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def compute_audit_hash(
    prev_hash: str,
    event_payload: dict[str, Any],
    *,
    allow_fallback: bool = False,
    fallback_handler: FallbackHandler | None = None,
) -> str:
    canonical = canonical_json(
        event_payload,
        allow_fallback=allow_fallback,
        fallback_handler=fallback_handler,
    )
    return hashlib.sha256((prev_hash + canonical).encode("utf-8")).hexdigest()
