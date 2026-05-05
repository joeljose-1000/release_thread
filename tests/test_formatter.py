from __future__ import annotations

from datetime import date

from app.models.release import ReleaseSummary
from app.models.ticket import TicketInfo
from app.slack.formatter import format_release_summary


class TestFormatReleaseSummary:
    def test_basic_format(self, sample_tickets: list[TicketInfo]) -> None:
        summary = ReleaseSummary(
            release_date=date(2025, 5, 4),
            tickets=sample_tickets,
            pic="@raj",
        )
        result = format_release_summary(summary)

        assert ":round_pushpin: *RELEASE May 4*" in result
        assert "*PIC:* @raj" in result
        assert "*Bugs and Improvements:*" in result
        assert (
            "1. <https://linear.app/company/issue/ENG-101/fix-onboarding-crash|Fix onboarding crash> - @raj"
            in result
        )
        assert (
            "2. <https://linear.app/company/issue/ENG-222/improve-retry-handling|Improve retry handling> - @john"
            in result
        )
        assert "*Dev ETA :* TBD" in result
        assert "*Prod ETA :* TBD" in result

    def test_no_tickets(self) -> None:
        summary = ReleaseSummary(
            release_date=date(2025, 1, 15),
            tickets=[],
            pic="TBD",
        )
        result = format_release_summary(summary)
        assert "_No tickets found._" in result

    def test_unassigned_ticket_no_at_symbol(self) -> None:
        summary = ReleaseSummary(
            tickets=[
                TicketInfo(identifier="X-1", title="Bug", url="https://example.com", assignee=None),
            ],
            pic="TBD",
        )
        result = format_release_summary(summary)
        line = [l for l in result.split("\n") if l.startswith("1.")][0]
        assert line.endswith("|Bug>")

    def test_hyperlink_format(self, sample_tickets: list[TicketInfo]) -> None:
        summary = ReleaseSummary(tickets=sample_tickets, pic="@raj")
        result = format_release_summary(summary)
        # Raw URLs should NOT appear outside Slack hyperlink syntax
        for ticket in sample_tickets:
            assert f"<{ticket.url}|{ticket.title}>" in result

    def test_numbering_is_sequential(self, sample_tickets: list[TicketInfo]) -> None:
        summary = ReleaseSummary(tickets=sample_tickets, pic="@raj")
        result = format_release_summary(summary)
        assert "1. <" in result
        assert "2. <" in result
        assert "3. <" in result
