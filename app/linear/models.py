from __future__ import annotations

from pydantic import BaseModel, Field


class LinearAssignee(BaseModel):
    name: str = ""
    display_name: str = Field(default="", alias="displayName")

    model_config = {"populate_by_name": True}

    @property
    def label(self) -> str:
        return self.display_name or self.name


class LinearState(BaseModel):
    name: str = "Unknown"


class LinearIssue(BaseModel):
    identifier: str = ""
    title: str
    url: str
    assignee: LinearAssignee | None = None
    state: LinearState | None = None

    model_config = {"populate_by_name": True}
