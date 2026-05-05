from __future__ import annotations

import asyncio
from functools import partial
from typing import Any

from app.utils.logging import get_logger

logger = get_logger(__name__)

_reader: Any = None


def _get_reader() -> Any:
    global _reader
    if _reader is None:
        import easyocr

        _reader = easyocr.Reader(["en"], gpu=False)
    return _reader


class EasyOCRProvider:
    """OCR provider backed by EasyOCR."""

    async def extract_text(self, image_data: bytes) -> str:
        loop = asyncio.get_running_loop()
        try:
            text: str = await loop.run_in_executor(None, partial(self._sync_extract, image_data))
            return text
        except Exception:
            logger.exception("easyocr_ocr_failed")
            return ""

    @staticmethod
    def _sync_extract(image_data: bytes) -> str:
        reader = _get_reader()
        results = reader.readtext(image_data, detail=0)
        return " ".join(results).strip()
