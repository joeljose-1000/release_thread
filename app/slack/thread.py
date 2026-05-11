from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class MessageInfo:
    text: str
    user_id: str = ""


@dataclass
class ThreadData:
    messages: list[MessageInfo] = field(default_factory=list)
    files: list[dict[str, Any]] = field(default_factory=list)

    @property
    def texts(self) -> list[str]:
        return [m.text for m in self.messages]


async def fetch_thread_messages(
    client: Any,
    channel: str,
    thread_ts: str,
) -> ThreadData:
    """Fetch all messages in a Slack thread, handling pagination."""
    data = ThreadData()
    cursor: str | None = None

    while True:
        kwargs: dict[str, Any] = {
            "channel": channel,
            "ts": thread_ts,
            "limit": 200,
        }
        if cursor:
            kwargs["cursor"] = cursor

        response = await client.conversations_replies(**kwargs)
        messages = response.get("messages", [])

        for msg in messages:
            text = msg.get("text", "")
            if text:
                data.messages.append(MessageInfo(text=text, user_id=msg.get("user", "")))

            msg_files = msg.get("files", [])
            data.files.extend(msg_files)

        if not response.get("has_more", False):
            break
        cursor = response.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            break

    logger.info("thread_fetched", channel=channel, thread_ts=thread_ts, messages=len(data.texts), files=len(data.files))
    return data


async def fetch_recent_messages(
    client: Any,
    channel: str,
    count: int = 20,
) -> ThreadData:
    """Fetch recent channel messages (fallback when /release is used outside a thread)."""
    data = ThreadData()
    response = await client.conversations_history(channel=channel, limit=count)

    for msg in response.get("messages", []):
        text = msg.get("text", "")
        if text:
            data.messages.append(MessageInfo(text=text, user_id=msg.get("user", "")))
        data.files.extend(msg.get("files", []))

    logger.info("recent_messages_fetched", channel=channel, messages=len(data.texts), files=len(data.files))
    return data
