"""Pillow-composited key faces for the Discord actions.

Uses the authentic Discord state icons (blurple=normal, red=muted/deafened)
embedded in discord_icons.py, with the voice volume number overlaid. Module
functions only, so ActionFactory's Action-subclass scan finds nothing here.
"""

import base64
import io

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFont

from . import discord_icons

SIZE = 108

WHITE = (255, 255, 255, 255)
GRAY = (120, 120, 120, 255)
BOOST = (255, 176, 32, 225)  # amber overfill for the 100-200 boost range
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


_glyph_cache = {}


def _glyph_mask(b64):
    """Mask of the white glyph (mic/headphones) inside the icon — the near-white
    pixels — so it can be re-asserted on top of the boost overfill."""
    if b64 not in _glyph_cache:
        icon = _load_icon(b64)
        bright = icon.convert("L").point(lambda p: 255 if p > 200 else 0)
        _glyph_cache[b64] = ImageChops.multiply(bright, icon.getchannel("A"))
    return _glyph_cache[b64]


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
    gauge. 0-100 fills the circle in the state color (blue when live, red when
    muted/deafened); 100-200 overfills the full circle with the amber BOOST
    color rising from the bottom again. Volume number in the corner."""
    icon = _load_icon(ICON_FOR[kind])
    result = ImageEnhance.Brightness(icon).enhance(DIM)  # dim "empty" gauge
    v = max(0.0, min(volume, 200.0))

    # 0-100: bright state-color fill, full circle at 100
    h1 = int(min(v, 100.0) / 100.0 * SIZE)
    if h1 > 0:
        y0 = SIZE - h1
        region = icon.crop((0, y0, SIZE, SIZE))
        result.paste(region, (0, y0), region)

    # 100-200: amber boost overfill, clipped to the circle via the icon's alpha
    if v > 100.0:
        h2 = int((v - 100.0) / 100.0 * SIZE)
        if h2 > 0:
            y0 = SIZE - h2
            box = (0, y0, SIZE, SIZE)
            accent = Image.new("RGBA", (SIZE, SIZE), BOOST)
            result.paste(accent.crop(box), (0, y0), icon.getchannel("A").crop(box))
            # keep the white glyph crisp on top of the amber
            white = Image.new("RGBA", (SIZE, SIZE), WHITE)
            result.paste(white.crop(box), (0, y0), _glyph_mask(ICON_FOR[kind]).crop(box))

    _draw_volume_number(ImageDraw.Draw(result), volume)
    return _to_data_url(result)
