from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from app.models.release import ReleaseSummary
from app.models.ticket import TicketInfo


@dataclass
class ReleaseState:
    """Tracks a live release summary that the bot is monitoring for updates."""

    channel: str
    thread_ts: str
    message_ts: str
    tickets: list[TicketInfo]
    summary: ReleaseSummary
    name_map: dict[str, str]
    ticket_ids: set[str] = field(default_factory=set)
    plain_titles: set[str] = field(default_factory=set)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)


class ReleaseStateStore:
    """In-memory store mapping (channel, thread_ts) → ReleaseState."""

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], ReleaseState] = {}

    def get(self, channel: str, thread_ts: str) -> ReleaseState | None:
        return self._store.get((channel, thread_ts))

    def put(self, state: ReleaseState) -> None:
        self._store[(state.channel, state.thread_ts)] = state

    def remove(self, channel: str, thread_ts: str) -> None:
        self._store.pop((channel, thread_ts), None)

    def has(self, channel: str, thread_ts: str) -> bool:
        return (channel, thread_ts) in self._store
