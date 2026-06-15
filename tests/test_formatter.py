from __future__ import annotations

from datetime import date

from app.models.release import ReleaseSummary
from app.models.ticket import DEFAULT_CATEGORY, TicketInfo
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

        assert "*RELEASE <4th May - Sunday>*" in result
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


class TestCategoryGrouping:
    """Tests for category-aware formatting."""

    def test_single_category_block_text(self) -> None:
        summary = ReleaseSummary(
            tickets=[
                TicketInfo(identifier="ENG-1", title="Fix crash", url="https://x.com", category="Features"),
                TicketInfo(identifier="ENG-2", title="Add logs", url="https://y.com"),
            ],
            pic="TBD",
        )
        result = format_release_summary(summary)
        assert "*Features:*" in result
        assert "*Bugs and Improvements:*" in result
        assert result.index("*Features:*") < result.index("*Bugs and Improvements:*")

    def test_per_category_numbering_plain_text(self) -> None:
        summary = ReleaseSummary(
            tickets=[
                TicketInfo(identifier="ENG-1", title="Deploy", url="", category="Features"),
                TicketInfo(identifier="ENG-2", title="Fix A", url=""),
                TicketInfo(identifier="ENG-3", title="Fix B", url=""),
            ],
            pic="TBD",
        )
        result = format_release_summary(summary)
        lines = result.split("\n")
        feature_items = []
        bugs_items = []
        current = None
        for line in lines:
            if "*Features:*" in line:
                current = "feature"
            elif "*Bugs and Improvements:*" in line:
                current = "bugs"
            elif current and line and line[0].isdigit():
                (feature_items if current == "feature" else bugs_items).append(line)
        assert len(feature_items) == 1
        assert feature_items[0].startswith("1.")
        assert len(bugs_items) == 2
        assert bugs_items[0].startswith("1.")
        assert bugs_items[1].startswith("2.")

    def test_default_category_appears_last_in_blocks(self) -> None:
        summary = ReleaseSummary(
            tickets=[
                TicketInfo(identifier="ENG-1", title="Bug fix", url=""),
                TicketInfo(identifier="ENG-2", title="New API", url="", category="Features"),
            ],
            pic="TBD",
        )
        blocks = format_release_blocks(summary)
        elements = blocks[0]["elements"]
        section_texts = []
        for el in elements:
            if el["type"] == "rich_text_section":
                for sub in el["elements"]:
                    if sub.get("type") == "text":
                        section_texts.append(sub["text"])
        assert "Features:" in section_texts
        assert "Bugs and Improvements:" in section_texts
        assert section_texts.index("Features:") < section_texts.index("Bugs and Improvements:")

    def test_each_category_list_starts_at_one(self) -> None:
        summary = ReleaseSummary(
            tickets=[
                TicketInfo(identifier="ENG-1", title="New API", url="", category="Features"),
                TicketInfo(identifier="ENG-2", title="Bug fix", url=""),
                TicketInfo(identifier="ENG-3", title="Another bug", url=""),
            ],
            pic="TBD",
        )
        blocks = format_release_blocks(summary)
        lists = [e for e in blocks[0]["elements"] if e["type"] == "rich_text_list"]
        assert len(lists) == 2
        assert "offset" not in lists[0]
        assert "offset" not in lists[1]

    def test_hotfix_header_plain_text(self) -> None:
        summary = ReleaseSummary(tickets=[], pic="TBD", is_hotfix=True)
        result = format_release_summary(summary)
        assert "*HOTFIX <" in result
        assert "RELEASE" not in result

    def test_hotfix_uses_items_heading(self) -> None:
        summary = ReleaseSummary(
            tickets=[
                TicketInfo(identifier="ENG-1", title="Fix crash", url=""),
                TicketInfo(identifier="ENG-2", title="New API", url="", category="Features"),
            ],
            pic="TBD",
            is_hotfix=True,
        )
        result = format_release_summary(summary)
        assert "*Items:*" in result
        assert "*Features:*" not in result
        assert "*Bugs and Improvements:*" not in result

    def test_hotfix_single_list_blocks(self) -> None:
        summary = ReleaseSummary(
            tickets=[
                TicketInfo(identifier="ENG-1", title="Fix crash", url=""),
                TicketInfo(identifier="ENG-2", title="New API", url="", category="Features"),
            ],
            pic="TBD",
            is_hotfix=True,
        )
        blocks = format_release_blocks(summary)
        lists = [e for e in blocks[0]["elements"] if e["type"] == "rich_text_list"]
        assert len(lists) == 1
        assert len(lists[0]["elements"]) == 2

    def test_hotfix_empty_shows_items_heading(self) -> None:
        summary = ReleaseSummary(tickets=[], pic="TBD", is_hotfix=True)
        result = format_release_summary(summary)
        assert "*Items:*" in result
        assert "*Bugs and Improvements:*" not in result

    def test_hotfix_header_blocks(self) -> None:
        summary = ReleaseSummary(tickets=[], pic="TBD", is_hotfix=True)
        blocks = format_release_blocks(summary)
        header_text = blocks[0]["elements"][0]["elements"][1]["text"]
        assert "HOTFIX" in header_text
        assert "RELEASE" not in header_text

    def test_release_header_by_default(self) -> None:
        summary = ReleaseSummary(tickets=[], pic="TBD")
        result = format_release_summary(summary)
        assert "*RELEASE <" in result

    def test_all_same_category_no_extra_headers(self) -> None:
        summary = ReleaseSummary(
            tickets=[
                TicketInfo(identifier="ENG-1", title="Fix A", url=""),
                TicketInfo(identifier="ENG-2", title="Fix B", url=""),
            ],
            pic="TBD",
        )
        result = format_release_summary(summary)
        assert result.count("*Bugs and Improvements:*") == 1
        assert "*Features:*" not in result
