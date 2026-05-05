from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from app.models.ticket import TicketInfo


class ReleaseSummary(BaseModel):
    release_date: date = Field(default_factory=date.today)
    release_date_str: str | None = None
    tickets: list[TicketInfo] = Field(default_factory=list)
    pic: str = "TBD"
    dev_eta: str = "TBD"
    prod_eta: str = "TBD"
