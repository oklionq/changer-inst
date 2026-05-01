"""
Calls OpenAI API with photos + topic + knowledge base context.
Uses gpt-4o (vision) to analyze photos and generate slide texts.
"""

import asyncio
import base64
import json
import os
from pathlib import Path

from openai import OpenAI
from prompts import SYSTEM_PROMPT, SLIDE_GENERATION_TEMPLATE
from knowledge_base import KnowledgeBase
from config import OPENAI_API_KEY, OPENAI_MODEL, TRANSCRIPTIONS_DIR

client = OpenAI(api_key=OPENAI_API_KEY)
kb = KnowledgeBase(TRANSCRIPTIONS_DIR)


def _image_to_base64(path: str) -> tuple[str, str]:
    path = Path(path)
    ext = path.suffix.lower()
    media_types = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }
    media_type = media_types.get(ext, "image/jpeg")
    data = base64.standard_b64encode(path.read_bytes()).decode("utf-8")
    return data, media_type


def _describe_slide_positions(n: int) -> str:
    if n == 1:
        return "1 (hook + insight + consequence all in one)"
    parts = ["1 (hook)"]
    for i in range(2, n):
        parts.append(f"{i} (insight/proof)")
    parts.append(f"{n} (consequence/action)")
    return ", ".join(parts)


def _sync_generate(photo_paths: list, topic: str) -> list:
    n = len(photo_paths)
    context = kb.get_context(topic)

    # Build message content — OpenAI vision format
    content = []

    for i, path in enumerate(photo_paths):
        b64, media_type = _image_to_base64(path)
        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:{media_type};base64,{b64}",
                "detail": "high",
            },
        })
        content.append({
            "type": "text",
            "text": f"[Photo {i + 1} of {n}]",
        })

    prompt = SLIDE_GENERATION_TEMPLATE.format(
        context=context,
        topic=topic,
        n_slides=n,
        slide_descriptions=_describe_slide_positions(n),
    )
    content.append({"type": "text", "text": prompt})

    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        max_tokens=3000,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
    )

    raw = response.choices[0].message.content.strip()
    raw = raw.replace("```json", "").replace("```", "").strip()
    return json.loads(raw)


async def generate_slide_texts(photo_paths: list, topic: str) -> list:
    return await asyncio.to_thread(_sync_generate, photo_paths, topic)
