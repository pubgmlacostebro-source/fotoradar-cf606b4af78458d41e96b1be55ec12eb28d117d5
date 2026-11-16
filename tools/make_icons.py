"""Рисует иконки сайта (объектив) без сторонних библиотек: python tools/make_icons.py"""
import math
import struct
import zlib
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "docs"
BG, RING, GLASS, ACCENT = (23, 20, 31), (241, 237, 247), (43, 36, 56), (255, 180, 84)


def mix(a, b, t):
    t = max(0.0, min(1.0, t))
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def pixel(x, y, n):
    cx = cy = (n - 1) / 2
    r = math.hypot(x - cx, y - cy) / n
    aa = 1.5 / n
    col = BG
    col = mix(col, RING, (0.36 - r) / aa)       # внешнее кольцо
    col = mix(col, GLASS, (0.30 - r) / aa)      # стекло
    col = mix(col, ACCENT, (0.17 - r) / aa)     # диафрагма
    col = mix(col, BG, (0.09 - r) / aa)         # зрачок
    hl = math.hypot(x - cx + 0.11 * n, y - cy + 0.11 * n) / n
    return mix(col, RING, (0.035 - hl) / aa)    # блик


def png(n):
    raw = b"".join(b"\x00" + bytes(c for x in range(n) for c in pixel(x, y, n)) for y in range(n))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", n, n, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


for size in (192, 512):
    (OUT / f"icon-{size}.png").write_bytes(png(size))
    print("ok", size)
