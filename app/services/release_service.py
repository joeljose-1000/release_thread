from __future__ import annotations

from typing import Any

from app.config.settings import Settings
from app.linear.client import LinearClient
from app.models.release import ReleaseSummary
from app.models.ticket import TicketInfo
from app.ocr.base import OCRProvider
from app.parsers.image_parser import extract_tickets_from_images
from app.parsers.ticket_parser import PlainItem, extract_from_messages
from app.services.pic_service import determine_pic
from app.slack.formatter import format_release_summary
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
            message = format_release_summary(summary)

            await client.chat_postMessage(
                channel=channel,
                thread_ts=thread_ts,
                text=message,
            )
            logger.info("release_posted", channel=channel, thread_ts=thread_ts, ticket_count=len(all_tickets))

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
