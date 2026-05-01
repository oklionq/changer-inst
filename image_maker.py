"""
Changer Club AI Content Factory — slide image renderer.

Creates Instagram carousel slides (1080x1350, 4:5 portrait) by overlaying
branded text on event photos.

Design spec:
  - Full-bleed photo, cropped/resized to 1080x1350
  - Dark gradient overlay: transparent top 28% -> ~85 % opacity at bottom
  - Logo: small centered text near top, flanked by thin decorative lines
  - Headline: large serif ALL CAPS, left-aligned, starts ~60 % height
  - Subtitle: smaller serif, light grey, below headline

Fonts: Playfair Display Bold / Regular (auto-downloaded from Google Fonts).
"""

import logging
import os
import textwrap
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from config import FONTS_DIR, LOGO_TEXT, SLIDE_HEIGHT, SLIDE_WIDTH

logger = logging.getLogger(__name__)

TARGET_SIZE: tuple[int, int] = (SLIDE_WIDTH, SLIDE_HEIGHT)

# ------------------------------------------------------------------
# Font management
# ------------------------------------------------------------------

_VAR_FONT_URL: str = (
    "https://github.com/google/fonts/raw/main/ofl/playfairdisplay/"
    "PlayfairDisplay%5Bwght%5D.ttf"
)
_VAR_FONT_FILE: str = "PlayfairDisplay-Variable.ttf"

# System fallbacks (cross-platform)
_FALLBACK_PATHS_BOLD: list[str] = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
    "C:/Windows/Fonts/timesbd.ttf",
    "C:/Windows/Fonts/georgiabd.ttf",
]
_FALLBACK_PATHS_REG: list[str] = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
    "C:/Windows/Fonts/times.ttf",
    "C:/Windows/Fonts/georgia.ttf",
]


def _ensure_fonts() -> None:
    """Download Playfair Display variable font from Google Fonts if not cached."""
    os.makedirs(FONTS_DIR, exist_ok=True)
    dest = Path(FONTS_DIR) / _VAR_FONT_FILE
    if not dest.exists():
        try:
            urllib.request.urlretrieve(_VAR_FONT_URL, str(dest))
            logger.info("Downloaded variable font %s", _VAR_FONT_FILE)
        except Exception as exc:
            logger.warning("Could not download %s: %s", _VAR_FONT_FILE, exc)


def _font_path() -> str:
    """Return the best available font file path (Playfair > system fallback)."""
    _ensure_fonts()
    path = Path(FONTS_DIR) / _VAR_FONT_FILE
    if path.exists():
        return str(path)

    # Also check legacy static files in case user placed them manually
    for name in ("PlayfairDisplay-Bold.ttf", "PlayfairDisplay-Regular.ttf"):
        p = Path(FONTS_DIR) / name
        if p.exists():
            return str(p)

    for fb in _FALLBACK_PATHS_BOLD + _FALLBACK_PATHS_REG:
        if Path(fb).exists():
            logger.info("Using fallback font: %s", fb)
            return fb

    logger.warning("No suitable font found — using Pillow default")
    return ""


# ------------------------------------------------------------------
# Image processing
# ------------------------------------------------------------------


def _load_and_crop(path: str) -> Image.Image:
    """Open *path*, crop to 4:5 centre, resize to target."""
    img = Image.open(path).convert("RGB")
    tw, th = TARGET_SIZE
    sw, sh = img.size
    if (sw / sh) > (tw / th):
        new_w = int(sh * tw / th)
        x = (sw - new_w) // 2
        img = img.crop((x, 0, x + new_w, sh))
    else:
        new_h = int(sw * th / tw)
        y = (sh - new_h) // 2
        img = img.crop((0, y, sw, y + new_h))
    return img.resize(TARGET_SIZE, Image.LANCZOS)


def _apply_dark_gradient(img: Image.Image) -> Image.Image:
    """Apply a bottom-heavy dark gradient overlay (~0 % -> ~85 % opacity)."""
    w, h = img.size
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    start_y = int(h * 0.28)
    for y in range(start_y, h):
        t = (y - start_y) / (h - start_y)
        alpha = int((t ** 1.25) * 218)
        draw.line([(0, y), (w, y)], fill=(0, 0, 0, alpha))
    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


