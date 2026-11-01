"""Build TSPL print jobs. Pure Python, no Home Assistant imports."""
from __future__ import annotations

from PIL import Image, ImageOps


def mm_to_dots(mm: float, dpi: int) -> int:
    return round(mm / 25.4 * dpi)


def build_bitmap_job(label: Image.Image, *, width_mm: float, height_mm: float,
                     gap_mm: float, density: int, speed: int, direction: int,
                     x_offset_mm: float = 0.0, y_offset_mm: float = 0.0,
                     dpi: int = 203, copies: int = 1, invert: bool = False) -> bytes:
    """Return a complete TSPL job printing `label` (mode "1") once per copy.

    TSPL BITMAP data: 1 bit per dot, MSB first, rows top to bottom, and a
    0 bit prints black. Pillow packs mode "1" the same way (black = 0), so
    the bytes go out as-is unless `invert` is set for odd firmware.
    """
    img = label.convert("1")
    pad_w = (img.width + 7) // 8 * 8
    if pad_w != img.width:
        padded = Image.new("1", (pad_w, img.height), 1)
        padded.paste(img, (0, 0))
        img = padded
    if invert:
        img = ImageOps.invert(img.convert("L")).convert("1", dither=Image.Dither.NONE)
    data = img.tobytes()

    x = mm_to_dots(x_offset_mm, dpi)
    y = mm_to_dots(y_offset_mm, dpi)
    head = (
        f"SIZE {width_mm:g} mm,{height_mm:g} mm\r\n"
        f"GAP {gap_mm:g} mm,0 mm\r\n"
        f"DIRECTION {int(direction)},0\r\n"
        "REFERENCE 0,0\r\n"
        f"DENSITY {max(0, min(15, int(density)))}\r\n"
        f"SPEED {max(1, int(speed))}\r\n"
        "SET TEAR ON\r\n"
        "CLS\r\n"
        f"BITMAP {x},{y},{pad_w // 8},{img.height},0,"
    ).encode("ascii")
    tail = f"\r\nPRINT 1,{max(1, int(copies))}\r\n".encode("ascii")
    return head + data + tail
