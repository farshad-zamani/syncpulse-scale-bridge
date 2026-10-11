# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Farshad Zamani - Cloudtart (https://cloudtart.com)
"""
Build dist/SyncPulseScaleBridge.exe — one file, nothing to install.

    python scripts/build.py            (needs: pip install -r requirements-dev.txt)
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from scale_bridge import ABOUT, COMPANY, EXE_NAME, PRODUCT, __version__  # noqa: E402


def version_file(path: str) -> None:
    parts = [int(p) for p in __version__.split(".")[:3]] + [0]
    numbers = ", ".join(str(n) for n in (parts + [0, 0, 0, 0])[:4])
    strings = {
        "CompanyName": COMPANY,
        "FileDescription": f"{PRODUCT} - RS-232 scale reader and network bridge",
        "FileVersion": __version__,
        "InternalName": EXE_NAME,
        "LegalCopyright": f"{ABOUT['copyright']}. Licensed under {ABOUT['license']}.",
        "OriginalFilename": f"{EXE_NAME}.exe",
        "ProductName": PRODUCT,
        "ProductVersion": __version__,
        "Comments": f"Author: {ABOUT['author']} - {ABOUT['website']} - {ABOUT['repository']}. "
                    f"Built for the {ABOUT['platform']} platform.",
    }
    entries = ",\n".join(f"          StringStruct({k!r}, {v!r})" for k, v in strings.items())
    text = f"""# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(filevers=({numbers}), prodvers=({numbers}), mask=0x3f, flags=0x0,
                    OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([
      StringTable('040904B0', [
{entries}
      ])
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def main() -> int:
    build = os.path.join(ROOT, "build")
    os.makedirs(build, exist_ok=True)
    icon = os.path.join(ROOT, "assets", "icon.ico")
    if not os.path.exists(icon):
        subprocess.check_call([sys.executable, os.path.join(ROOT, "scripts", "make_icon.py")])
    vfile = os.path.join(build, "version_info.txt")
    version_file(vfile)
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--console",
           "--name", EXE_NAME, "--icon", icon, "--version-file", vfile,
           "--distpath", os.path.join(ROOT, "dist"), "--workpath", os.path.join(build, "pyinstaller"),
           "--specpath", build, os.path.join(ROOT, "run_bridge.py")]
    subprocess.check_call(cmd, cwd=ROOT)
    exe = os.path.join(ROOT, "dist", EXE_NAME + (".exe" if os.name == "nt" else ""))
    with open(exe, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    with open(exe + ".sha256", "w", encoding="ascii", newline="\n") as f:
        f.write(f"{digest}  {os.path.basename(exe)}\n")
    print(f"\nbuilt {exe}\nSHA-256 {digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
