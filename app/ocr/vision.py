from __future__ import annotations

import base64

from app.utils.logging import get_logger

logger = get_logger(__name__)


class VisionProvider:
    """OCR provider backed by OpenAI Vision API."""

    def __init__(self, api_key: str, model: str = "gpt-4o") -> None:
        self._api_key = api_key
        self._model = model

    async def extract_text(self, image_data: bytes) -> str:
        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(api_key=self._api_key)
            b64 = base64.b64encode(image_data).decode()
            response = await client.chat.completions.create(
                model=self._model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    "Extract all text from this image. "
                                    "Focus on any ticket identifiers that look like "
                                    "PROJECT-123 (uppercase letters, dash, numbers). "
                                    "Return only the extracted text."
                                ),
                            },
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{b64}"},
                            },
                        ],
                    }
                ],
                max_tokens=1024,
            )
            return (response.choices[0].message.content or "").strip()
        except Exception:
            logger.exception("vision_ocr_failed")
            return ""
