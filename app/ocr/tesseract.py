from __future__ import annotations

import asyncio
import io
from functools import partial

from PIL import Image
import pytesseract

from app.utils.logging import get_logger

logger = get_logger(__name__)


class TesseractProvider:
    """OCR provider backed by Tesseract."""

    async def extract_text(self, image_data: bytes) -> str:
        loop = asyncio.get_running_loop()
        try:
            text: str = await loop.run_in_executor(None, partial(self._sync_extract, image_data))
            return text
        except Exception:
            logger.exception("tesseract_ocr_failed")
            return ""

    @staticmethod
    def _sync_extract(image_data: bytes) -> str:
        image = Image.open(io.BytesIO(image_data))
        return pytesseract.image_to_string(image).strip()
