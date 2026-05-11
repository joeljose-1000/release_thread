from __future__ import annotations

from datetime import date

from app.models.release import ReleaseSummary
from app.models.ticket import TicketInfo
from app.slack.formatter import format_release_blocks, format_release_summary


class TestFormatReleaseSummary:
    """Tests for the plain-text fallback formatter."""

    def test_basic_format(self, sample_tickets: list[TicketInfo]) -> None:
        summary = ReleaseSummary(
            release_date=date(2025, 5, 4),
            tickets=sample_tickets,
            pic="@raj",
        )
        result = format_release_summary(summary)

        assert "*RELEASE <May 4>*" in result
        assert "*PIC:* @raj" in result
        assert "*Bugs and Improvements:*" in result
        assert "1. <" in result
        assert "*Dev ETA :* TBD" in result
        assert "*Prod ETA :* TBD" in result

    def test_no_tickets(self) -> None:
        summary = ReleaseSummary(release_date=date(2025, 1, 15), tickets=[], pic="TBD")
        result = format_release_summary(summary)
        assert "_No tickets found._" in result

    def test_plain_text_item_no_url(self) -> None:
        summary = ReleaseSummary(
            tickets=[
                TicketInfo(identifier="ENG-1", title="Fix crash", url="https://example.com", assignee="raj"),
                TicketInfo(identifier="", title="fix for admin whitelist", url="", assignee_display="<@U123>"),
            ],
            pic="@raj",
        )
        result = format_release_summary(summary)
        assert "1. <https://example.com|Fix crash> - @raj" in result
        assert "2. fix for admin whitelist - <@U123>" in result


class TestFormatReleaseBlocks:
    """Tests for the Block Kit rich_text formatter."""

    def test_returns_single_rich_text_block(self, sample_tickets: list[TicketInfo]) -> None:
        summary = ReleaseSummary(tickets=sample_tickets, pic="@raj")
        blocks = format_release_blocks(summary)
        assert len(blocks) == 1
        assert blocks[0]["type"] == "rich_text"

    def test_ordered_list_present(self, sample_tickets: list[TicketInfo]) -> None:
        summary = ReleaseSummary(tickets=sample_tickets, pic="@raj")
        blocks = format_release_blocks(summary)
        elements = blocks[0]["elements"]
        list_el = [e for e in elements if e["type"] == "rich_text_list"]
        assert len(list_el) == 1
        assert list_el[0]["style"] == "ordered"
        assert len(list_el[0]["elements"]) == len(sample_tickets)

    def test_ticket_link_in_list(self, sample_tickets: list[TicketInfo]) -> None:
        summary = ReleaseSummary(tickets=sample_tickets, pic="@raj")
        blocks = format_release_blocks(summary)
        list_el = [e for e in blocks[0]["elements"] if e["type"] == "rich_text_list"][0]
        first_item = list_el["elements"][0]
        link = first_item["elements"][0]
        assert link["type"] == "link"
        assert link["url"] == sample_tickets[0].url
        assert link["text"] == sample_tickets[0].title

    def test_plain_item_has_text_not_link(self) -> None:
        summary = ReleaseSummary(
            tickets=[TicketInfo(identifier="", title="fix cache", url="", assignee_display="<@U99>")],
            pic="TBD",
        )
        blocks = format_release_blocks(summary)
        list_el = [e for e in blocks[0]["elements"] if e["type"] == "rich_text_list"][0]
        first_item = list_el["elements"][0]
        assert first_item["elements"][0] == {"type": "text", "text": "fix cache"}

    def test_user_mention_in_assignee(self) -> None:
        summary = ReleaseSummary(
            tickets=[TicketInfo(identifier="A-1", title="t", url="https://x.com", assignee_display="<@UABC>")],
            pic="<@UABC>",
        )
        blocks = format_release_blocks(summary)
        list_el = [e for e in blocks[0]["elements"] if e["type"] == "rich_text_list"][0]
        item_els = list_el["elements"][0]["elements"]
        user_els = [e for e in item_els if e["type"] == "user"]
        assert len(user_els) == 1
        assert user_els[0]["user_id"] == "UABC"

    def test_no_tickets_no_list(self) -> None:
        summary = ReleaseSummary(tickets=[], pic="TBD")
        blocks = format_release_blocks(summary)
        list_el = [e for e in blocks[0]["elements"] if e["type"] == "rich_text_list"]
        assert len(list_el) == 0

    def test_dev_and_prod_eta(self) -> None:
        summary = ReleaseSummary(tickets=[], pic="TBD", dev_eta="14th May 12pm", prod_eta="15th May TBD")
        blocks = format_release_blocks(summary)
        texts = []
        for el in blocks[0]["elements"]:
            if el["type"] == "rich_text_section":
                for sub in el["elements"]:
                    if sub.get("type") == "text":
                        texts.append(sub["text"])
        assert "14th May 12pm" in texts
        assert "15th May TBD" in texts
