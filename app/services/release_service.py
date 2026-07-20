from __future__ import annotations

import re
from typing import Any

from app.config.settings import Settings
from app.linear.client import LinearClient
from app.models.release import ReleaseSummary
from app.models.ticket import DEFAULT_CATEGORY, TicketInfo
from app.ocr.base import OCRProvider
from app.parsers.image_parser import extract_tickets_from_images
from app.parsers.initial_parser import extract_from_messages
from app.parsers.parser_utils import PlainItem, release_date_from_eta
from app.parsers.update_parser import parse_update_message
from app.services.pic_service import determine_pic
from app.services.release_state import ReleaseState, ReleaseStateStore
from app.slack.formatter import format_release_blocks, format_release_summary
from app.slack.thread import ThreadData, fetch_recent_messages, fetch_thread_messages
from app.utils.logging import get_logger

logger = get_logger(__name__)


class ReleaseService:
    def __init__(
        self,
        settings: Settings,
        linear_client: LinearClient,
        ocr_provider: OCRProvider,
    ) -> None:
        self._settings = settings
        self._linear = linear_client
        self._ocr = ocr_provider
        self._state_store = ReleaseStateStore()

    def has_active_release(self, channel: str, thread_ts: str) -> bool:
        return self._state_store.has(channel, thread_ts)

    async def _gather_thread_data(
        self,
        client: Any,
        channel: str,
        thread_ts: str | None,
    ) -> ThreadData:
        if thread_ts:
            return await fetch_thread_messages(client, channel, thread_ts)
        return await fetch_recent_messages(client, channel, self._settings.fallback_message_count)

    async def _build_team_member_map(self, client: Any) -> dict[str, str]:
        """Build a name→Slack-ID map filtered to configured TEAM_MEMBERS.

        Scans the Slack workspace user list but only includes users whose
        real_name or display_name matches a name in ``self._settings.team_members``
        (case-insensitive).
        """
        allowed = {n.lower() for n in self._settings.team_members}
        if not allowed:
            return {}

        name_map: dict[str, str] = {}
        try:
            cursor = None
            while True:
                kwargs: dict[str, Any] = {"limit": 200}
                if cursor:
                    kwargs["cursor"] = cursor
                resp = await client.users_list(**kwargs)
                for member in resp.get("members", []):
                    if member.get("is_bot") or member.get("deleted"):
                        continue
                    uid = member["id"]
                    profile = member.get("profile", {})
                    real_name = (profile.get("real_name") or "").strip()
                    display_name = (profile.get("display_name") or "").strip()
                    first_name = (profile.get("first_name") or "").strip()

                    if real_name.lower() not in allowed and display_name.lower() not in allowed:
                        continue

                    if display_name:
                        name_map[display_name.lower()] = uid
                    if real_name:
                        name_map[real_name.lower()] = uid
                    if first_name:
                        name_map[first_name.lower()] = uid

                cursor = resp.get("response_metadata", {}).get("next_cursor")
                if not cursor:
                    break
        except Exception:
            logger.exception("failed_to_fetch_slack_users")

        logger.info("team_member_map_built", user_count=len(name_map))
        return name_map

    async def _build_thread_participant_map(
        self, client: Any, user_ids: list[str]
    ) -> dict[str, str]:
        """Build a name→Slack-ID map from thread participants via users.info."""
        name_map: dict[str, str] = {}
        seen: set[str] = set()
        for uid in user_ids:
            if not uid or uid in seen:
                continue
            seen.add(uid)
            try:
                resp = await client.users_info(user=uid)
                user = resp.get("user", {})
                if user.get("is_bot") or user.get("deleted"):
                    continue
                profile = user.get("profile", {})
                for key in ("real_name", "display_name", "first_name"):
                    val = (profile.get(key) or "").strip()
                    if val:
                        name_map[val.lower()] = uid
            except Exception:
                logger.warning("thread_participant_lookup_failed", user_id=uid)
        return name_map

    @staticmethod
    def _normalize(name: str) -> str:
        """Normalize separators so ``joel.jose`` becomes ``joel jose``."""
        return re.sub(r"[.\-_]+", " ", name)

    def _resolve_assignee(self, assignee_name: str | None, name_map: dict[str, str]) -> str:
        """Convert a Linear assignee name to a Slack <@U123> mention if possible."""
        if not assignee_name:
            return ""
        lookup = assignee_name.strip().lower()
        normalized = self._normalize(lookup)

        slack_id = name_map.get(lookup)

        if not slack_id and normalized != lookup:
            slack_id = name_map.get(normalized)

        if not slack_id:
            parts = normalized.split()
            if parts:
                slack_id = name_map.get(parts[0])

        if not slack_id:
            for key, uid in name_map.items():
                if normalized in key or key.startswith(normalized):
                    slack_id = uid
                    break

        if slack_id:
            return f"<@{slack_id}>"

        logger.warning("assignee_slack_match_failed", assignee=assignee_name)
        return f"@{assignee_name}"

    async def process_release(
        self,
        client: Any,
        channel: str,
        thread_ts: str | None,
        user_id: str = "",
    ) -> None:
        """Full release flow: fetch thread -> parse -> OCR -> Linear -> format -> post."""
        try:
            thread_data = await self._gather_thread_data(client, channel, thread_ts)

            user_ids = [m.user_id for m in thread_data.messages]
            parse_result = extract_from_messages(thread_data.texts, user_ids=user_ids)
            text_ids = parse_result.ticket_ids
            status_filter = parse_result.status_filter
            logger.info(
                "text_tickets_extracted",
                count=len(text_ids),
                tickets=sorted(text_ids),
                plain_items=len(parse_result.plain_items),
                status_filter=status_filter,
                release_date=parse_result.release_date,
                dev_eta=parse_result.dev_eta,
                prod_eta=parse_result.prod_eta,
            )

            image_ids = await extract_tickets_from_images(
                thread_data.files,
                self._settings.slack_bot_token,
                self._ocr,
            )
            logger.info("image_tickets_extracted", count=len(image_ids), tickets=sorted(image_ids))

            all_ids = text_ids | image_ids

            need_state = status_filter is not None
            tickets: list[TicketInfo] = []
            if all_ids:
                logger.info("fetching_linear_issues", count=len(all_ids), include_state=need_state)
                tickets = await self._linear.fetch_issues(all_ids, include_state=need_state)

                if status_filter and tickets:
                    tickets = _filter_by_status(tickets, status_filter)
                    logger.info("status_filtered", status=status_filter, remaining=len(tickets))

            for ticket in tickets:
                cat = parse_result.ticket_categories.get(ticket.identifier)
                if cat:
                    ticket.category = cat

            plain_tickets = _build_plain_tickets(parse_result.plain_items)
            all_tickets = tickets + plain_tickets

            if not all_tickets:
                await client.chat_postMessage(
                    channel=channel,
                    thread_ts=thread_ts,
                    text=":warning: No release items found in this thread.",
                )
                return

            thread_map = await self._build_thread_participant_map(client, user_ids)
            team_map = await self._build_team_member_map(client)
            merged_map = {**team_map, **thread_map}

            overrides = parse_result.ticket_assignee_overrides
            for ticket in all_tickets:
                if ticket.assignee_display and ticket.assignee_display.startswith("<@"):
                    continue
                override = overrides.get(ticket.identifier)
                if override and override.startswith("<@"):
                    ticket.assignee_display = override
                    continue
                name = override or ticket.assignee
                resolved = self._resolve_assignee(name, thread_map)
                if not resolved.startswith("<@"):
                    resolved = self._resolve_assignee(name, team_map)
                ticket.assignee_display = resolved

            pic = determine_pic(all_tickets)
            if pic.startswith("@"):
                pic_name = pic[1:]
                pic = self._resolve_assignee(pic_name, thread_map)
                if not pic.startswith("<@"):
                    pic = self._resolve_assignee(pic_name, team_map)

            prod_eta = parse_result.prod_eta or "TBD"
            release_date_str = release_date_from_eta(prod_eta) or parse_result.release_date

            summary = ReleaseSummary(
                tickets=all_tickets,
                pic=pic,
                dev_eta=parse_result.dev_eta or "TBD",
                prod_eta=prod_eta,
                release_date_str=release_date_str,
                is_hotfix=parse_result.is_hotfix,
            )
            blocks = format_release_blocks(summary)
            fallback_text = format_release_summary(summary)

            response = await client.chat_postMessage(
                channel=channel,
                thread_ts=thread_ts,
                text=fallback_text,
                blocks=blocks,
            )
            logger.info("release_posted", channel=channel, thread_ts=thread_ts, ticket_count=len(all_tickets))

            if thread_ts:
                message_ts = response.get("ts", "")
                if message_ts:
                    state = ReleaseState(
                        channel=channel,
                        thread_ts=thread_ts,
                        message_ts=message_ts,
                        tickets=list(all_tickets),
                        summary=summary,
                        name_map=merged_map,
                        ticket_ids={t.identifier for t in all_tickets if t.identifier},
                        plain_titles={t.title.lower().strip() for t in all_tickets if not t.identifier},
                    )
                    self._state_store.put(state)
                    logger.info("release_state_stored", channel=channel, thread_ts=thread_ts)

        except Exception:
            logger.exception("release_processing_failed", channel=channel, thread_ts=thread_ts)
            try:
                await client.chat_postMessage(
                    channel=channel,
                    thread_ts=thread_ts,
                    text=":x: An error occurred while generating the release summary. Please try again.",
                )
            except Exception:
                logger.exception("error_message_post_failed")

    async def handle_thread_message(
        self,
        client: Any,
        channel: str,
        thread_ts: str,
        text: str,
        user_id: str,
    ) -> bool:
        """Process a new message in a monitored release thread.

        Returns True if the release summary was updated.
        """
        state = self._state_store.get(channel, thread_ts)
        if not state:
            return False

        action = parse_update_message(text, user_id)
        if not action.has_changes:
            return False

        async with state.lock:
            changed = False

            if action.remove_indices:
                sorted_indices = sorted(set(action.remove_indices), reverse=True)
                for idx in sorted_indices:
                    target = _nth_in_category(state.tickets, DEFAULT_CATEGORY, idx)
                    if target is not None:
                        removed = state.tickets.pop(target)
                        if removed.identifier:
                            state.ticket_ids.discard(removed.identifier)
                        else:
                            state.plain_titles.discard(removed.title.lower().strip())
                        changed = True
                if changed:
                    logger.info(
                        "items_removed_by_index",
                        indices=sorted(action.remove_indices),
                        channel=channel,
                        thread_ts=thread_ts,
                    )

            if action.remove_ticket_ids:
                before = len(state.tickets)
                state.tickets = [
                    t for t in state.tickets
                    if t.identifier not in action.remove_ticket_ids
                ]
                state.ticket_ids -= action.remove_ticket_ids
                if len(state.tickets) != before:
                    changed = True
                    logger.info(
                        "tickets_removed",
                        ids=sorted(action.remove_ticket_ids),
                        channel=channel,
                        thread_ts=thread_ts,
                    )

            if action.remove_texts:
                for remove_text in action.remove_texts:
                    before = len(state.tickets)
                    state.tickets, removed_titles = _remove_plain_by_text(
                        state.tickets, remove_text
                    )
                    state.plain_titles -= removed_titles
                    if len(state.tickets) != before:
                        changed = True
                        logger.info(
                            "plain_items_removed",
                            query=remove_text,
                            channel=channel,
                            thread_ts=thread_ts,
                        )

            new_linear_ids = action.add_ticket_ids - state.ticket_ids
            if new_linear_ids:
                try:
                    new_tickets = await self._linear.fetch_issues(
                        new_linear_ids, include_state=False
                    )
                    for ticket in new_tickets:
                        override = action.add_ticket_assignee_overrides.get(ticket.identifier)
                        if override and override.startswith("<@"):
                            ticket.assignee_display = override
                        else:
                            name = override or ticket.assignee
                            ticket.assignee_display = self._resolve_assignee(
                                name, state.name_map
                            )
                        cat = action.add_ticket_categories.get(ticket.identifier)
                        if cat:
                            ticket.category = cat
                        state.tickets.append(ticket)
                        state.ticket_ids.add(ticket.identifier)
                    if new_tickets:
                        changed = True
                        logger.info(
                            "tickets_added",
                            ids=sorted(new_linear_ids),
                            channel=channel,
                            thread_ts=thread_ts,
                        )
                except Exception:
                    logger.exception("failed_to_fetch_new_tickets", ids=sorted(new_linear_ids))

            new_plain = [
                item
                for item in action.add_plain_items
                if item.title.lower().strip() not in state.plain_titles
            ]
            if new_plain:
                for item in new_plain:
                    state.plain_titles.add(item.title.lower().strip())
                    if item.assignee_name and item.assignee_name.startswith("<@"):
                        display = item.assignee_name
                    elif item.assignee_name:
                        display = self._resolve_assignee(item.assignee_name, state.name_map)
                    elif item.user_id:
                        display = f"<@{item.user_id}>"
                    else:
                        display = ""
                    state.tickets.append(
                        TicketInfo(
                            identifier="",
                            title=item.title,
                            url=item.url,
                            assignee_display=display,
                            category=item.category,
                        )
                    )
                changed = True
                logger.info(
                    "plain_items_added",
                    count=len(new_plain),
                    channel=channel,
                    thread_ts=thread_ts,
                )

            if action.category_changes:
                for cat_change in action.category_changes:
                    for idx in cat_change.indices:
                        target = _nth_in_category(state.tickets, DEFAULT_CATEGORY, idx)
                        if target is not None:
                            state.tickets[target].category = cat_change.category
                            changed = True
                    for ticket in state.tickets:
                        if ticket.identifier and ticket.identifier in cat_change.ticket_ids:
                            ticket.category = cat_change.category
                            changed = True
                if changed:
                    logger.info(
                        "items_recategorized",
                        changes=[
                            {"indices": c.indices, "ticket_ids": sorted(c.ticket_ids), "category": c.category}
                            for c in action.category_changes
                        ],
                        channel=channel,
                        thread_ts=thread_ts,
                    )

            if action.is_hotfix is not None:
                state.summary.is_hotfix = action.is_hotfix
                changed = True
                logger.info("hotfix_toggled", is_hotfix=action.is_hotfix)

            if action.new_release_date is not None:
                state.summary.release_date_str = action.new_release_date
                changed = True
                logger.info("release_date_updated", new_date=action.new_release_date)

            if action.new_dev_eta is not None:
                state.summary.dev_eta = action.new_dev_eta
                changed = True
                logger.info("dev_eta_updated", new_eta=action.new_dev_eta)

            if action.new_prod_eta is not None:
                state.summary.prod_eta = action.new_prod_eta
                derived = release_date_from_eta(action.new_prod_eta)
                if derived:
                    state.summary.release_date_str = derived
                changed = True
                logger.info("prod_eta_updated", new_eta=action.new_prod_eta)

            if action.new_pic is not None:
                state.pic_override = action.new_pic
                changed = True
                logger.info("pic_updated", new_pic=action.new_pic)

            if not changed:
                return False

            if state.pic_override:
                pic = state.pic_override
            else:
                pic = determine_pic(state.tickets)
            if pic.startswith("@"):
                pic = self._resolve_assignee(pic[1:], state.name_map)

            state.summary = ReleaseSummary(
                tickets=state.tickets,
                pic=pic,
                dev_eta=state.summary.dev_eta,
                prod_eta=state.summary.prod_eta,
                release_date_str=state.summary.release_date_str,
                is_hotfix=state.summary.is_hotfix,
            )
            blocks = format_release_blocks(state.summary)
            fallback_text = format_release_summary(state.summary)

            try:
                await client.chat_update(
                    channel=channel,
                    ts=state.message_ts,
                    text=fallback_text,
                    blocks=blocks,
                )
                logger.info(
                    "release_updated",
                    channel=channel,
                    thread_ts=thread_ts,
                    ticket_count=len(state.tickets),
                )
            except Exception:
                logger.exception("release_update_failed", channel=channel, thread_ts=thread_ts)
                return False

        return True


