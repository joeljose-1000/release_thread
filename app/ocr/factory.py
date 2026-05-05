from __future__ import annotations

from app.ocr.base import OCRProvider
from app.ocr.easyocr_provider import EasyOCRProvider
from app.ocr.tesseract import TesseractProvider
from app.ocr.vision import VisionProvider


def create_ocr_provider(
    provider_name: str,
    openai_api_key: str = "",
) -> OCRProvider:
    """Factory that returns the configured OCR provider instance."""
    name = provider_name.lower().strip()
    if name == "tesseract":
        return TesseractProvider()
    if name == "easyocr":
        return EasyOCRProvider()
    if name == "vision":
        if not openai_api_key:
            raise ValueError("OPENAI_API_KEY is required for the Vision OCR provider")
        return VisionProvider(api_key=openai_api_key)
    raise ValueError(f"Unknown OCR provider: {provider_name!r}. Use: easyocr, tesseract, vision")
