from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from pathlib import Path
import sys

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from storage.serialization import canonical_json, to_jsonable


class SampleEnum(str, Enum):
    ALPHA = "alpha"


@dataclass
class SampleData:
    name: str
    amount: Decimal


def test_to_jsonable_handles_decimal_datetime_enum_dataclass():
    sample = SampleData(name="test", amount=Decimal("10.50"))
    now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    payload = {
        "enum": SampleEnum.ALPHA,
        "decimal": Decimal("1.25"),
        "datetime": now,
        "dataclass": sample,
    }

    result = to_jsonable(payload)

    assert result["enum"] == "alpha"
    assert result["decimal"] == "1.25"
    assert result["datetime"].endswith("+00:00")
    assert result["dataclass"] == {"name": "test", "amount": "10.50"}


def test_canonical_json_is_stable():
    payload = {"b": 2, "a": 1}
    assert canonical_json(payload) == '{"a":1,"b":2}'


def test_to_jsonable_rejects_unknown_without_fallback():
    class Unserializable:
        pass

    with pytest.raises(TypeError):
        to_jsonable(Unserializable())
