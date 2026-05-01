"""
Changer Club — Premium Slide Renderer.

MZ Property Portfolio standard. Instagram carousel 1080 x 1350 (4:5).

Design grid:
  ┌──────────────────────────────┐
  │                    [LOGO]    │  8 % top / 8 % right
  │                              │  logo — top-right corner
  │                              │  transparent — photo breathes
  │       ░░░░░░░░░░░░░░░░░     │  gradient starts (33 %)
  │                              │
  │      HEADLINE  CAPS          │  centred, safe zone 70 % W
  │         ───────              │  70 px gap + divider
  │       body sentence          │  centred, Montserrat Light
  │  ████████████████████████    │  gradient max (bottom 33 %)
  └──────────────────────────────┘

Typography:
  Title — Cinzel Bold, UPPERCASE, letter-spaced
  Body  — Montserrat Light, 2.5× smaller, natural spacing
  Line height 1.45

Gradient:
  Upper third  → alpha 0 (transparent)
  Middle third → 0 → 180 (smooth ease)
  Lower third  → alpha 180 (near-black)
"""

import logging
import math
import os
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from config import FONTS_DIR, LOGO_TEXT, SLIDE_HEIGHT, SLIDE_WIDTH

logger = logging.getLogger(__name__)

# ── Canvas ──────────────────────────────────────────────────
TARGET: tuple[int, int] = (SLIDE_WIDTH, SLIDE_HEIGHT)  # 1080 × 1350

# ── Layout ratios ───────────────────────────────────────────
PAD_X = 0.15          # 15 % side padding (min 150 px enforced in code)
PAD_X_MIN = 150       # absolute minimum side padding in pixels
LOGO_TOP = 0.08       # 8 % from top
LOGO_RIGHT = 0.08     # 8 % from right edge
LOGO_W = 0.15         # logo image width = 15 % of slide (compact for corner)
TEXT_BOTTOM = 0.82     # text block bottom edge (safe zone end)
TITLE_RATIO = 0.060   # title font ≈ 6 % of width → ~65 px
BODY_DIV = 2.5        # body = title / 2.5
SPACING_K = 0.12      # letter-spacing = 12 % of title font size
LINE_H = 1.45         # line-height multiplier
GAP_PX = 70           # fixed gap between title & body (60-80 px range)
DIVIDER_W = 50        # decorative divider line width

# ── Gradient ────────────────────────────────────────────────
GRAD_ALPHA = 180       # max opacity (lower third)

# ── Font registry ──────────────────────────────────────────
_FONTS = {
    "cinzel": {
        "url": (
            "https://github.com/google/fonts/raw/main/ofl/cinzel/"
            "Cinzel%5Bwght%5D.ttf"
        ),
        "file": "Cinzel-Variable.ttf",
    },
    "montserrat": {
        "url": (
            "https://github.com/google/fonts/raw/main/ofl/montserrat/"
            "Montserrat%5Bwght%5D.ttf"
        ),
        "file": "Montserrat-Variable.ttf",
    },
}

