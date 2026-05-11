from __future__ import annotations

from collections import Counter

from app.models.ticket import TicketInfo


def determine_pic(tickets: list[TicketInfo]) -> str:
    """Determine the Person In Charge — the assignee with the most tickets.

    Handles ties (lists all tied names), unassigned tickets, and empty lists.
    """
    if not tickets:
        return "TBD"

    counter: Counter[str] = Counter()
    for ticket in tickets:
        if ticket.assignee:
            counter[ticket.assignee] += 1
        elif ticket.assignee_display:
            counter[ticket.assignee_display] += 1

    if not counter:
        return "TBD"

    max_count = counter.most_common(1)[0][1]
    top_assignees = sorted(name for name, count in counter.items() if count == max_count)

    if len(top_assignees) == 1:
        name = top_assignees[0]
        if name.startswith("<@"):
            return name
        return f"@{name}"
    return ", ".join(
        name if name.startswith("<@") else f"@{name}"
        for name in top_assignees
    )
