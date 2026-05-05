from __future__ import annotations

from pydantic import BaseModel


class TicketInfo(BaseModel):
    identifier: str
    title: str
    url: str
    assignee: str | None = None
    assignee_display: str = ""
    state: str | None = None
