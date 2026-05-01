"""
AI-powered photo selection from the library.
Step 1: sends thumbnails to GPT-4o for cheap selection.
Step 2: returns full-res paths of selected photos.

Token budget (detail=low): 85 tokens per image.
With MAX_GALLERY_SAMPLE=20 → ~1 700 image tokens + text ≈ 3-4k total.
Well within 30k TPM limit.
"""

import base64
import io
import json
import logging
from pathlib import Path

from openai import OpenAI
from PIL import Image

from config import OPENAI_API_KEY, OPENAI_MODEL, PHOTOS_DIR

logger = logging.getLogger(__name__)

client = OpenAI(api_key=OPENAI_API_KEY)

SUPPORTED = {".jpg", ".jpeg", ".png", ".webp"}
THUMB_SIZE = 512
MIN_PHOTOS = 3
MAX_PHOTOS = 8
MAX_GALLERY_SAMPLE = 20  # max photos sent to AI for selection


def _get_all_photos() -> list[Path]:
    """Returns all image paths in PHOTOS_DIR, sorted newest-first (by mtime)."""
    folder = Path(PHOTOS_DIR)
    if not folder.exists():
        return []
    photos = [p for p in folder.iterdir() if p.suffix.lower() in SUPPORTED]
    photos.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return photos


def _make_thumbnail_b64(path: Path) -> str:
    """Resize to thumbnail and return base64 JPEG string."""
    img = Image.open(path).convert("RGB")
    w, h = img.size
    scale = THUMB_SIZE / max(w, h)
    if scale < 1.0:
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=75)
    return base64.standard_b64encode(buf.getvalue()).decode("utf-8")


SELECTOR_SYSTEM = """You are a visual content strategist for Changer Club — 
a private wealth club for ultra-high-net-worth entrepreneurs (5M+ liquid assets).

Your task: select the best photos for an Instagram carousel on a given topic.

SELECTION CRITERIA — choose photos that:
- Signal power, focus, or real decision-making moments
- Feel authentic (not staged smiles, not generic networking shots)
- Show proximity to influence: rooms, gestures, conversations, environments
- Could belong to a billionaire's private archive
- Together tell a coherent visual story

REJECT photos that are:
- Generic group smiles at camera
- Empty rooms or generic venue shots without people or tension
- Redundant (very similar to another selected photo)

Return ONLY valid JSON. No explanation, no markdown."""

SELECTOR_PROMPT = """Topic for the carousel: {topic}

You are looking at {n} photos from Changer Club events (numbered 0 to {last}).

Select the best {min_n}–{max_n} photos for this topic.
Order them as they should appear in the carousel (narrative arc matters).

Return JSON:
{{
  "selected": [0, 3, 7, ...],
  "reasoning": "one sentence why this set works for the topic"
}}

Only return the JSON object."""


def select_photos(topic: str) -> tuple[list[str], str]:
    """
    Returns (list_of_full_res_paths, reasoning_string).

    Flow:
      1. Collect all photos, take at most MAX_GALLERY_SAMPLE (newest first).
      2. Send low-detail thumbnails (512px, 85 tok each) to GPT-4o.
      3. GPT returns indices → map back to original full-res paths.

    Raises ValueError if no photos found in library.
    """
    all_photos = _get_all_photos()  # newest first
    if not all_photos:
        raise ValueError(f"No photos found in '{PHOTOS_DIR}/' folder.")

    # --- Limit: send at most MAX_GALLERY_SAMPLE photos to the API ---
    sample = all_photos[:MAX_GALLERY_SAMPLE]
    if len(all_photos) > MAX_GALLERY_SAMPLE:
        logger.info(
            "Gallery has %d photos, sending %d newest to AI for selection",
            len(all_photos), MAX_GALLERY_SAMPLE,
        )

    n = len(sample)

    # --- Build vision payload with compressed thumbnails ---
    content: list[dict] = []
    for i, path in enumerate(sample):
        b64 = _make_thumbnail_b64(path)
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "low"},
        })
        content.append({"type": "text", "text": f"[Photo {i}] {path.name}"})

    prompt = SELECTOR_PROMPT.format(
        topic=topic,
        n=n,
        last=n - 1,
        min_n=MIN_PHOTOS,
        max_n=min(MAX_PHOTOS, n),
    )
    content.append({"type": "text", "text": prompt})

    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        max_tokens=300,
        messages=[
            {"role": "system", "content": SELECTOR_SYSTEM},
            {"role": "user", "content": content},
        ],
    )

    raw = response.choices[0].message.content.strip()
    raw = raw.replace("```json", "").replace("```", "").strip()
    result = json.loads(raw)

    indices = result.get("selected", [])
    reasoning = result.get("reasoning", "")

    # Map indices back to the *sample* list (which holds full-res Paths)
    indices = [i for i in indices if 0 <= i < n]
    indices = indices[:MAX_PHOTOS]

    if not indices:
        indices = list(range(min(MIN_PHOTOS, n)))

    # Return full-resolution paths — thumbnails were only for AI evaluation
    selected_paths = [str(sample[i]) for i in indices]
    return selected_paths, reasoning
