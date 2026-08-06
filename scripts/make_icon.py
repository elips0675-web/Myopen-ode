#!/usr/bin/env python3
"""Generate a small app icon (PNG + ICO) for the desktop app without PIL."""
import struct, zlib, sys
from pathlib import Path

SIZE = 64
ASSETS = Path(__file__).resolve().parent.parent / "assets"


def make_png(size=SIZE):
    rows = []
    for y in range(size):
        row = bytearray([0])
        for x in range(size):
            d = min(x, y, size - 1 - x, size - 1 - y)
            r = min(255, int(16 + 3 * x))
            g = min(255, int(190 + 2 * y))
            b = min(255, int(16 + 3 * (size - 1 - x)))
            a = 255
            if d < 4:
                r, g, b = 220, 235, 250
            row += bytes((r, g, b, a))
        rows.append(bytes(row))
    raw = b"".join(rows)

    def chunk(tag, data):
        c = tag + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c))

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def png_to_ico(png, size=SIZE):
    header = struct.pack("<HHH", 0, 1, 1)
    entry = struct.pack("<BBBBHHII", size, size, 0, 0, 1, 32, len(png), 22)
    return header + entry + png


def main():
    ASSETS.mkdir(exist_ok=True)
    png = make_png()
    (ASSETS / "icon.png").write_bytes(png)
    (ASSETS / "icon.ico").write_bytes(png_to_ico(png))
    print(f"written {ASSETS / 'icon.png'} ({len(png)}b), "
          f"{ASSETS / 'icon.ico'}")


if __name__ == "__main__":
    main()
