from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.release import ReleaseSummary
from app.models.ticket import TicketInfo
from app.services.release_state import ReleaseState, ReleaseStateStore


class TestReleaseStateStore:
    def test_put_and_get(self) -> None:
        store = ReleaseStateStore()
        state = _make_state("C1", "ts1")
        store.put(state)
        assert store.get("C1", "ts1") is state

    def test_get_missing(self) -> None:
        store = ReleaseStateStore()
        assert store.get("C1", "ts_missing") is None

    def test_has(self) -> None:
        store = ReleaseStateStore()
        store.put(_make_state("C1", "ts1"))
        assert store.has("C1", "ts1")
        assert not store.has("C1", "ts_other")

    def test_remove(self) -> None:
        store = ReleaseStateStore()
        store.put(_make_state("C1", "ts1"))
        store.remove("C1", "ts1")
        assert not store.has("C1", "ts1")

    def test_remove_missing_is_noop(self) -> None:
        store = ReleaseStateStore()
        store.remove("C1", "ts_missing")

    def test_overwrite(self) -> None:
        store = ReleaseStateStore()
        s1 = _make_state("C1", "ts1", message_ts="msg1")
        s2 = _make_state("C1", "ts1", message_ts="msg2")
        store.put(s1)
        store.put(s2)
        assert store.get("C1", "ts1") is s2


def _make_state(
    channel: str = "C1",
    thread_ts: str = "ts1",
    message_ts: str = "msg_ts",
) -> ReleaseState:
    return ReleaseState(
        channel=channel,
        thread_ts=thread_ts,
        message_ts=message_ts,
        tickets=[],
        summary=ReleaseSummary(),
        name_map={},
    )
