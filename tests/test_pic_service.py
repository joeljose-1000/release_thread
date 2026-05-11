from __future__ import annotations

from app.models.ticket import TicketInfo
from app.services.pic_service import determine_pic


class TestDeterminePic:
    def test_single_top_assignee(self, sample_tickets: list[TicketInfo]) -> None:
        # raj has 2 tickets, john has 1
        result = determine_pic(sample_tickets)
        assert result == "@raj"

    def test_tie_lists_alphabetically(self) -> None:
        tickets = [
            TicketInfo(identifier="A-1", title="t", url="u", assignee="zara"),
            TicketInfo(identifier="A-2", title="t", url="u", assignee="alice"),
        ]
        result = determine_pic(tickets)
        assert result == "@alice, @zara"

    def test_all_unassigned(self, unassigned_tickets: list[TicketInfo]) -> None:
        result = determine_pic(unassigned_tickets)
        assert result == "TBD"

    def test_empty_list(self) -> None:
        result = determine_pic([])
        assert result == "TBD"

    def test_mixed_assigned_and_unassigned(self) -> None:
        tickets = [
            TicketInfo(identifier="A-1", title="t", url="u", assignee="bob"),
            TicketInfo(identifier="A-2", title="t", url="u", assignee=None),
            TicketInfo(identifier="A-3", title="t", url="u", assignee="bob"),
        ]
        result = determine_pic(tickets)
        assert result == "@bob"

    def test_plain_items_counted_by_assignee_display(self) -> None:
        tickets = [
            TicketInfo(identifier="A-1", title="t", url="u", assignee="bob"),
            TicketInfo(identifier="", title="fix cache", url="", assignee_display="<@U999>"),
            TicketInfo(identifier="", title="fix logs", url="", assignee_display="<@U999>"),
        ]
        result = determine_pic(tickets)
        assert result == "<@U999>"
