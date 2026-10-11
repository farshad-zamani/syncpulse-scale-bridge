# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Farshad Zamani — Cloudtart (https://cloudtart.com)
# Additional terms under GPLv3 section 7(b): see NOTICE.md.
"""
SyncPulse Scale Bridge — a universal RS-232 scale reader and network bridge.

Plug a weighing scale's serial cable into a Windows PC, run one program, and
it finds the port, the speed and the protocol by itself, shows the live
weight, and serves it on the local network for the SyncPulse platform — or
any other system — to read.
"""

__version__ = "1.1.0"

PRODUCT = "SyncPulse Scale Bridge"
SERVICE_ID = "syncpulse-scale-bridge"
EXE_NAME = "SyncPulseScaleBridge"

# Authorship. Keeping these visible in the user interface is a condition of
# the licence (GPLv3 section 7(b), see NOTICE.md).
AUTHOR = "Farshad Zamani"
COMPANY = "Cloudtart"
WEBSITE = "https://cloudtart.com"
GITHUB = "https://github.com/farshad-zamani"
LINKEDIN = "https://www.linkedin.com/in/farshad-zamani92/"
REPOSITORY = "https://github.com/farshad-zamani/syncpulse-scale-bridge"
PLATFORM = "SyncPulse"
LICENSE_ID = "GPL-3.0-or-later"
COPYRIGHT = f"Copyright (C) 2026 {AUTHOR} - {COMPANY}"

ABOUT = {
    "product": PRODUCT,
    "version": __version__,
    "author": AUTHOR,
    "company": COMPANY,
    "website": WEBSITE,
    "github": GITHUB,
    "linkedin": LINKEDIN,
    "repository": REPOSITORY,
    "platform": PLATFORM,
    "license": LICENSE_ID,
    "copyright": COPYRIGHT,
}
