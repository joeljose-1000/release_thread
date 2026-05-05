from __future__ import annotations

import pytest

from app.models.ticket import TicketInfo


@pytest.fixture
def sample_tickets() -> list[TicketInfo]:
    return [
        TicketInfo(
            identifier="ENG-101",
            title="Fix onboarding crash",
            url="https://linear.app/company/issue/ENG-101/fix-onboarding-crash",
            assignee="raj",
        ),
        TicketInfo(
            identifier="ENG-222",
            title="Improve retry handling",
            url="https://linear.app/company/issue/ENG-222/improve-retry-handling",
            assignee="john",
        ),
        TicketInfo(
            identifier="ENG-333",
            title="Add dark mode",
            url="https://linear.app/company/issue/ENG-333/add-dark-mode",
            assignee="raj",
        ),
    ]


@pytest.fixture
def unassigned_tickets() -> list[TicketInfo]:
    return [
        TicketInfo(
            identifier="ENG-400",
            title="Unassigned bug",
            url="https://linear.app/company/issue/ENG-400/unassigned-bug",
            assignee=None,
        ),
        TicketInfo(
            identifier="ENG-401",
            title="Another unassigned",
            url="https://linear.app/company/issue/ENG-401/another-unassigned",
            assignee=None,
        ),
    ]
