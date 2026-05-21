from __future__ import annotations

import re
from dataclasses import dataclass, field
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

REMOVAL_LINE_PATTERN = re.compile(
    r"\b(?:remove|drop|take\s+out|delete|exclude)\s+(.+)",
    re.IGNORECASE,
)

DEV_ETA_PATTERN = re.compile(r"dev\s+eta\b.{0,60}", re.IGNORECASE)
PROD_ETA_PATTERN = re.compile(r"prod(?:uction)?\s+eta\b.{0,60}", re.IGNORECASE)

RELEASE_DATE_PATTERN = re.compile(
    r"(?:release\s+(?:items?\s+)?(?:for|on)\s+(.+)"
    r"|(?:for|on)\s+(.+?)\s+release\b"
    r"|(?:items?\s+for)\s+(.+?)\s+release\b)",
    re.IGNORECASE,
)

RELEASE_DATE_UPDATE = re.compile(
    r"(?:(?:change|update|set)\s+(?:the\s+)?)?"
    r"release\s+"
    r"(?:"
    r"date\s*(?:(?:changed?|moved?)\s+to|to|is|:|=)\s*"
    r"|(?:moved?|planned)\s+(?:to|for)\s*"
    r"|date\s+"
    r")"
    r"(.+)",
    re.IGNORECASE,
)
DEV_ETA_UPDATE = re.compile(
    r"(?:(?:change|update|set)\s+(?:the\s+)?)?dev\s+eta\s*(?:(?:changed?|moved?)\s+to|to|is|:|=)?\s*(.+)",
    re.IGNORECASE,
)
PROD_ETA_UPDATE = re.compile(
    r"(?:(?:change|update|set)\s+(?:the\s+)?)?prod(?:uction)?\s+eta\s*(?:(?:changed?|moved?)\s+to|to|is|:|=)?\s*(.+)",
    re.IGNORECASE,
)
PIC_UPDATE = re.compile(
    r"(?:(?:change|update|set)\s+(?:the\s+)?)?pic\s*(?:(?:changed?|moved?)\s+to|to|is|:|=)\s*(.+)",
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


def _extract_item_indices(text: str) -> list[int]:
    """Extract 1-based item numbers from text like 'item 2 and 3', '#2, #3'."""
    cleaned = re.sub(
        r"\s+(?:from|in)\s+(?:the\s+)?release\.?\s*$",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()

    numbers = [int(m.group(1)) for m in re.finditer(r"#?(\d+)", cleaned)]
    if not numbers:
        return []

    if re.search(r"\bitems?\b", cleaned, re.IGNORECASE):
        return numbers
    if re.search(r"#\d", cleaned):
        return numbers
    return []


# ---------------------------------------------------------------------------
# Release metadata extraction (from thread's first message)
# ---------------------------------------------------------------------------

def extract_release_metadata(first_message: str) -> dict[str, str | date | None]:
    """Extract release date, dev ETA, and prod ETA from the thread's opening message."""
    result: dict[str, str | date | None] = {
        "release_date": None,
        "release_date_obj": None,
        "dev_eta": None,
        "prod_eta": None,
    }

    release_date_obj: date | None = None
    m = RELEASE_DATE_PATTERN.search(first_message)
    if m:
        date_text = m.group(1) or m.group(2) or m.group(3)
        if date_text:
            release_date_obj = _resolve_date_from_text(date_text.strip())
            if release_date_obj:
                result["release_date"] = _format_date(release_date_obj)
                result["release_date_obj"] = release_date_obj

    dev_match = DEV_ETA_PATTERN.search(first_message)
    if dev_match:
        eta_text = re.sub(r"^dev\s+eta\s*", "", dev_match.group(0), flags=re.IGNORECASE).strip()
        if eta_text:
            result["dev_eta"] = _resolve_eta_text(eta_text)

    prod_match = PROD_ETA_PATTERN.search(first_message)
    if prod_match:
        eta_text = re.sub(r"^prod(?:uction)?\s+eta\s*", "", prod_match.group(0), flags=re.IGNORECASE).strip()
        if eta_text:
            result["prod_eta"] = _resolve_eta_text(eta_text)

    if not result["prod_eta"] and release_date_obj:
        result["prod_eta"] = f"{_format_date_short(release_date_obj)} TBD"

    return result


def _extract_eta_from_message(msg: str) -> tuple[str | None, str | None]:
    """Try to extract dev and prod ETA from a single message using update patterns."""
    dev_eta: str | None = None
    prod_eta: str | None = None

    for line in msg.split("\n"):
        line = line.strip()
        if not line:
            continue
        dev_match = DEV_ETA_UPDATE.search(line)
        if dev_match:
            resolved = _resolve_eta_text(dev_match.group(1).strip())
            if resolved:
                dev_eta = resolved
            continue
        prod_match = PROD_ETA_UPDATE.search(line)
        if prod_match:
            resolved = _resolve_eta_text(prod_match.group(1).strip())
            if resolved:
                prod_eta = resolved

    return dev_eta, prod_eta


# ---------------------------------------------------------------------------
# Multi-message extraction (initial thread scan)
# ---------------------------------------------------------------------------

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

        if idx > 0:
            dev_eta, prod_eta = _extract_eta_from_message(msg)
            if dev_eta:
                result.dev_eta = dev_eta
            if prod_eta:
                result.prod_eta = prod_eta

    return result


# ---------------------------------------------------------------------------
# Real-time thread update parsing
# ---------------------------------------------------------------------------

@dataclass
class UpdateAction:
    """Parsed add/remove actions from a single real-time thread message."""

    add_ticket_ids: set[str] = field(default_factory=set)
    remove_ticket_ids: set[str] = field(default_factory=set)
    add_plain_items: list[PlainItem] = field(default_factory=list)
    remove_texts: list[str] = field(default_factory=list)
    remove_indices: list[int] = field(default_factory=list)
    new_release_date: str | None = None
    new_dev_eta: str | None = None
    new_prod_eta: str | None = None
    new_pic: str | None = None

    @property
    def has_changes(self) -> bool:
        return bool(
            self.add_ticket_ids
            or self.remove_ticket_ids
            or self.add_plain_items
            or self.remove_texts
            or self.remove_indices
            or self.new_release_date is not None
            or self.new_dev_eta is not None
            or self.new_prod_eta is not None
            or self.new_pic is not None
        )


def parse_update_message(text: str, user_id: str = "") -> UpdateAction:
    """Parse a single thread message for release item additions, removals,
    and metadata updates (release date, dev/prod ETA).

    Per-line analysis:
      1. Metadata updates — "change release date to …", "dev eta: …", etc.
      2. Removal keywords — remove/drop/delete/exclude/take out; supports
         ticket IDs, item indices ("remove item 2 and 3"), and plain text.
      3. Additions — ticket IDs and bulleted/numbered plain items.
    """
    action = UpdateAction()

    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue

        pic_match = PIC_UPDATE.search(line)
        if pic_match:
            action.new_pic = pic_match.group(1).strip()
            continue

        rd_match = RELEASE_DATE_UPDATE.search(line)
        if rd_match:
            resolved = _resolve_date_from_text(rd_match.group(1).strip())
            if resolved:
                action.new_release_date = _format_date(resolved)
            continue

        dev_match = DEV_ETA_UPDATE.search(line)
        if dev_match:
            resolved_eta = _resolve_eta_text(dev_match.group(1).strip())
            if resolved_eta:
                action.new_dev_eta = resolved_eta
            continue

        prod_match = PROD_ETA_UPDATE.search(line)
        if prod_match:
            resolved_eta = _resolve_eta_text(prod_match.group(1).strip())
            if resolved_eta:
                action.new_prod_eta = resolved_eta
            continue

        removal_match = REMOVAL_LINE_PATTERN.search(line)
        if removal_match:
            rest = removal_match.group(1).strip()
            ids = extract_ticket_ids(rest)
            action.remove_ticket_ids.update(ids)
            if not ids:
                indices = _extract_item_indices(rest)
                if indices:
                    action.remove_indices.extend(indices)
                else:
                    cleaned = re.sub(
                        r"\s+(?:from|in)\s+(?:the\s+)?release\.?\s*$",
                        "",
                        rest,
                        flags=re.IGNORECASE,
                    ).strip().rstrip(".")
                    if cleaned:
                        action.remove_texts.append(cleaned)
            continue

        ids = extract_ticket_ids(line)
        action.add_ticket_ids.update(ids)

        if not ids:
            for item_text in extract_plain_items(line):
                action.add_plain_items.append(
                    PlainItem(title=item_text, user_id=user_id)
                )

    return action
