from __future__ import annotations

import sys

if sys.platform.startswith("win"):
    import asyncio as _asyncio_tmp

    _asyncio_tmp.set_event_loop_policy(_asyncio_tmp.WindowsSelectorEventLoopPolicy())

from ib_insync import util

from .scanner_runner import run_scanner_cycle


def main() -> None:
    util.patchAsyncio()
    run_scanner_cycle(mode="standalone")


if __name__ == "__main__":
    main()
