from __future__ import annotations

import httpx

from app.ocr.base import OCRProvider
from app.parsers.ticket_parser import extract_ticket_ids
from app.utils.logging import get_logger

logger = get_logger(__name__)

IMAGE_MIMETYPES = frozenset({"image/png", "image/jpeg", "image/gif", "image/webp", "image/bmp"})


async def download_slack_file(url: str, bot_token: str, *, timeout: float = 30.0) -> bytes:
    """Download a file from Slack using the bot token for auth."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            url,
            headers={"Authorization": f"Bearer {bot_token}"},
            timeout=timeout,
            follow_redirects=True,
        )
        resp.raise_for_status()
        return resp.content


def is_image_file(file_info: dict) -> bool:
    mimetype = file_info.get("mimetype", "")
    return mimetype in IMAGE_MIMETYPES


async def extract_tickets_from_images(
    files: list[dict],
    bot_token: str,
    ocr_provider: OCRProvider,
) -> set[str]:
    """Download each image file from Slack, run OCR, and extract ticket IDs."""
    all_ids: set[str] = set()

    image_files = [f for f in files if is_image_file(f)]
    if not image_files:
        return all_ids

    logger.info("processing_images", count=len(image_files))

    for file_info in image_files:
        url = file_info.get("url_private", "")
        if not url:
            continue
        try:
            image_data = await download_slack_file(url, bot_token)
            text = await ocr_provider.extract_text(image_data)
            ids = extract_ticket_ids(text)
            if ids:
                logger.info("ocr_tickets_found", file=file_info.get("name", ""), tickets=sorted(ids))
            all_ids.update(ids)
        except Exception:
            logger.exception("image_processing_failed", file=file_info.get("name", ""))

    return all_ids