_FALLBACK_SERIF = [
    "C:/Windows/Fonts/georgiabd.ttf",
    "C:/Windows/Fonts/georgia.ttf",
    "C:/Windows/Fonts/timesbd.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
]
_FALLBACK_SANS = [
    "C:/Windows/Fonts/segoeuil.ttf",   # Segoe UI Light
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Light.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


# ── Font management ─────────────────────────────────────────

def _download_font(key: str) -> None:
    """Download Google Font to FONTS_DIR if not cached."""
    os.makedirs(FONTS_DIR, exist_ok=True)
    cfg = _FONTS[key]
    dest = Path(FONTS_DIR) / cfg["file"]
    if dest.exists():
        return
    try:
        urllib.request.urlretrieve(cfg["url"], str(dest))
        logger.info("Downloaded font: %s", cfg["file"])
    except Exception as exc:
        logger.warning("Font download failed (%s): %s", cfg["file"], exc)


def _load_font(key: str, size: int, weight: int = 400) -> ImageFont.FreeTypeFont:
    """Load variable font at *weight*, fall back to system fonts."""
    _download_font(key)
    cfg = _FONTS[key]
    path = Path(FONTS_DIR) / cfg["file"]

    if path.exists():
        try:
            font = ImageFont.truetype(str(path), size)
            try:
                font.set_variation_by_axes([weight])
            except Exception:
                pass
            return font
        except Exception:
            pass

    fallbacks = _FALLBACK_SERIF if key == "cinzel" else _FALLBACK_SANS
    for fb in fallbacks:
        if Path(fb).exists():
            try:
                return ImageFont.truetype(fb, size)
            except Exception:
                continue

    logger.warning("No suitable font for '%s' — using Pillow default", key)
    return ImageFont.load_default()


# ── Drawing primitives ──────────────────────────────────────

def _measure_spaced(draw: ImageDraw.Draw, text: str,
                    font: ImageFont.FreeTypeFont, spacing: float) -> float:
    """Measure total width of *text* with per-character *spacing*."""
    if not text:
        return 0
    total = 0.0
    for i, ch in enumerate(text):
        total += draw.textlength(ch, font=font)
        if i < len(text) - 1:
            total += spacing
    return total


def _draw_spaced(draw: ImageDraw.Draw, pos: tuple[float, float], text: str,
                 font: ImageFont.FreeTypeFont, fill: tuple, spacing: float,
                 shadow: tuple | None = None) -> None:
    """Render *text* character-by-character with *spacing* and optional shadow."""
    x, y = pos
    for i, ch in enumerate(text):
        if shadow:
            sx, sy, sc = shadow
            draw.text((x + sx, y + sy), ch, font=font, fill=sc)
        draw.text((x, y), ch, font=font, fill=fill)
        x += draw.textlength(ch, font=font)
        if i < len(text) - 1:
            x += spacing


def _wrap_lines(draw: ImageDraw.Draw, text: str,
                font: ImageFont.FreeTypeFont, spacing: float,
                max_w: float) -> list[str]:
    """Word-wrap *text* respecting letter-spacing."""
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    buf: list[str] = []
    for word in words:
        candidate = " ".join(buf + [word])
        if buf and _measure_spaced(draw, candidate, font, spacing) > max_w:
            lines.append(" ".join(buf))
            buf = [word]
        else:
            buf.append(word)
    if buf:
        lines.append(" ".join(buf))
    return lines or [""]


# ── Image processing ────────────────────────────────────────

def _crop_to_target(path: str) -> Image.Image:
    """Open *path*, centre-crop to 4:5, resize to TARGET."""
    img = Image.open(path).convert("RGB")
    tw, th = TARGET
    sw, sh = img.size
    if sw / sh > tw / th:
        nw = int(sh * tw / th)
        x = (sw - nw) // 2
        img = img.crop((x, 0, x + nw, sh))
    else:
        nh = int(sw * th / tw)
        y = (sh - nh) // 2
        img = img.crop((0, y, sw, y + nh))
    return img.resize(TARGET, Image.LANCZOS)


def _draw_gradient_overlay(img: Image.Image) -> Image.Image:
    """
    Premium bottom-up gradient (three-zone, smooth ease).

    Upper  third (0 – 33 %):  alpha 0     → photo untouched
    Middle third (33 – 67 %): 0 → 180     → smooth S-curve transition
    Lower  third (67 – 100 %): alpha 180  → text contrast zone
    """
    w, h = img.size
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw_ov = ImageDraw.Draw(overlay)

    zone_top = h / 3.0
    zone_bot = 2.0 * h / 3.0

    for y in range(h):
        if y <= zone_top:
            alpha = 0
        elif y >= zone_bot:
            alpha = GRAD_ALPHA
        else:
            t = (y - zone_top) / (zone_bot - zone_top)
            t = (1.0 - math.cos(t * math.pi)) / 2.0   # ease in-out
            alpha = int(t * GRAD_ALPHA)
        draw_ov.line([(0, y), (w, y)], fill=(0, 0, 0, alpha))

    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


# ── Logo ────────────────────────────────────────────────────

def _place_logo(img: Image.Image, logo_override: str | None = None) -> Image.Image:
    """Place logo in the **top-right corner** (8 % from top, 8 % from right)."""
    w, h = img.size
    y = int(h * LOGO_TOP)
    margin_r = int(w * LOGO_RIGHT)

    # Try image logo first
    logo_path = Path(logo_override) if logo_override else Path("logo.png")
    if logo_path.exists():
        try:
            logo = Image.open(logo_path).convert("RGBA")
            target_w = int(w * LOGO_W)
            ratio = target_w / logo.width
            target_h = int(logo.height * ratio)
            logo = logo.resize((target_w, target_h), Image.LANCZOS)
            x = w - target_w - margin_r              # right-aligned
            img.paste(logo, (x, y), logo)
            return img
        except Exception as exc:
            logger.warning("Could not load logo image: %s", exc)

    # Text fallback — elegant spaced serif, right-aligned
    draw = ImageDraw.Draw(img)
    size = int(w * 0.022)                          # ~24 px
    font = _load_font("cinzel", size, weight=400)
    spacing = size * 0.50                           # wide tracking for logo
    text = logo_override or LOGO_TEXT

    tw = _measure_spaced(draw, text, font, spacing)
    x = w - int(tw) - margin_r                      # right-aligned
    shadow = (1, 1, (0, 0, 0))
    _draw_spaced(draw, (x, y), text, font, (255, 255, 255), spacing, shadow)
    return img


# ── Text block ──────────────────────────────────────────────

def _draw_text_block(img: Image.Image, headline: str, subtitle: str) -> Image.Image:
    """
    Draw headline + subtitle, both **centred horizontally** in the safe zone.

    Title:  Cinzel Bold 700, UPPERCASE, letter-spaced, white + shadow.
    Body:   Montserrat Light 300, natural spacing, light grey.
    Gap:    70 px + thin decorative divider line.
    """
    draw = ImageDraw.Draw(img)
    w, h = img.size

    pad_x = max(int(w * PAD_X), PAD_X_MIN)          # ≥ 150 px
    max_w = w - 2 * pad_x                            # ~70 % of width

    # ── Title setup ──
    title_size = int(w * TITLE_RATIO)                # ~65 px
    title_font = _load_font("cinzel", title_size, weight=700)
    title_spacing = title_size * SPACING_K           # ~7.8 px
    title_line_h = int(title_size * LINE_H)

    title_lines = _wrap_lines(draw, headline.upper(), title_font,
                              title_spacing, max_w)

    # ── Body setup ──
    body_size = int(title_size / BODY_DIV)           # ~26 px
    body_font = _load_font("montserrat", body_size, weight=300)
    body_spacing = 0.0                                # natural for body
    body_line_h = int(body_size * LINE_H)

    body_lines = _wrap_lines(draw, subtitle, body_font, body_spacing, max_w)

    # ── Compute total block height, bottom-align in safe zone ──
    block_h = (len(title_lines) * title_line_h
               + GAP_PX
               + len(body_lines) * body_line_h)

    bottom = int(h * TEXT_BOTTOM)
    top_y = bottom - block_h
    # Clamp: never go above 20 % of height (safe zone top)
    top_y = max(top_y, int(h * 0.20))

    y = top_y
    shadow = (2, 2, (0, 0, 0))

    # ── Draw title lines (centred) ──
    for line in title_lines:
        lw = _measure_spaced(draw, line, title_font, title_spacing)
        x = (w - lw) / 2                             # centred horizontally
        _draw_spaced(draw, (x, y), line, title_font,
                     (255, 255, 255), title_spacing, shadow)
        y += title_line_h

    # ── Decorative divider ──
    div_y = int(y + GAP_PX * 0.45)
    div_x = (w - DIVIDER_W) // 2
    draw.line([(div_x, div_y), (div_x + DIVIDER_W, div_y)],
              fill=(255, 255, 255), width=1)

    y += GAP_PX

    # ── Draw body lines (centred) ──
    for line in body_lines:
        lw = draw.textlength(line, font=body_font)
        x = (w - lw) / 2                             # centred horizontally
        draw.text((x + 2, y + 1), line, font=body_font, fill=(0, 0, 0))
        draw.text((x, y), line, font=body_font, fill=(200, 200, 200))
        y += body_line_h

    return img


# ── Public API ──────────────────────────────────────────────

def create_slide(
    input_path: str,
    headline: str,
    subtitle: str,
    output_path: str,
    logo: str | None = None,
) -> str:
    """
    Render a premium branded Instagram slide.

    Pipeline:
      1. Crop & resize photo to 1080 × 1350
      2. Apply bottom-up gradient overlay
      3. Place logo (image or text) at top-right corner
      4. Draw headline + subtitle in the lower safe zone
      5. Save as high-quality JPEG

    Returns the *output_path* on success.
    """
    os.makedirs(Path(output_path).parent, exist_ok=True)

    img = _crop_to_target(input_path)
    img = _draw_gradient_overlay(img)
    img = _place_logo(img, logo)
    img = _draw_text_block(img, headline, subtitle)

    img.save(output_path, "JPEG", quality=95, optimize=True)
    logger.info("Slide saved: %s", output_path)
    return output_path
