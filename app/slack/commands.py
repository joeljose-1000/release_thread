from __future__ import annotations

import asyncio
import re
from typing import Any

from slack_bolt.async_app import AsyncApp

from app.services.release_service import ReleaseService
from app.utils.logging import get_logger

logger = get_logger(__name__)

SLACK_THREAD_LINK_PATTERN = re.compile(
    r"https?://[\w.]*slack\.com/archives/(\w+)/p(\d{10})(\d{6})"
)


def register_commands(bolt_app: AsyncApp, release_service: ReleaseService) -> None:
    """Register slash commands and message shortcuts on the Bolt app."""

    @bolt_app.command("/release")
    async def handle_release(ack: Any, body: dict, client: Any, respond: Any) -> None:
        await ack()

        channel_id: str = body.get("channel_id", "")
        user_id: str = body.get("user_id", "")
        thread_ts: str | None = None

        cmd_text = body.get("text", "").strip()

        link_match = SLACK_THREAD_LINK_PATTERN.search(cmd_text)
        if link_match:
            channel_id = link_match.group(1)
            thread_ts = f"{link_match.group(2)}.{link_match.group(3)}"
        elif cmd_text and _looks_like_ts(cmd_text):
            thread_ts = cmd_text

        if not thread_ts:
            logger.info("release_outside_thread", channel=channel_id, user=user_id)
            await respond(
                ":information_source: No thread detected. "
                "Scanning recent channel messages for tickets.\n"
                "To target a specific thread, either:\n"
                "• Right-click a message in the thread → *Shortcuts* → *Generate Release Summary*\n"
                "• Or paste a thread link: `/release <thread_link>`",
                response_type="ephemeral",
            )

        logger.info(
            "release_command_received",
            channel=channel_id,
            user=user_id,
            thread_ts=thread_ts,
        )

        asyncio.create_task(
            release_service.process_release(client, channel_id, thread_ts, user_id)
        )

    @bolt_app.shortcut("generate_release_summary")
    async def handle_shortcut(ack: Any, shortcut: dict, client: Any) -> None:
        """Message shortcut — triggered from right-click menu on any message."""
        await ack()

        channel_id: str = shortcut.get("channel", {}).get("id", "")
        user_id: str = shortcut.get("user", {}).get("id", "")
        message_ts: str = shortcut.get("message_ts", "") or shortcut.get("message", {}).get("ts", "")
        thread_ts: str = shortcut.get("message", {}).get("thread_ts", "") or message_ts

        if not channel_id or not thread_ts:
            logger.warning("shortcut_missing_context", shortcut_keys=list(shortcut.keys()))
            return

        logger.info(
            "release_shortcut_triggered",
            channel=channel_id,
            user=user_id,
            thread_ts=thread_ts,
        )

        asyncio.create_task(
            release_service.process_release(client, channel_id, thread_ts, user_id)
        )


def _looks_like_ts(text: str) -> bool:
    """Heuristic: Slack timestamps look like '1234567890.123456'."""
    parts = text.split(".")
    return len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit()
