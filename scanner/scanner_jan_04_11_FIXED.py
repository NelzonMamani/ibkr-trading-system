#!/usr/bin/env python3
"""
scanner_jan_04_11_FIXED.py

WRAPPER FIX:
- Starts a persistent asyncio loop for ib_insync on Windows / Python 3.11+
- Replaces asyncio.run usage by forcing ib_insync util loop

USAGE:
- Place this file next to scanner_jan_04_11.py
- Run THIS file instead of the original
"""

from ib_insync import util
util.startLoop()

# Import the original scanner AFTER loop is started
import scanner_jan_04_11 as scanner

if __name__ == "__main__":
    scanner.main()
