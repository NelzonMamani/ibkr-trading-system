"""Quick import test for scanner modules."""
from __future__ import annotations

from . import scanner_main
from .scanner_config import IB_HOST, IB_PORT


def main() -> None:
    _ = (scanner_main, IB_HOST, IB_PORT)
    print("OK: imports resolved")


if __name__ == "__main__":
    main()
