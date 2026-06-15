from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from app.parsers.parser_utils import (
    PlainItem,
    _format_date,
    _format_date_short,
    _resolve_date_from_text,
    _resolve_eta_text,
    detect_status_filter,
    extract_plain_items,
    extract_ticket_ids,
)

DEV_ETA_PATTERN = re.compile(r"dev\s+eta\b.{0,60}", re.IGNORECASE)
PROD_ETA_PATTERN = re.compile(r"prod(?:uction)?\s+eta\b.{0,60}", re.IGNORECASE)

RELEASE_DATE_PATTERN = re.compile(
    r"(?:(?:release|hotfix)\s+(?:items?\s+)?(?:for|on)\s+(.+)"
    r"|(?:for|on)\s+(.+?)\s+(?:release|hotfix)\b"
    r"|(?:items?\s+for)\s+(.+?)\s+(?:release|hotfix)\b)",
    re.IGNORECASE,
)

HOTFIX_HEADER_PATTERN = re.compile(r"\bhotfix\b", re.IGNORECASE)

DEV_ETA_UPDATE = re.compile(
    r"(?:"
    r"(?:change|update|set)\s+(?:the\s+)?dev\s+eta\s*(?:(?:changed?|moved?)\s+to|to|is|:)\s*"
    r"|dev\s+eta\s*(?:(?:changed?|moved?)\s+to|is|:)?\s*"
    r")"
    r"(.+)",
    re.IGNORECASE,
)
PROD_ETA_UPDATE = re.compile(
    r"(?:"
    r"(?:change|update|set)\s+(?:the\s+)?prod(?:uction)?\s+eta\s*(?:(?:changed?|moved?|updated)\s+to|to|is|:)\s*"
    r"|prod(?:uction)?\s+eta\s*(?:(?:changed?|moved?|updated)\s+to|is|:)?\s*"
    r")"
    r"(.+)",
    re.IGNORECASE,
)


def extract_release_metadata(first_message: str) -> dict[str, str | date | bool | None]:
    """Extract release date, dev ETA, prod ETA, and hotfix flag from the opening message."""
    result: dict[str, str | date | bool | None] = {
        "release_date": None,
        "release_date_obj": None,
        "dev_eta": None,
        "prod_eta": None,
        "is_hotfix": bool(HOTFIX_HEADER_PATTERN.search(first_message)),
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


@dataclass
class ParseResult:
    ticket_ids: set[str] = field(default_factory=set)
    plain_items: list[PlainItem] = field(default_factory=list)
    status_filter: str | None = None
    release_date: str | None = None
    dev_eta: str | None = None
    prod_eta: str | None = None
    is_hotfix: bool = False


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
        result.is_hotfix = bool(metadata.get("is_hotfix"))

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
