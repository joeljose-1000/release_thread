from __future__ import annotations

from app.models.release import ReleaseSummary


def format_release_summary(summary: ReleaseSummary) -> str:
    """Build a Slack mrkdwn formatted release summary."""
    date_str = summary.release_date_str or summary.release_date.strftime("%B %-d")

    lines: list[str] = [
        f":round_pushpin: *RELEASE &lt;{date_str}&gt;*",
        f"*PIC:* {summary.pic}",
        "*Bugs and Improvements:*",
    ]

    if not summary.tickets:
        lines.append("_No tickets found._")
    else:
        for idx, ticket in enumerate(summary.tickets, start=1):
            assignee_part = ""
            if ticket.assignee_display:
                assignee_part = f" - {ticket.assignee_display}"
            elif ticket.assignee:
                assignee_part = f" - @{ticket.assignee}"
            if ticket.url:
                lines.append(f"{idx}. <{ticket.url}|{ticket.title}>{assignee_part}")
            else:
                lines.append(f"{idx}. {ticket.title}{assignee_part}")

    lines.extend([
        f"*Dev ETA :* {summary.dev_eta}",
        f"*Prod ETA :* {summary.prod_eta}",
    ])

    return "\n".join(lines)
