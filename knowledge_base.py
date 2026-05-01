"""
Changer Club AI Content Factory — knowledge base.

Loads event transcriptions from disk and provides relevant context
for slide text generation.
"""

import logging
import re
from pathlib import Path
from typing import Dict, List

from config import KNOWLEDGE_CONTEXT_CHARS

logger = logging.getLogger(__name__)


class KnowledgeBase:
    """Index of plain-text transcription files used as context for Claude."""

    def __init__(self, transcriptions_dir: str) -> None:
        self.dir = Path(transcriptions_dir)
        self.documents: Dict[str, str] = {}
        self._load()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if not self.dir.exists():
            logger.warning("Transcriptions directory not found: %s", self.dir)
            return
        for path in self.dir.glob("*.txt"):
            text = path.read_text(encoding="utf-8", errors="ignore").strip()
            if text:
                self.documents[path.stem] = text
        logger.info("Loaded %d transcription(s)", len(self.documents))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_context(self, topic: str, max_chars: int | None = None) -> str:
        """Return the most relevant transcription passages for *topic*.

        Relevance is scored by keyword overlap — simple but effective for
        a small corpus of event transcriptions.
        """
        max_chars = max_chars or KNOWLEDGE_CONTEXT_CHARS

        if not self.documents:
            return "No transcription context available."

        topic_words = set(re.findall(r"\w+", topic.lower()))
        scored: list[tuple[int, str, str]] = []

        for name, text in self.documents.items():
            text_lower = text.lower()
            score = sum(1 for w in topic_words if w in text_lower)
            scored.append((score, name, text))

        scored.sort(reverse=True)

        context_parts: list[str] = []
        total = 0
        for _score, name, text in scored:
            if total >= max_chars:
                break
            chunk = text[: max_chars - total]
            context_parts.append(f"[From: {name}]\n{chunk}")
            total += len(chunk)

        if not context_parts:
            first_name, first_text = next(iter(self.documents.items()))
            context_parts.append(f"[From: {first_name}]\n{first_text[:max_chars]}")

        return "\n\n---\n\n".join(context_parts)

    def list_files(self) -> List[str]:
        """Return stem names of all loaded transcription files."""
        return list(self.documents.keys())