# ------------------------------------------------------------------
# Drawing helpers
# ------------------------------------------------------------------


def _safe_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load Playfair Display at *size*, falling back to Pillow default.

    For variable fonts, Pillow >=10.1 supports ``variation_name``; for
    older versions or static fonts it loads the default axis values.
    """
    path = _font_path()
    if path:
        try:
            font = ImageFont.truetype(path, size)
            try:
                axes = font.get_variation_names()
                target = "Bold" if bold else "Regular"
                if target.encode() in axes:
                    font.set_variation_by_name(target)
                elif bold:
                    font.set_variation_by_axes([700])
                else:
                    font.set_variation_by_axes([400])
            except Exception:
                pass
            return font
        except Exception:
            pass
    return ImageFont.load_default()


def _draw_logo(draw: ImageDraw.Draw, w: int, h: int, logo: str) -> None:
    """Draw the brand logo centred near the top with flanking lines."""
    size = int(w * 0.029)
    font = _safe_font(size, bold=True)

    logo_w = int(draw.textlength(logo, font=font))
    lx = (w - logo_w) // 2
    ly = int(h * 0.050)

    line_y = ly + size // 2
    line_len = int(w * 0.095)
    margin = 20
    gray = (200, 200, 200)

    left_x2 = lx - margin
    left_x1 = left_x2 - line_len
    right_x1 = lx + logo_w + margin
    right_x2 = right_x1 + line_len

    draw.line([(max(0, left_x1), line_y), (left_x2, line_y)], fill=gray, width=1)
    draw.line([(right_x1, line_y), (min(w, right_x2), line_y)], fill=gray, width=1)
    draw.text((lx, ly), logo, font=font, fill=(255, 255, 255))


def _draw_text_block(
    draw: ImageDraw.Draw, w: int, h: int, headline: str, subtitle: str
) -> None:
    """Draw headline + subtitle in the lower portion of the slide."""
    pad = int(w * 0.072)
    text_w = w - 2 * pad

    # Headline
    hl_size = int(w * 0.082)
    hl_font = _safe_font(hl_size, bold=True)
    hl_chars = max(8, int(text_w / (hl_size * 0.57)))
    hl_lines = textwrap.fill(headline.upper(), width=hl_chars).split("\n")
    hl_line_h = int(hl_size * 1.16)

    # Subtitle
    sub_size = int(w * 0.037)
    sub_font = _safe_font(sub_size, bold=False)
    sub_chars = max(15, int(text_w / (sub_size * 0.52)))
    sub_lines = textwrap.fill(subtitle, width=sub_chars).split("\n")
    sub_line_h = int(sub_size * 1.55)

    gap = int(h * 0.022)
    total_h = len(hl_lines) * hl_line_h + gap + len(sub_lines) * sub_line_h
    y = int(h * 0.595)
    if y + total_h > h - pad:
        y = h - pad - total_h

    for line in hl_lines:
        draw.text((pad + 2, y + 2), line, font=hl_font, fill=(0, 0, 0))
        draw.text((pad, y), line, font=hl_font, fill=(255, 255, 255))
        y += hl_line_h

    y += gap

    for line in sub_lines:
        draw.text((pad, y), line, font=sub_font, fill=(195, 195, 195))
        y += sub_line_h


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------


def create_slide(
    input_path: str,
    headline: str,
    subtitle: str,
    output_path: str,
    logo: str | None = None,
) -> str:
    """Render a single branded Instagram slide and save to *output_path*.

    Returns the output path on success.
    """
    logo = logo or LOGO_TEXT
    os.makedirs(Path(output_path).parent, exist_ok=True)

    img = _load_and_crop(input_path)
    img = _apply_dark_gradient(img)

    draw = ImageDraw.Draw(img)
    w, h = img.size

    _draw_logo(draw, w, h, logo)
    _draw_text_block(draw, w, h, headline, subtitle)

    img.save(output_path, "JPEG", quality=95, optimize=True)
    logger.info("Slide saved: %s", output_path)
    return output_path
