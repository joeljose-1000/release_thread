from __future__ import annotations

import asyncio

import httpx

from app.linear.models import LinearIssue
from app.linear.queries import ISSUE_BASIC, ISSUE_WITH_STATE
from app.models.ticket import TicketInfo
from app.utils.logging import get_logger
from app.utils.retry import api_retry

logger = get_logger(__name__)

LINEAR_API_URL = "https://api.linear.app/graphql"


class LinearClient:
    def __init__(self, api_key: str, *, timeout: float = 30.0, max_concurrency: int = 5) -> None:
        self._headers = {
            "Authorization": api_key,
            "Content-Type": "application/json",
        }
        self._timeout = timeout
        self._semaphore = asyncio.Semaphore(max_concurrency)

    @api_retry
    async def _query(
        self,
        client: httpx.AsyncClient,
        identifier: str,
        *,
        include_state: bool = False,
    ) -> LinearIssue | None:
        query = ISSUE_WITH_STATE if include_state else ISSUE_BASIC
        payload = {
            "query": query,
            "variables": {"id": identifier},
        }
        resp = await client.post(LINEAR_API_URL, json=payload, headers=self._headers, timeout=self._timeout)
        resp.raise_for_status()
        data = resp.json()

        if "errors" in data:
            logger.warning("linear_graphql_errors", identifier=identifier, errors=data["errors"])

        issue_data = data.get("data", {}).get("issue")
        if not issue_data:
            logger.warning("linear_issue_not_found", identifier=identifier)
            return None

        return LinearIssue.model_validate(issue_data)

    async def fetch_issue(
        self,
        client: httpx.AsyncClient,
        identifier: str,
        *,
        include_state: bool = False,
    ) -> TicketInfo | None:
        async with self._semaphore:
            issue = await self._query(client, identifier, include_state=include_state)
            if issue is None:
                return None
            return TicketInfo(
                identifier=identifier,
                title=issue.title,
                url=issue.url,
                assignee=issue.assignee.label if issue.assignee else None,
                state=issue.state.name if issue.state else None,
            )

    async def fetch_issues(
        self,
        identifiers: set[str],
        *,
        include_state: bool = False,
    ) -> list[TicketInfo]:
        tickets: list[TicketInfo] = []
        async with httpx.AsyncClient() as client:
            tasks = [
                self.fetch_issue(client, ident, include_state=include_state)
                for ident in sorted(identifiers)
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, TicketInfo):
                tickets.append(result)
            elif isinstance(result, Exception):
                logger.error("linear_fetch_error", error=str(result))

        return tickets
