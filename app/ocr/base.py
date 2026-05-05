from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class OCRProvider(Protocol):
    """Abstract interface for OCR providers."""

    async def extract_text(self, image_data: bytes) -> str:
        """Extract text content from raw image bytes."""
        ...
