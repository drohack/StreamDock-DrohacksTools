"""Pillow-composited key faces for the Discord actions.

Uses the authentic Discord state icons (blurple=normal, red=muted/deafened)
embedded in discord_icons.py, with the voice volume number overlaid. Module
functions only, so ActionFactory's Action-subclass scan finds nothing here.
"""

import base64
import io

from PIL import Image, ImageDraw, ImageEnhance, ImageFont

from . import discord_icons

SIZE = 108

WHITE = (255, 255, 255, 255)
GRAY = (120, 120, 120, 255)
DIM = 0.28  # brightness of the icon above the volume fill line

# Short labels for non-ready connection states (drawn as the key title)
STATE_LABELS = {
    "no_creds": "Setup",
    "needs_connect": "Connect",
    "no_discord": "No\nDiscord",
    "connecting": "...",
    "awaiting_approval": "Approve\nin app",
    "authenticating": "Auth...",
    "auth_failed": "Auth\nfailed",
}

_icon_cache = {}


def _font(size):
    for name in ("arialbd.ttf", "arial.ttf", "segoeui.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _load_icon(b64):
    if b64 not in _icon_cache:
        _icon_cache[b64] = Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGBA")
    return _icon_cache[b64]


def _to_data_url(img: Image.Image) -> str:
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()


def _draw_volume_number(draw, volume):
    """Volume readout in the bottom-right, white with a dark outline so it's
    legible over the blurple/red icon circle."""
    txt = str(int(round(volume)))
    font = _font(30)
    bbox = draw.textbbox((0, 0), txt, font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x, y = SIZE - w - 6, SIZE - h - 12
    draw.text((x, y), txt, font=font, fill=WHITE,
              stroke_width=3, stroke_fill=(0, 0, 0, 220))


ICON_FOR = {
    "mic": discord_icons.MIC,
    "muted": discord_icons.MIC_MUTED,
    "deafened": discord_icons.DEAFENED,
}


def state_face() -> str:
    """Dim background used while not connected (title carries the state)."""
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, SIZE - 8, SIZE, SIZE], fill=GRAY)
    return _to_data_url(img)


def icon_face(kind: str, volume: float) -> str:
    """Authentic Discord icon (mic / muted / deafened) rendered as a volume
    gauge: the icon's colored background (blue when live, red when muted or
    deafened) is bright up to the volume level and dimmed above it, so the
    fill rises/falls with the percentage. Volume number in the corner."""
    icon = _load_icon(ICON_FOR[kind])
    result = ImageEnhance.Brightness(icon).enhance(DIM)  # dim "empty" gauge
    fill_h = int(max(0.0, min(volume, 200.0)) / 200.0 * SIZE)
    if fill_h > 0:
        y0 = SIZE - fill_h
        region = icon.crop((0, y0, SIZE, SIZE))
        result.paste(region, (0, y0), region)  # bright fill from the bottom up
    _draw_volume_number(ImageDraw.Draw(result), volume)
    return _to_data_url(result)
