from __future__ import annotations

import re
from typing import Any

from datetime import date

from app.models.release import ReleaseSummary
from app.models.ticket import DEFAULT_CATEGORY, TicketInfo

_DAY_LABELS = {0: "Monday", 1: "Tuesday", 2: "Wednesday", 3: "Thursday", 4: "Friday", 5: "Saturday", 6: "Sunday"}
_ORDINAL_SUFFIXES = {1: "st", 2: "nd", 3: "rd", 21: "st", 22: "nd", 23: "rd", 31: "st"}


def _format_fallback_date(d: date) -> str:
    """Format a date as '25th May - Monday'."""
    suffix = _ORDINAL_SUFFIXES.get(d.day, "th")
    day_name = _DAY_LABELS[d.weekday()]
    return f"{d.day}{suffix} {d.strftime('%B')} - {day_name}"

_USER_MENTION_RE = re.compile(r"<@(U\w+)>")


def _group_by_category(tickets: list[TicketInfo]) -> list[tuple[str, list[TicketInfo]]]:
    """Group tickets by category, keeping DEFAULT_CATEGORY last."""
    groups: dict[str, list[TicketInfo]] = {}
    for ticket in tickets:
        groups.setdefault(ticket.category, []).append(ticket)
    result = [(k, v) for k, v in groups.items() if k != DEFAULT_CATEGORY]
    if DEFAULT_CATEGORY in groups:
        result.append((DEFAULT_CATEGORY, groups[DEFAULT_CATEGORY]))
    return result


def _mention_elements(text: str) -> list[dict[str, Any]]:
    """Convert a string that may contain <@U123> mentions into rich_text elements."""
    elements: list[dict[str, Any]] = []
    last = 0
    for m in _USER_MENTION_RE.finditer(text):
        if m.start() > last:
            elements.append({"type": "text", "text": text[last:m.start()]})
        elements.append({"type": "user", "user_id": m.group(1)})
        last = m.end()
    if last < len(text):
        elements.append({"type": "text", "text": text[last:]})
    if not elements:
        elements.append({"type": "text", "text": text})
    return elements


def format_release_blocks(summary: ReleaseSummary) -> list[dict[str, Any]]:
    """Build Slack Block Kit rich_text blocks with a native ordered list."""
    date_str = summary.release_date_str or _format_fallback_date(summary.release_date)

    parts: list[dict[str, Any]] = []

    parts.append({
        "type": "rich_text_section",
        "elements": [
            {"type": "emoji", "name": "round_pushpin"},
            {"type": "text", "text": f" {'HOTFIX' if summary.is_hotfix else 'RELEASE'} <{date_str}>", "style": {"bold": True}},
        ],
    })

    pic_els: list[dict[str, Any]] = [{"type": "text", "text": "PIC: ", "style": {"bold": True}}]
    pic_els.extend(_mention_elements(summary.pic))
    parts.append({"type": "rich_text_section", "elements": pic_els})

    if not summary.tickets:
        parts.append({
            "type": "rich_text_section",
            "elements": [{"type": "text", "text": "Bugs and Improvements:", "style": {"bold": True}}],
        })
        parts.append({
            "type": "rich_text_section",
            "elements": [{"type": "text", "text": "No tickets found.", "style": {"italic": True}}],
        })
    else:
        for category, cat_tickets in _group_by_category(summary.tickets):
            parts.append({
                "type": "rich_text_section",
                "elements": [{"type": "text", "text": f"{category}:", "style": {"bold": True}}],
            })

            list_items: list[dict[str, Any]] = []
            for ticket in cat_tickets:
                els: list[dict[str, Any]] = []
                if ticket.url:
                    els.append({"type": "link", "url": ticket.url, "text": ticket.title})
                else:
                    els.append({"type": "text", "text": ticket.title})

                assignee = ticket.assignee_display or (f"@{ticket.assignee}" if ticket.assignee else "")
                if assignee:
                    els.append({"type": "text", "text": " - "})
                    els.extend(_mention_elements(assignee))

                list_items.append({"type": "rich_text_section", "elements": els})

            parts.append({
                "type": "rich_text_list",
                "style": "ordered",
                "elements": list_items,
            })

    parts.append({
        "type": "rich_text_section",
        "elements": [
            {"type": "text", "text": "Dev ETA : ", "style": {"bold": True}},
            {"type": "text", "text": summary.dev_eta},
        ],
    })
    parts.append({
        "type": "rich_text_section",
        "elements": [
            {"type": "text", "text": "Prod ETA : ", "style": {"bold": True}},
            {"type": "text", "text": summary.prod_eta},
        ],
    })

    return [{"type": "rich_text", "elements": parts}]


def format_release_summary(summary: ReleaseSummary) -> str:
    """Build a plain-text fallback for the release summary."""
    date_str = summary.release_date_str or _format_fallback_date(summary.release_date)

    label = "HOTFIX" if summary.is_hotfix else "RELEASE"
    lines: list[str] = [
        f":round_pushpin: *{label} <{date_str}>*",
        f"*PIC:* {summary.pic}",
    ]

    if not summary.tickets:
        lines.append("*Bugs and Improvements:*")
        lines.append("_No tickets found._")
    else:
        for category, cat_tickets in _group_by_category(summary.tickets):
            lines.append(f"*{category}:*")
            for idx, ticket in enumerate(cat_tickets, start=1):
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
