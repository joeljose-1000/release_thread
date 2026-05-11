from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta


IDENTIFIER_PATTERN = re.compile(r"\b([A-Z]{2,10}-\d+)\b")

LINEAR_URL_PATTERN = re.compile(
    r"https?://linear\.app/[\w-]+/issue/([A-Z]{2,10}-\d+)",
)

PLAIN_ITEM_PATTERN = re.compile(
    r"^(?:\d+[.)]\s*|[-*•]\s+)(.+)$",
    re.MULTILINE,
)

STATUS_FILTER_PATTERN = re.compile(
    r"\b(?:all\s+(?:items?|tickets?|issues?)\s+(?:in|with)\s+(\w+)(?:\s+status)?)\b",
    re.IGNORECASE,
)

DEV_ETA_PATTERN = re.compile(r"dev\s+eta\b.{0,60}", re.IGNORECASE)
PROD_ETA_PATTERN = re.compile(r"prod(?:uction)?\s+eta\b.{0,60}", re.IGNORECASE)

RELEASE_DATE_PATTERNS = [
    re.compile(r"release\s+(?:items?\s+)?(?:for|on)\s+(\w+)", re.IGNORECASE),
    re.compile(r"(?:for|on)\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)", re.IGNORECASE),
]

DAY_NAMES = {
    "monday": 0, "mon": 0,
    "tuesday": 1, "tue": 1, "tues": 1,
    "wednesday": 2, "wed": 2,
    "thursday": 3, "thu": 3, "thurs": 3,
    "friday": 4, "fri": 4,
    "saturday": 5, "sat": 5,
    "sunday": 6, "sun": 6,
}

DAY_LABELS = {0: "Monday", 1: "Tuesday", 2: "Wednesday", 3: "Thursday", 4: "Friday", 5: "Saturday", 6: "Sunday"}

ORDINAL_SUFFIXES = {1: "st", 2: "nd", 3: "rd", 21: "st", 22: "nd", 23: "rd", 31: "st"}


@dataclass
class PlainItem:
    """A release item described in plain text (no Linear ticket)."""
    title: str
    user_id: str = ""


@dataclass
class ParseResult:
    ticket_ids: set[str] = field(default_factory=set)
    plain_items: list[PlainItem] = field(default_factory=list)
    status_filter: str | None = None
    release_date: str | None = None
    dev_eta: str | None = None
    prod_eta: str | None = None


def _ordinal(day: int) -> str:
    """Return day with ordinal suffix: 1st, 2nd, 3rd, 4th, etc."""
    suffix = ORDINAL_SUFFIXES.get(day, "th")
    return f"{day}{suffix}"


def _format_date(d: date) -> str:
    """Format a date as '7th May - Thursday'."""
    day_name = DAY_LABELS[d.weekday()]
    return f"{_ordinal(d.day)} {d.strftime('%B')} - {day_name}"


def _format_date_short(d: date) -> str:
    """Format a date as '7th May'."""
    return f"{_ordinal(d.day)} {d.strftime('%B')}"


def extract_ticket_ids(text: str) -> set[str]:
    """Extract Linear ticket identifiers from plain text and URLs."""
    ids: set[str] = set()
    ids.update(IDENTIFIER_PATTERN.findall(text))
    ids.update(LINEAR_URL_PATTERN.findall(text))
    return ids


def detect_status_filter(text: str) -> str | None:
    match = STATUS_FILTER_PATTERN.search(text)
    return match.group(1).capitalize() if match else None


def extract_plain_items(text: str) -> list[str]:
    """Extract numbered/bulleted line items that don't reference a Linear ticket."""
    items: list[str] = []
    for match in PLAIN_ITEM_PATTERN.finditer(text):
        line = match.group(1).strip()
        if not line:
            continue
        if IDENTIFIER_PATTERN.search(line) or LINEAR_URL_PATTERN.search(line):
            continue
        items.append(line)
    return items


def _resolve_day_to_date(day_str: str) -> date | None:
    """Convert a day name to the next occurrence of that date."""
    lower = day_str.strip().lower()
    target_weekday = DAY_NAMES.get(lower)
    if target_weekday is None:
        return None
    today = date.today()
    days_ahead = (target_weekday - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return today + timedelta(days=days_ahead)


TIME_PATTERN = re.compile(r"\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM)")

DAY_NAME_TOKEN = re.compile(
    r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday"
    r"|mon|tue|tues|wed|thu|thurs|fri|sat|sun)\b",
    re.IGNORECASE,
)


def _extract_day_and_time(text: str) -> str | None:
    """Pull the day name and optional time from free-form text.

    Works regardless of surrounding phrasing like "would be", "is on",
    "set to", "around", etc.
    """
    day_match = DAY_NAME_TOKEN.search(text)
    if not day_match:
        return None

    resolved = _resolve_day_to_date(day_match.group(1))
    if not resolved:
        return None

    date_part = _format_date_short(resolved)

    time_match = TIME_PATTERN.search(text)
    if time_match:
        return f"{date_part} {time_match.group(0).strip()}"

    return date_part


def extract_release_metadata(first_message: str) -> dict[str, str | date | None]:
    """Extract release date, dev ETA, and prod ETA from the thread's opening message."""
    result: dict[str, str | date | None] = {
        "release_date": None,
        "release_date_obj": None,
        "dev_eta": None,
        "prod_eta": None,
    }

    release_date_obj: date | None = None
    for pattern in RELEASE_DATE_PATTERNS:
        m = pattern.search(first_message)
        if m:
            release_date_obj = _resolve_day_to_date(m.group(1))
            if release_date_obj:
                result["release_date"] = _format_date(release_date_obj)
                result["release_date_obj"] = release_date_obj
            break

    dev_match = DEV_ETA_PATTERN.search(first_message)
    if dev_match:
        result["dev_eta"] = _extract_day_and_time(dev_match.group(0))

    prod_match = PROD_ETA_PATTERN.search(first_message)
    if prod_match:
        result["prod_eta"] = _extract_day_and_time(prod_match.group(0))

    if not result["prod_eta"] and release_date_obj:
        result["prod_eta"] = f"{_format_date_short(release_date_obj)} TBD"

    return result


def extract_from_messages(
    messages: list[str],
    user_ids: list[str] | None = None,
) -> ParseResult:
    """Extract ticket identifiers, plain text items, status filter, and release metadata."""
    result = ParseResult()

    if messages:
        metadata = extract_release_metadata(messages[0])
        result.release_date = metadata.get("release_date")  # type: ignore[assignment]
        result.dev_eta = metadata.get("dev_eta")  # type: ignore[assignment]
        result.prod_eta = metadata.get("prod_eta")  # type: ignore[assignment]

    for idx, msg in enumerate(messages):
        result.ticket_ids.update(extract_ticket_ids(msg))
        if result.status_filter is None:
            result.status_filter = detect_status_filter(msg)

        sender = (user_ids[idx] if user_ids and idx < len(user_ids) else "")
        for item_text in extract_plain_items(msg):
            result.plain_items.append(PlainItem(title=item_text, user_id=sender))

    return result
