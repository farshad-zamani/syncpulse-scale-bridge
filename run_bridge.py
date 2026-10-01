# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Farshad Zamani - Cloudtart (https://cloudtart.com)
"""Entry point for the single-file program (PyInstaller) and for `python run_bridge.py`."""
import sys

from scale_bridge.cli import main

if __name__ == "__main__":
    sys.exit(main())
