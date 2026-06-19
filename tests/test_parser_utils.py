from __future__ import annotations

from app.parsers.parser_utils import (
    detect_status_filter,
    extract_plain_items,
    extract_ticket_ids,
    release_date_from_eta,
)


class TestExtractTicketIds:
    def test_plain_identifiers(self) -> None:
        text = "We need to fix ENG-123 and PLAT-456 before release"
        result = extract_ticket_ids(text)
        assert result == {"ENG-123", "PLAT-456"}

    def test_linear_urls(self) -> None:
        text = "See https://linear.app/company/issue/ENG-789/fix-the-thing"
        result = extract_ticket_ids(text)
        assert "ENG-789" in result

    def test_mixed_text_and_urls(self) -> None:
        text = (
            "Fixed ENG-101 and also check "
            "https://linear.app/myteam/issue/ENG-202/improve-perf "
            "and ENG-303"
        )
        result = extract_ticket_ids(text)
        assert result == {"ENG-101", "ENG-202", "ENG-303"}

    def test_deduplication(self) -> None:
        text = "ENG-100 is the same as ENG-100 and ENG-100"
        result = extract_ticket_ids(text)
        assert result == {"ENG-100"}

    def test_no_tickets(self) -> None:
        result = extract_ticket_ids("Nothing to see here")
        assert result == set()

    def test_lowercase_not_matched(self) -> None:
        result = extract_ticket_ids("eng-123 is not valid")
        assert result == set()

    def test_single_letter_prefix_not_matched(self) -> None:
        result = extract_ticket_ids("A-123 should not match")
        assert result == set()

    def test_url_with_query_params(self) -> None:
        text = "https://linear.app/co/issue/DEV-42/title?foo=bar"
        result = extract_ticket_ids(text)
        assert "DEV-42" in result

    def test_identifier_at_line_boundaries(self) -> None:
        text = "ENG-1\nENG-2\nENG-3"
        result = extract_ticket_ids(text)
        assert result == {"ENG-1", "ENG-2", "ENG-3"}


class TestDetectStatusFilter:
    def test_all_items_in_review(self) -> None:
        assert detect_status_filter("all items in review") == "Review"

    def test_all_tickets_in_done_status(self) -> None:
        assert detect_status_filter("all tickets in done status") == "Done"

    def test_all_issues_in_progress(self) -> None:
        assert detect_status_filter("all issues in progress") == "Progress"

    def test_no_status_filter(self) -> None:
        assert detect_status_filter("Fix ENG-123 please") is None

    def test_case_insensitive(self) -> None:
        assert detect_status_filter("ALL ITEMS IN REVIEW") == "Review"


class TestExtractPlainItems:
    def test_numbered_items(self) -> None:
        text = "1.fix for admin whitelist\n2.ats sync logs\n3.package upgrades"
        result = extract_plain_items(text)
        assert result == ["fix for admin whitelist", "ats sync logs", "package upgrades"]

    def test_numbered_with_linear_url_excluded(self) -> None:
        text = (
            "1.fix for admin whitelist\n"
            "2.https://linear.app/co/issue/WHA-2455/my-tasks-page-update"
        )
        result = extract_plain_items(text)
        assert result == ["fix for admin whitelist"]

    def test_numbered_with_identifier_excluded(self) -> None:
        text = "1.fix for admin whitelist\n2.ENG-123 fix login"
        result = extract_plain_items(text)
        assert result == ["fix for admin whitelist"]

    def test_bullet_dash_items(self) -> None:
        text = "- fix caching\n- improve logging"
        result = extract_plain_items(text)
        assert result == ["fix caching", "improve logging"]

    def test_no_items_in_plain_text(self) -> None:
        text = "Please add your release items for Thursday."
        result = extract_plain_items(text)
        assert result == []

    def test_mixed_numbered_and_link(self) -> None:
        text = (
            "1.fix for admin whitelist\n"
            "2.ats sync logs\n"
            "3.package upgrades\n"
            "4.https://linear.app/what-the-ai/issue/WHA-2455/my-tasks-page-update"
        )
        result = extract_plain_items(text)
        assert len(result) == 3
        assert "fix for admin whitelist" in result
        assert "ats sync logs" in result
        assert "package upgrades" in result


class TestReleaseDateFromEta:
    def test_date_with_time(self) -> None:
        result = release_date_from_eta("18th June 3pm")
        assert result is not None
        assert "18th June" in result
        assert " - " in result  # day name appended

    def test_date_with_tbd(self) -> None:
        result = release_date_from_eta("18th June TBD")
        assert result is not None
        assert "18th June" in result

    def test_date_only(self) -> None:
        result = release_date_from_eta("20th June")
        assert result is not None
        assert "20th June" in result

    def test_tbd_only(self) -> None:
        assert release_date_from_eta("TBD") is None

    def test_empty_string(self) -> None:
        assert release_date_from_eta("") is None

    def test_none_safe(self) -> None:
        assert release_date_from_eta("") is None
