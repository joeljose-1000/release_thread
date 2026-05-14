from __future__ import annotations

from typing import Any

from app.config.settings import Settings
from app.linear.client import LinearClient
from app.models.release import ReleaseSummary
from app.models.ticket import TicketInfo
from app.ocr.base import OCRProvider
from app.parsers.image_parser import extract_tickets_from_images
from app.parsers.ticket_parser import PlainItem, extract_from_messages, parse_update_message
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

    async def _build_name_to_slack_id_map(self, client: Any) -> dict[str, str]:
        """Build a mapping from display names / real names to Slack user IDs.

        Keys are lowercased. Multiple keys point to the same user ID so that
        matching by first name, full name, or display name all work.
        """
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
                    email = (profile.get("email") or "").strip()

                    if display_name:
                        name_map[display_name.lower()] = uid
                    if real_name:
                        name_map[real_name.lower()] = uid
                    if first_name:
                        name_map[first_name.lower()] = uid
                    if email:
                        # Map the local part of the email (before @)
                        local = email.split("@")[0].lower()
                        name_map[local] = uid

                cursor = resp.get("response_metadata", {}).get("next_cursor")
                if not cursor:
                    break
        except Exception:
            logger.exception("failed_to_fetch_slack_users")

        logger.info("slack_user_map_built", user_count=len(name_map))
        return name_map

    def _resolve_assignee(self, assignee_name: str | None, name_map: dict[str, str]) -> str:
        """Convert a Linear assignee name to a Slack <@U123> mention if possible."""
        if not assignee_name:
            return ""
        lookup = assignee_name.strip().lower()

        # Try exact match on full name
        slack_id = name_map.get(lookup)

        # Try first name only
        if not slack_id:
            first = lookup.split()[0] if lookup.split() else lookup
            slack_id = name_map.get(first)

        # Try matching as substring (e.g. Linear has "sharooq" and Slack has "sharooq farzeen a k")
        if not slack_id:
            for key, uid in name_map.items():
                if lookup in key or key.startswith(lookup):
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

            plain_tickets = _build_plain_tickets(parse_result.plain_items)
            all_tickets = tickets + plain_tickets

            if not all_tickets:
                await client.chat_postMessage(
                    channel=channel,
                    thread_ts=thread_ts,
                    text=":warning: No release items found in this thread.",
                )
                return

            name_map = await self._build_name_to_slack_id_map(client)

            for ticket in all_tickets:
                if ticket.assignee_display and ticket.assignee_display.startswith("<@"):
                    continue
                ticket.assignee_display = self._resolve_assignee(ticket.assignee, name_map)

            pic = determine_pic(all_tickets)
            if pic.startswith("@"):
                pic_name = pic[1:]
                pic = self._resolve_assignee(pic_name, name_map)

            summary = ReleaseSummary(
                tickets=all_tickets,
                pic=pic,
                dev_eta=parse_result.dev_eta or "TBD",
                prod_eta=parse_result.prod_eta or "TBD",
                release_date_str=parse_result.release_date,
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
                        name_map=name_map,
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
                    pos = idx - 1
                    if 0 <= pos < len(state.tickets):
                        removed = state.tickets.pop(pos)
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
                        ticket.assignee_display = self._resolve_assignee(
                            ticket.assignee, state.name_map
                        )
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
                    state.tickets.append(
                        TicketInfo(
                            identifier="",
                            title=item.title,
                            url="",
                            assignee_display=f"<@{item.user_id}>" if item.user_id else "",
                        )
                    )
                changed = True
                logger.info(
                    "plain_items_added",
                    count=len(new_plain),
                    channel=channel,
                    thread_ts=thread_ts,
                )

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
                changed = True
                logger.info("prod_eta_updated", new_eta=action.new_prod_eta)

            if not changed:
                return False

            pic = determine_pic(state.tickets)
            if pic.startswith("@"):
                pic = self._resolve_assignee(pic[1:], state.name_map)

            state.summary = ReleaseSummary(
                tickets=state.tickets,
                pic=pic,
                dev_eta=state.summary.dev_eta,
                prod_eta=state.summary.prod_eta,
                release_date_str=state.summary.release_date_str,
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
        tickets.append(
            TicketInfo(
                identifier="",
                title=item.title,
                url="",
                assignee_display=f"<@{item.user_id}>" if item.user_id else "",
            )
        )
    return tickets


def _filter_by_status(tickets: list[TicketInfo], status: str) -> list[TicketInfo]:
    """Keep only tickets whose state matches the requested status (case-insensitive)."""
    normalized = status.lower()
    return [t for t in tickets if t.state and t.state.lower() == normalized]


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
