from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.parsers.parser_utils import (
    PlainItem,
    _format_date,
    _resolve_date_from_text,
    _resolve_eta_text,
    extract_plain_items,
    extract_ticket_ids,
)

REMOVAL_LINE_PATTERN = re.compile(
    r"\b(?:remove|drop|take\s+out|delete|exclude)\s+(.+)",
    re.IGNORECASE,
)

RELEASE_DATE_UPDATE = re.compile(
    r"(?:"
    r"(?:change|update|set)\s+(?:the\s+)?release\s+(?:date\s*(?:(?:changed?|moved?)\s+to|to|is|:)\s*|(?:moved?|planned)\s+(?:to|for)\s*|date\s+)"
    r"|release\s+(?:date\s*(?:(?:changed?|moved?)\s+to|is|:)\s*|(?:moved?|planned)\s+(?:to|for)\s*)"
    r")"
    r"(.+)",
    re.IGNORECASE,
)
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
PIC_UPDATE = re.compile(
    r"(?:(?:change|update|set)\s+(?:the\s+)?)?pic\s*(?:(?:changed?|moved?)\s+to|to|is|:)\s*(.+)",
    re.IGNORECASE,
)


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