def _build_plain_tickets(plain_items: list[PlainItem]) -> list[TicketInfo]:
    """Convert plain text release items into TicketInfo with the sender as assignee."""
    seen_titles: set[str] = set()
    tickets: list[TicketInfo] = []
    for item in plain_items:
        key = item.title.lower().strip()
        if key in seen_titles:
            continue
        seen_titles.add(key)
        if item.assignee_name and item.assignee_name.startswith("<@"):
            assignee_display = item.assignee_name
            assignee_raw = None
        elif item.assignee_name:
            assignee_display = f"@{item.assignee_name}"
            assignee_raw = item.assignee_name
        elif item.user_id:
            assignee_display = f"<@{item.user_id}>"
            assignee_raw = None
        else:
            assignee_display = ""
            assignee_raw = None
        tickets.append(
            TicketInfo(
                identifier="",
                title=item.title,
                url=item.url,
                assignee=assignee_raw,
                assignee_display=assignee_display,
                category=item.category,
            )
        )
    return tickets


def _filter_by_status(tickets: list[TicketInfo], status: str) -> list[TicketInfo]:
    """Keep only tickets whose state matches the requested status (case-insensitive)."""
    normalized = status.lower()
    return [t for t in tickets if t.state and t.state.lower() == normalized]


def _nth_in_category(
    tickets: list[TicketInfo], category: str, n: int
) -> int | None:
    """Return the flat-list index of the Nth item (1-based) in *category*, or None."""
    count = 0
    for i, t in enumerate(tickets):
        if t.category == category:
            count += 1
            if count == n:
                return i
    return None


def _remove_plain_by_text(
    tickets: list[TicketInfo], remove_text: str
) -> tuple[list[TicketInfo], set[str]]:
    """Remove plain items (no identifier) whose title matches *remove_text*.

    Matching strategy: exact match first, then substring in either direction.
    Returns the filtered list and the set of removed title keys (lowered).
    """
    query = remove_text.lower().strip()
    remaining: list[TicketInfo] = []
    removed_titles: set[str] = set()

    for t in tickets:
        if t.identifier:
            remaining.append(t)
            continue
        title_lower = t.title.lower().strip()
        if title_lower == query or query in title_lower or title_lower in query:
            removed_titles.add(title_lower)
        else:
            remaining.append(t)

    return remaining, removed_titles
