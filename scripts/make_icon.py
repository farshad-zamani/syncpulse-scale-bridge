# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Farshad Zamani - Cloudtart (https://cloudtart.com)
"""Draw the program icon (a platform scale with a display) into assets/icon.ico — standard library only."""
from __future__ import annotations

import os
import struct
import sys
import zlib

TEAL = (15, 118, 110)
DARK = (8, 64, 60)
WHITE = (255, 255, 255)


def _in_round_rect(x, y, x0, y0, x1, y1, r):
    if not (x0 <= x <= x1 and y0 <= y <= y1):
        return False
    cx = min(max(x, x0 + r), x1 - r)
    cy = min(max(y, y0 + r), y1 - r)
    return (x - cx) ** 2 + (y - cy) ** 2 <= r * r


def _in_trapezoid(x, y, top, bottom, top_x0, top_x1, bottom_x0, bottom_x1):
    if not (top <= y <= bottom):
        return False
    f = (y - top) / (bottom - top)
    return top_x0 + (bottom_x0 - top_x0) * f <= x <= top_x1 + (bottom_x1 - top_x1) * f


def colour_at(x, y):
    """Colour of the 64x64 design at (x, y), or None outside the icon."""
    if not _in_round_rect(x, y, 0, 0, 64, 64, 14):
        return None
    if _in_round_rect(x, y, 23, 34, 41, 42, 2):                  # display window
        if _in_round_rect(x, y, 26, 37, 38, 39, 1):              # the reading
            return WHITE
        return DARK
    if _in_round_rect(x, y, 11, 13, 53, 19, 2.5):                # weighing plate
        return WHITE
    if 29 <= x <= 35 and 19 <= y <= 28:                          # column
        return WHITE
    if _in_trapezoid(x, y, 27, 51, 18, 46, 13, 51):              # body
        return WHITE
    return TEAL


def render(size: int, samples: int = 4) -> list[list[tuple[int, int, int, int]]]:
    rows = []
    step = 64 / size
    for py in range(size):
        row = []
        for px in range(size):
            acc = [0, 0, 0]
            covered = 0
            for sy in range(samples):
                for sx in range(samples):
                    c = colour_at((px + (sx + 0.5) / samples) * step, (py + (sy + 0.5) / samples) * step)
                    if c is not None:
                        covered += 1
                        acc[0] += c[0]
                        acc[1] += c[1]
                        acc[2] += c[2]
            if covered:
                row.append((acc[0] // covered, acc[1] // covered, acc[2] // covered,
                            round(255 * covered / samples ** 2)))
            else:
                row.append((0, 0, 0, 0))
        rows.append(row)
    return rows


def png(rows) -> bytes:
    h, w = len(rows), len(rows[0])
    raw = b"".join(b"\x00" + bytes(v for px in row for v in px) for row in rows)

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def dib(rows) -> bytes:
    h, w = len(rows), len(rows[0])
    header = struct.pack("<IiiHHIIiiII", 40, w, h * 2, 1, 32, 0, 0, 0, 0, 0, 0)
    pixels = b"".join(bytes((b, g, r, a)) for row in reversed(rows) for (r, g, b, a) in row)
    mask_row = ((w + 31) // 32) * 4
    return header + pixels + b"\x00" * mask_row * h


def ico(sizes=(16, 24, 32, 48, 64, 256)) -> bytes:
    images = [(s, png(render(s)) if s >= 256 else dib(render(s))) for s in sizes]
    out = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    for s, data in images:
        out += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    return out + b"".join(d for _, d in images)


def main() -> int:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target = os.path.join(root, "assets", "icon.ico")
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "wb") as f:
        f.write(ico())
    with open(os.path.join(root, "assets", "icon.png"), "wb") as f:
        f.write(png(render(256)))
    print(target)
    return 0


if __name__ == "__main__":
    sys.exit(main())
