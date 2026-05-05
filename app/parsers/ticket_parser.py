from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta


IDENTIFIER_PATTERN = re.compile(r"\b([A-Z]{2,10}-\d+)\b")

LINEAR_URL_PATTERN = re.compile(
    r"https?://linear\.app/[\w-]+/issue/([A-Z]{2,10}-\d+)",
)

STATUS_FILTER_PATTERN = re.compile(
    r"\b(?:all\s+(?:items?|tickets?|issues?)\s+(?:in|with)\s+(\w+)(?:\s+status)?)\b",
    re.IGNORECASE,
)

DEV_ETA_PATTERN = re.compile(
    r"dev\s+eta[:\s]+(.+?)(?:\.|$)",
    re.IGNORECASE,
)

PROD_ETA_PATTERN = re.compile(
    r"prod(?:uction)?\s+eta[:\s]+(.+?)(?:\.|$)",
    re.IGNORECASE,
)

RELEASE_DATE_PATTERNS = [
    re.compile(r"release\s+(?:items?\s+)?(?:for|on)\s+(\w+(?:\s+\d{1,2}(?:\s*(?:am|pm))?)?)", re.IGNORECASE),
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


@dataclass
class ParseResult:
    ticket_ids: set[str] = field(default_factory=set)
    status_filter: str | None = None
    release_date: str | None = None
    dev_eta: str | None = None
    prod_eta: str | None = None


def extract_ticket_ids(text: str) -> set[str]:
    """Extract Linear ticket identifiers from plain text and URLs."""
    ids: set[str] = set()
    ids.update(IDENTIFIER_PATTERN.findall(text))
    ids.update(LINEAR_URL_PATTERN.findall(text))
    return ids


def detect_status_filter(text: str) -> str | None:
    match = STATUS_FILTER_PATTERN.search(text)
    return match.group(1).capitalize() if match else None


def _resolve_day_name(day_str: str) -> str:
    """Convert a day name like 'Thursday' to an actual date string like 'May 8'."""
    lower = day_str.strip().lower()
    target_weekday = DAY_NAMES.get(lower)
    if target_weekday is None:
        return day_str.strip()

    today = date.today()
    days_ahead = (target_weekday - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    target_date = today + timedelta(days=days_ahead)
    return target_date.strftime("%B %-d")


def _parse_eta(text: str) -> str:
    """Clean up an ETA string, resolving day names to dates."""
    cleaned = text.strip().rstrip(".")
    words = cleaned.split()
    if words:
        first = words[0].lower().rstrip(",")
        if first in DAY_NAMES:
            date_part = _resolve_day_name(first)
            rest = " ".join(words[1:]).strip()
            return f"{date_part} {rest}".strip() if rest else date_part
    return cleaned


def extract_release_metadata(first_message: str) -> dict[str, str | None]:
    """Extract release date, dev ETA, and prod ETA from the thread's opening message."""
    result: dict[str, str | None] = {
        "release_date": None,
        "dev_eta": None,
        "prod_eta": None,
    }

    dev_match = DEV_ETA_PATTERN.search(first_message)
    if dev_match:
        result["dev_eta"] = _parse_eta(dev_match.group(1))

    prod_match = PROD_ETA_PATTERN.search(first_message)
    if prod_match:
        result["prod_eta"] = _parse_eta(prod_match.group(1))

    for pattern in RELEASE_DATE_PATTERNS:
        m = pattern.search(first_message)
        if m:
            result["release_date"] = _resolve_day_name(m.group(1))
            break

    return result


def extract_from_messages(messages: list[str]) -> ParseResult:
    """Extract ticket identifiers, status filter, and release metadata from messages."""
    result = ParseResult()

    if messages:
        metadata = extract_release_metadata(messages[0])
        result.release_date = metadata["release_date"]
        result.dev_eta = metadata["dev_eta"]
        result.prod_eta = metadata["prod_eta"]

    for msg in messages:
        result.ticket_ids.update(extract_ticket_ids(msg))
        if result.status_filter is None:
            result.status_filter = detect_status_filter(msg)
    return result
