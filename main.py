#!/usr/bin/env python3
"""Polar H10 real-time ECG / ACC / RR monitor with HRV and session recording."""

import sys

if sys.platform == "win32":
    sys.coinit_flags = 0

from gui import run_app

if __name__ == "__main__":
    run_app()
