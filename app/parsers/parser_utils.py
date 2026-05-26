from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from difflib import get_close_matches

import dateparser


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

DAY_NAMES = {
    "monday": 0, "mon": 0,
    "tuesday": 1, "tue": 1, "tues": 1,
    "wednesday": 2, "wed": 2,
    "thursday": 3, "thu": 3, "thurs": 3,
    "friday": 4, "fri": 4,
    "saturday": 5, "sat": 5,
    "sunday": 6, "sun": 6,
}

_CANONICAL_DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def _fuzzy_day_match(word: str) -> int | None:
    """Return weekday number if word is close enough to a day name, else None."""
    lower = word.lower()
    if lower in DAY_NAMES:
        return DAY_NAMES[lower]
    matches = get_close_matches(lower, _CANONICAL_DAYS, n=1, cutoff=0.7)
    if matches:
        return DAY_NAMES[matches[0]]
    return None

DAY_LABELS = {0: "Monday", 1: "Tuesday", 2: "Wednesday", 3: "Thursday", 4: "Friday", 5: "Saturday", 6: "Sunday"}

ORDINAL_SUFFIXES = {1: "st", 2: "nd", 3: "rd", 21: "st", 22: "nd", 23: "rd", 31: "st"}

DATEPARSER_SETTINGS = {
    "PREFER_DATES_FROM": "future",
    "PREFER_DAY_OF_MONTH": "first",
    "RETURN_AS_TIMEZONE_AWARE": False,
}

TIME_PATTERN = re.compile(r"\d{1,2}(?::\d{2})?\s*(?:am|pm)", re.IGNORECASE)
BARE_ORDINAL_RE = re.compile(r"^(\d{1,2})(?:st|nd|rd|th)?$", re.IGNORECASE)

_NOISE_RE = re.compile(
    r"\b(?:changed?|moved?|updated?|set|planned|shifted)\s+(?:to|for)\s*",
    re.IGNORECASE,
)
_PREFIX_RE = re.compile(r"^\s*(?:next|this|coming)\s+", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Date parsing (hybrid: DAY_NAMES for typos + dateparser for explicit dates)
# ---------------------------------------------------------------------------

def _resolve_day_name(text: str) -> date | None:
    """Match against known day names (with fuzzy matching) and return next occurrence."""
    stripped = _PREFIX_RE.sub("", text).strip().lower()
    word = stripped.split()[0] if stripped else ""
    target_weekday = _fuzzy_day_match(word)
    if target_weekday is None:
        return None
    today = date.today()
    days_ahead = (target_weekday - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return today + timedelta(days=days_ahead)


def _resolve_bare_ordinal(text: str) -> date | None:
    """Parse '12th', '27th', '1st' etc. as a day in the current or next month."""
    m = BARE_ORDINAL_RE.match(text.strip())
    if not m:
        return None
    day = int(m.group(1))
    today = date.today()
    try:
        result = date(today.year, today.month, day)
        if result <= today:
            if today.month == 12:
                result = date(today.year + 1, 1, day)
            else:
                result = date(today.year, today.month + 1, day)
        return result
    except (ValueError, OverflowError):
        return None


def _parse_date(text: str) -> datetime | None:
    """Parse free-form text into a datetime.

    Strategy:
    1. Strip noise words (changed to, moved to, etc.)
    2. Try day-name resolution (handles typos via DAY_NAMES dict)
    3. Try bare ordinal (12th, 27th — as day of current/next month)
    4. Fall back to dateparser (handles explicit dates like '27th May', 'May 21')
    """
    cleaned = _NOISE_RE.sub("", text).strip()
    if not cleaned:
        return None

    day_date = _resolve_day_name(cleaned)
    if day_date:
        time_match = TIME_PATTERN.search(cleaned)
        if time_match:
            time_parsed = dateparser.parse(time_match.group(0))
            if time_parsed:
                return datetime.combine(day_date, time_parsed.time())
        return datetime.combine(day_date, datetime.min.time())

    ordinal_date = _resolve_bare_ordinal(cleaned)
    if ordinal_date:
        return datetime.combine(ordinal_date, datetime.min.time())

    return dateparser.parse(cleaned, settings=DATEPARSER_SETTINGS)


def _resolve_date_from_text(text: str) -> date | None:
    """Resolve a date from free-form text."""
    parsed = _parse_date(text)
    if parsed and parsed.date() >= date.today():
        return parsed.date()
    return None


def _resolve_eta_text(text: str) -> str | None:
    """Parse ETA text into a formatted string (date + optional time)."""
    stripped = text.strip()
    if stripped.upper() == "TBD":
        return "TBD"

    has_tbd = bool(re.search(r"\bTBD\b", stripped, re.IGNORECASE))
    clean_text = re.sub(r"\s*\bTBD\b\s*", " ", stripped, flags=re.IGNORECASE).strip() if has_tbd else stripped

    parsed = _parse_date(clean_text)
    if not parsed:
        return None

    date_part = _format_date_short(parsed.date())

    if has_tbd:
        return f"{date_part} TBD"

    if parsed.hour != 0 or parsed.minute != 0:
        time_str = parsed.strftime("%-I%p").lower() if parsed.minute == 0 else parsed.strftime("%-I:%M%p").lower()
        return f"{date_part} {time_str}"

    time_match = TIME_PATTERN.search(text)
    if time_match:
        return f"{date_part} {time_match.group(0).strip()}"

    return date_part


# ---------------------------------------------------------------------------
# Extraction helpers (tickets, plain items, status)
# ---------------------------------------------------------------------------

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


@dataclass
class PlainItem:
    """A release item described in plain text (no Linear ticket)."""
    title: str
    user_id: str = ""
