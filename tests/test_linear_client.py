from __future__ import annotations

import pytest
import httpx
import respx

from app.linear.client import LINEAR_API_URL, LinearClient


@pytest.fixture
def linear_client() -> LinearClient:
    return LinearClient(api_key="test-key", timeout=5.0, max_concurrency=2)


@pytest.mark.asyncio
class TestLinearClient:
    @respx.mock
    async def test_fetch_issue_success(self, linear_client: LinearClient) -> None:
        respx.post(LINEAR_API_URL).respond(
            json={
                "data": {
                    "issues": {
                        "nodes": [
                            {
                                "title": "Fix crash",
                                "url": "https://linear.app/co/issue/ENG-101/fix-crash",
                                "assignee": {"name": "Raj", "displayName": "raj"},
                            }
                        ]
                    }
                }
            }
        )

        tickets = await linear_client.fetch_issues({"ENG-101"})
        assert len(tickets) == 1
        assert tickets[0].identifier == "ENG-101"
        assert tickets[0].title == "Fix crash"
        assert tickets[0].assignee == "raj"
        assert tickets[0].state is None

    @respx.mock
    async def test_fetch_issue_with_state(self, linear_client: LinearClient) -> None:
        respx.post(LINEAR_API_URL).respond(
            json={
                "data": {
                    "issues": {
                        "nodes": [
                            {
                                "title": "Fix crash",
                                "url": "https://linear.app/co/issue/ENG-101/fix-crash",
                                "assignee": {"name": "Raj", "displayName": "raj"},
                                "state": {"name": "In Review"},
                            }
                        ]
                    }
                }
            }
        )

        tickets = await linear_client.fetch_issues({"ENG-101"}, include_state=True)
        assert len(tickets) == 1
        assert tickets[0].state == "In Review"

    @respx.mock
    async def test_fetch_issue_not_found(self, linear_client: LinearClient) -> None:
        respx.post(LINEAR_API_URL).respond(
            json={"data": {"issues": {"nodes": []}}}
        )

        tickets = await linear_client.fetch_issues({"NOPE-999"})
        assert tickets == []

    @respx.mock
    async def test_fetch_issue_server_error_retries(self, linear_client: LinearClient) -> None:
        route = respx.post(LINEAR_API_URL)
        route.side_effect = [
            httpx.Response(500),
            httpx.Response(500),
            httpx.Response(500),
        ]

        tickets = await linear_client.fetch_issues({"ENG-1"})
        assert tickets == []

    @respx.mock
    async def test_fetch_multiple_issues(self, linear_client: LinearClient) -> None:
        def _handler(request: httpx.Request) -> httpx.Response:
            import json

            body = json.loads(request.content)
            ident = body["variables"]["filter"]["identifier"]["eq"]
            return httpx.Response(
                200,
                json={
                    "data": {
                        "issues": {
                            "nodes": [
                                {
                                    "title": f"Title for {ident}",
                                    "url": f"https://linear.app/co/issue/{ident}/slug",
                                    "assignee": None,
                                }
                            ]
                        }
                    }
                },
            )

        respx.post(LINEAR_API_URL).mock(side_effect=_handler)

        tickets = await linear_client.fetch_issues({"ENG-1", "ENG-2"})
        assert len(tickets) == 2
        identifiers = {t.identifier for t in tickets}
        assert identifiers == {"ENG-1", "ENG-2"}

    @respx.mock
    async def test_identifier_comes_from_caller(self, linear_client: LinearClient) -> None:
        """The identifier on TicketInfo is set from the queried ID, not the API response."""
        respx.post(LINEAR_API_URL).respond(
            json={
                "data": {
                    "issues": {
                        "nodes": [
                            {
                                "title": "Some title",
                                "url": "https://linear.app/co/issue/ENG-55/slug",
                                "assignee": None,
                            }
                        ]
                    }
                }
            }
        )

        tickets = await linear_client.fetch_issues({"ENG-55"})
        assert tickets[0].identifier == "ENG-55"
