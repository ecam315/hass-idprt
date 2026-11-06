"""Render a niimbot.print-style payload to a 1-bit label image.

Pure Pillow, no Home Assistant imports, so it can be tested on its own.
Supported element types: text, multiline, rectangle, line, icon, qrcode.
Coordinates and sizes are in the payload's canvas pixels (default 591x354).
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

_LOGGER = logging.getLogger(__name__)

FONT_DIR = Path(__file__).parent / "fonts"
TEXT_FONT = FONT_DIR / "DejaVuSans-Bold.ttf"
ICON_FONT = FONT_DIR / "materialdesignicons-webfont.ttf"
ICON_MAP = FONT_DIR / "mdi_map.json"


@lru_cache(maxsize=64)
def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, max(int(size), 1))


@lru_cache(maxsize=1)
def _icon_map() -> dict[str, int]:
    return json.loads(ICON_MAP.read_text())


def _color(value: Any, default: int | None = 0) -> int | None:
    """Map a colour name to L-mode grey. Anything not white/none prints black."""
    if value is None:
        return default
    v = str(value).strip().lower()
    if v in ("none", "transparent", ""):
        return None
    if v in ("white", "#fff", "#ffffff", "w"):
        return 255
    return 0


def _num(el: dict, key: str, default: float = 0) -> float:
    try:
        return float(el.get(key, default))
    except (TypeError, ValueError):
        return default


def _fit_font(draw: ImageDraw.ImageDraw, text: str, x: float, size: int,
              canvas_w: int, anchor: str) -> ImageFont.FreeTypeFont:
    """Shrink text that would run off the right edge (long customer names)."""
    font = _font(str(TEXT_FONT), size)
    if anchor[0] != "l":
        return font
    while size > 10:
        right = draw.textbbox((x, 0), text, font=font, anchor=anchor)[2]
        if right <= canvas_w - 2:
            break
        size = int(size * 0.92)
        font = _font(str(TEXT_FONT), size)
    return font


def _wrap(draw, text: str, font, width: float) -> list[str]:
    """Greedy word wrap to `width` px; words longer than a line are split."""
    def fits(s: str) -> bool:
        return draw.textlength(s, font=font) <= width

    lines: list[str] = []
    for para in text.split("\n"):
        line = ""
        for word in para.split():
            cand = f"{line} {word}" if line else word
            if fits(cand):
                line = cand
                continue
            if line:
                lines.append(line)
            while not fits(word) and len(word) > 1:
                cut = len(word) - 1
                while cut > 1 and not fits(word[:cut]):
                    cut -= 1
                lines.append(word[:cut])
                word = word[cut:]
            line = word
        lines.append(line)
    return lines


def _draw_wrapped(draw, el, text: str, x: float, y: float, canvas_w: int, canvas_h: int):
    """Wrap text inside max_width. If max_height is given (default: to the
    bottom of the label), step the size down only until the wrapped block fits."""
    width = min(_num(el, "max_width"), canvas_w - x - 2)
    max_h = _num(el, "max_height", canvas_h - y - 2)
    size = int(_num(el, "size", 20))
    spacing = _num(el, "line_spacing", 1.15)
    while True:
        font = _font(str(TEXT_FONT), size)
        lines = _wrap(draw, text, font, width)
        step = size * spacing
        if len(lines) * step - (step - size) <= max_h or size <= 12:
            break
        size -= 1
    fill = _color(el.get("color", "black"))
    for i, line in enumerate(lines):
        draw.text((x, y + i * step), line, fill=fill, font=font, anchor="lt")


def _draw_text(draw, el, canvas_w, canvas_h=10_000):
    text = str(el.get("value", ""))
    if not text:
        return
    x, y = _num(el, "x"), _num(el, "y")
    anchor = str(el.get("anchor", "lt"))
    if el.get("max_width") and anchor[0] == "l":
        _draw_wrapped(draw, el, text, x, y, canvas_w, canvas_h)
        return
    size = int(_num(el, "size", 20))
    font = _fit_font(draw, text, x, size, canvas_w, anchor) if el.get("fit", True) \
        else _font(str(TEXT_FONT), size)
    draw.text((x, y), text, fill=_color(el.get("color", "black")), font=font, anchor=anchor)


def _draw_multiline(draw, el, canvas_w):
    delim = str(el.get("delimiter", "|"))
    lines = str(el.get("value", "")).split(delim)
    y = _num(el, "start_y", _num(el, "y"))
    step = _num(el, "offset_y", _num(el, "size", 20) * 1.2)
    for line in lines:
        _draw_text(draw, {**el, "value": line, "y": y}, canvas_w)
        y += step


def _draw_rectangle(draw, el):
    box = [_num(el, "x_start"), _num(el, "y_start"), _num(el, "x_end"), _num(el, "y_end")]
    fill = _color(el.get("fill"), None)
    outline = _color(el.get("outline"), None if fill is not None else 0)
    draw.rectangle(box, fill=fill, outline=outline, width=int(_num(el, "width", 1)))


def _draw_line(draw, el):
    pts = [_num(el, "x_start"), _num(el, "y_start"), _num(el, "x_end"), _num(el, "y_end")]
    draw.line(pts, fill=_color(el.get("fill", el.get("color", "black"))), width=int(_num(el, "width", 2)))


def _draw_icon(draw, el):
    name = str(el.get("value", "")).removeprefix("mdi:").strip()
    code = _icon_map().get(name)
    if code is None:
        _LOGGER.warning("Unknown mdi icon %r, skipped", name)
        return
    font = _font(str(ICON_FONT), int(_num(el, "size", 40)))
    draw.text((_num(el, "x"), _num(el, "y")), chr(code),
              fill=_color(el.get("color", el.get("fill", "black"))),
              font=font, anchor=str(el.get("anchor", "la")))


def _draw_qrcode(img, el):
    try:
        import qrcode  # type: ignore[import-not-found]
    except ImportError:
        _LOGGER.warning("qrcode library not installed; qrcode element skipped")
        return
    box = int(_num(el, "boxsize", 2))
    qr = qrcode.QRCode(border=int(_num(el, "border", 1)), box_size=box)
    qr.add_data(str(el.get("data", el.get("value", ""))))
    qr.make(fit=True)
    q = qr.make_image(fill_color="black", back_color="white").convert("L")
    img.paste(q, (int(_num(el, "x")), int(_num(el, "y"))))


def render_payload(payload: list[dict] | str, width: int, height: int,
                   rotate: int = 0) -> Image.Image:
    """Draw the payload on a white greyscale canvas of width x height."""
    if isinstance(payload, str):
        payload = json.loads(payload)
    img = Image.new("L", (int(width), int(height)), 255)
    draw = ImageDraw.Draw(img)
    for el in payload or []:
        if not isinstance(el, dict):
            continue
        kind = str(el.get("type", "")).lower()
        if el.get("visible", True) in (False, "false"):
            continue
        if kind == "text":
            _draw_text(draw, el, img.width, img.height)
        elif kind == "multiline":
            _draw_multiline(draw, el, img.width)
        elif kind == "rectangle":
            _draw_rectangle(draw, el)
        elif kind == "line":
            _draw_line(draw, el)
        elif kind == "icon":
            _draw_icon(draw, el)
        elif kind == "qrcode":
            _draw_qrcode(img, el)
        else:
            _LOGGER.warning("Unsupported payload element type %r, skipped", kind)
    if rotate:
        img = img.rotate(-int(rotate), expand=True, fillcolor=255)
    return img


def to_label(img: Image.Image, dots_w: int, dots_h: int) -> Image.Image:
    """Scale the canvas onto the printer's dot grid without distorting it
    (fit inside, centred on white), then threshold to 1-bit."""
    scale = min(dots_w / img.width, dots_h / img.height)
    w = max(1, round(img.width * scale))
    h = max(1, round(img.height * scale))
    scaled = Image.new("L", (dots_w, dots_h), 255)
    scaled.paste(img.resize((w, h), Image.Resampling.LANCZOS),
                 ((dots_w - w) // 2, (dots_h - h) // 2))
    return scaled.point(lambda p: 255 if p >= 140 else 0).convert("1", dither=Image.Dither.NONE)
