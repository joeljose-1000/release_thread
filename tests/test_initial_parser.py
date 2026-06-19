from __future__ import annotations

from app.parsers.initial_parser import extract_from_messages


class TestExtractFromMessages:
    def test_multiple_messages(self) -> None:
        messages = [
            "Fix ENG-10",
            "Also ENG-20 and PLAT-30",
            "No tickets here",
        ]
        result = extract_from_messages(messages)
        assert result.ticket_ids == {"ENG-10", "ENG-20", "PLAT-30"}
        assert result.status_filter is None

    def test_empty_messages(self) -> None:
        result = extract_from_messages([])
        assert result.ticket_ids == set()
        assert result.status_filter is None

    def test_with_status_filter(self) -> None:
        messages = [
            "ENG-10 and ENG-20",
            "all items in review",
        ]
        result = extract_from_messages(messages)
        assert result.ticket_ids == {"ENG-10", "ENG-20"}
        assert result.status_filter == "Review"

    def test_plain_items_with_user_ids(self) -> None:
        messages = [
            "1.fix for admin whitelist\n2.ats sync logs",
            "https://linear.app/co/issue/WHA-100/some-task",
        ]
        user_ids = ["U_ALICE", "U_BOB"]
        result = extract_from_messages(messages, user_ids=user_ids)
        assert "WHA-100" in result.ticket_ids
        assert len(result.plain_items) == 2
        assert result.plain_items[0].title == "fix for admin whitelist"
        assert result.plain_items[0].user_id == "U_ALICE"
        assert result.plain_items[1].user_id == "U_ALICE"

    def test_eta_from_later_messages(self) -> None:
        messages = [
            "Please Share release items for next Thursday",
            "https://linear.app/co/issue/WHA-2479/some-task",
            "Dev eta May 20 12pm\nProd eta May 21 TBD",
        ]
        result = extract_from_messages(messages)
        assert result.dev_eta is not None
        assert "20th May" in result.dev_eta
        assert "12pm" in result.dev_eta
        assert result.prod_eta is not None
        assert "21st May" in result.prod_eta

    def test_later_eta_overrides_first_message_eta(self) -> None:
        messages = [
            "release items for Thursday\ndev eta: Monday",
            "dev eta May 25 3pm",
        ]
        result = extract_from_messages(messages)
        assert result.dev_eta is not None
        assert "25th May" in result.dev_eta
        assert "3pm" in result.dev_eta


class TestReleaseDateNextThis:
    def test_next_thursday(self) -> None:
        messages = ["Please Share release items for next Thursday"]
        result = extract_from_messages(messages)
        assert result.release_date is not None
        assert "Thursday" in result.release_date

    def test_this_friday(self) -> None:
        messages = ["release items for this Friday"]
        result = extract_from_messages(messages)
        assert result.release_date is not None
        assert "Friday" in result.release_date

    def test_plain_thursday_still_works(self) -> None:
        messages = ["release items for Thursday"]
        result = extract_from_messages(messages)
        assert result.release_date is not None
        assert "Thursday" in result.release_date


class TestCategoryHeaderParsing:
    def test_feature_and_fixes_headers(self) -> None:
        messages = [
            "Feature:\nAgent mode - candidate assistant\n\nFixes:\nQuestions changed for paused interview\nCandidate Assistant Issue"
        ]
        result = extract_from_messages(messages, user_ids=["U_SHAROOQ"])
        assert len(result.plain_items) == 3
        assert result.plain_items[0].title == "Agent mode - candidate assistant"
        assert result.plain_items[0].category == "Features"
        assert result.plain_items[1].category == "Bugs and Improvements"
        assert result.plain_items[2].category == "Bugs and Improvements"

    def test_feature_and_bug_with_ticket_urls(self) -> None:
        messages = [
            "feature:\nhttps://linear.app/co/issue/WHA-2524/interview-reschedule\n\nbug:\nhttps://linear.app/co/issue/WHA-2564/proctoring-tab-missing"
        ]
        result = extract_from_messages(messages, user_ids=["U_ALEX"])
        assert "WHA-2524" in result.ticket_ids
        assert "WHA-2564" in result.ticket_ids
        assert result.ticket_categories.get("WHA-2524") == "Features"
        assert result.ticket_categories.get("WHA-2564") == "Bugs and Improvements"

    def test_mixed_messages_with_and_without_headers(self) -> None:
        messages = [
            "https://linear.app/co/issue/WHA-2609/role-sync-failure",
            "Feature:\nAgent mode - candidate assistant\n\nFixes:\nQuestions changed",
            "https://linear.app/co/issue/WHA-2541/bug-duration",
        ]
        result = extract_from_messages(
            messages, user_ids=["U_JOEL", "U_SHAROOQ", "U_JOEL2"]
        )
        assert "WHA-2609" in result.ticket_ids
        assert "WHA-2541" in result.ticket_ids
        assert "WHA-2609" not in result.ticket_categories
        assert result.plain_items[0].title == "Agent mode - candidate assistant"
        assert result.plain_items[0].category == "Features"
        assert result.plain_items[1].title == "Questions changed"
        assert result.plain_items[1].category == "Bugs and Improvements"

    def test_no_headers_uses_standard_extraction(self) -> None:
        messages = ["1. Fix admin whitelist\n2. ATS sync logs"]
        result = extract_from_messages(messages, user_ids=["U_BOB"])
        assert len(result.plain_items) == 2
        assert result.plain_items[0].category == "Bugs and Improvements"
        assert result.plain_items[1].category == "Bugs and Improvements"

    def test_improvements_header(self) -> None:
        messages = ["Improvements:\nFaster search indexing"]
        result = extract_from_messages(messages, user_ids=["U_A"])
        assert result.plain_items[0].category == "Bugs and Improvements"

    def test_bugs_and_improvements_header(self) -> None:
        messages = ["Bugs and Improvements:\nLogin page fix"]
        result = extract_from_messages(messages, user_ids=["U_A"])
        assert result.plain_items[0].category == "Bugs and Improvements"

    def test_features_header_plural(self) -> None:
        messages = ["Features:\nNew dashboard"]
        result = extract_from_messages(messages, user_ids=["U_A"])
        assert result.plain_items[0].category == "Features"

    def test_user_id_carried_through(self) -> None:
        messages = [
            "Feature:\nNew feature item",
        ]
        result = extract_from_messages(messages, user_ids=["U_SHAROOQ"])
        assert result.plain_items[0].user_id == "U_SHAROOQ"


class TestHotfixDetection:
    def test_hotfix_in_header(self) -> None:
        messages = ["hotfix items for Thursday"]
        result = extract_from_messages(messages)
        assert result.is_hotfix is True
        assert result.release_date is not None

    def test_hotfix_keyword_anywhere(self) -> None:
        messages = ["This is a hotfix release\nDev ETA: Monday"]
        result = extract_from_messages(messages)
        assert result.is_hotfix is True

    def test_normal_release_not_hotfix(self) -> None:
        messages = ["release items for Thursday"]
        result = extract_from_messages(messages)
        assert result.is_hotfix is False
