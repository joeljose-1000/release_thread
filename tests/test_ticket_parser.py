from __future__ import annotations

from app.parsers.ticket_parser import (
    detect_status_filter,
    extract_from_messages,
    extract_plain_items,
    extract_ticket_ids,
    parse_update_message,
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


class TestParseUpdateMessage:
    def test_add_ticket_ids(self) -> None:
        action = parse_update_message("ENG-123 and PLAT-456")
        assert action.add_ticket_ids == {"ENG-123", "PLAT-456"}
        assert action.remove_ticket_ids == set()

    def test_add_ticket_from_url(self) -> None:
        action = parse_update_message(
            "https://linear.app/team/issue/ENG-789/fix-something"
        )
        assert "ENG-789" in action.add_ticket_ids

    def test_remove_ticket_ids(self) -> None:
        action = parse_update_message("remove ENG-123")
        assert action.remove_ticket_ids == {"ENG-123"}
        assert action.add_ticket_ids == set()

    def test_remove_multiple_tickets(self) -> None:
        action = parse_update_message("drop ENG-123 and ENG-456")
        assert action.remove_ticket_ids == {"ENG-123", "ENG-456"}

    def test_remove_plain_text(self) -> None:
        action = parse_update_message("remove fix login page")
        assert action.remove_texts == ["fix login page"]
        assert action.remove_ticket_ids == set()

    def test_remove_plain_text_strips_trailing(self) -> None:
        action = parse_update_message("remove fix login page from the release.")
        assert action.remove_texts == ["fix login page"]

    def test_remove_keywords_case_insensitive(self) -> None:
        action = parse_update_message("REMOVE ENG-100")
        assert action.remove_ticket_ids == {"ENG-100"}

    def test_delete_keyword(self) -> None:
        action = parse_update_message("delete ENG-200")
        assert action.remove_ticket_ids == {"ENG-200"}

    def test_exclude_keyword(self) -> None:
        action = parse_update_message("exclude ENG-300")
        assert action.remove_ticket_ids == {"ENG-300"}

    def test_take_out_keyword(self) -> None:
        action = parse_update_message("take out ENG-400")
        assert action.remove_ticket_ids == {"ENG-400"}

    def test_add_plain_item_bulleted(self) -> None:
        action = parse_update_message("- Fix caching layer", user_id="U_ALICE")
        assert len(action.add_plain_items) == 1
        assert action.add_plain_items[0].title == "Fix caching layer"
        assert action.add_plain_items[0].user_id == "U_ALICE"

    def test_add_plain_item_numbered(self) -> None:
        action = parse_update_message("1. Fix caching layer", user_id="U_BOB")
        assert len(action.add_plain_items) == 1
        assert action.add_plain_items[0].title == "Fix caching layer"

    def test_mixed_lines_add_and_remove(self) -> None:
        text = "remove ENG-123\nENG-456"
        action = parse_update_message(text)
        assert action.remove_ticket_ids == {"ENG-123"}
        assert action.add_ticket_ids == {"ENG-456"}

    def test_no_changes(self) -> None:
        action = parse_update_message("just a regular conversation message")
        assert not action.has_changes

    def test_empty_text(self) -> None:
        action = parse_update_message("")
        assert not action.has_changes

    def test_drop_plain_text(self) -> None:
        action = parse_update_message("drop the admin whitelist fix")
        assert action.remove_texts == ["the admin whitelist fix"]
        assert action.add_ticket_ids == set()

    # --- Remove by item index ---

    def test_remove_item_by_index(self) -> None:
        action = parse_update_message("remove item 2")
        assert action.remove_indices == [2]

    def test_remove_items_by_multiple_indices(self) -> None:
        action = parse_update_message("remove item 2 and 3 from release")
        assert sorted(action.remove_indices) == [2, 3]

    def test_remove_items_comma_separated(self) -> None:
        action = parse_update_message("remove items 1, 4, 5")
        assert sorted(action.remove_indices) == [1, 4, 5]

    def test_remove_items_hash_notation(self) -> None:
        action = parse_update_message("remove #2 and #3")
        assert sorted(action.remove_indices) == [2, 3]

    def test_remove_item_drop_keyword(self) -> None:
        action = parse_update_message("drop item 3 from the release")
        assert action.remove_indices == [3]

    # --- Release date updates ---

    def test_change_release_date_explicit(self) -> None:
        action = parse_update_message("change release date to 15 May")
        assert action.new_release_date is not None
        assert "15th May" in action.new_release_date

    def test_update_release_date_day_name(self) -> None:
        action = parse_update_message("update release date to Thursday")
        assert action.new_release_date is not None
        assert "Thursday" in action.new_release_date

    def test_release_date_with_ordinal(self) -> None:
        action = parse_update_message("release date is 22nd June")
        assert action.new_release_date is not None
        assert "22nd June" in action.new_release_date

    def test_release_date_month_first(self) -> None:
        action = parse_update_message("set release date to June 22")
        assert action.new_release_date is not None
        assert "22nd June" in action.new_release_date

    # --- Dev ETA updates ---

    def test_change_dev_eta_day(self) -> None:
        action = parse_update_message("dev eta: Monday 9am")
        assert action.new_dev_eta is not None
        assert "Monday" not in action.new_dev_eta  # resolved to a date
        assert "9am" in action.new_dev_eta

    def test_change_dev_eta_explicit_date(self) -> None:
        action = parse_update_message("change dev eta to 15 May 9am")
        assert action.new_dev_eta is not None
        assert "15th May" in action.new_dev_eta
        assert "9am" in action.new_dev_eta

    def test_dev_eta_tbd(self) -> None:
        action = parse_update_message("dev eta: TBD")
        assert action.new_dev_eta == "TBD"

    def test_dev_eta_date_only(self) -> None:
        action = parse_update_message("update dev eta to 20 May")
        assert action.new_dev_eta is not None
        assert "20th May" in action.new_dev_eta

    # --- Prod ETA updates ---

    def test_change_prod_eta(self) -> None:
        action = parse_update_message("prod eta: Wednesday 3pm")
        assert action.new_prod_eta is not None
        assert "3pm" in action.new_prod_eta

    def test_change_production_eta(self) -> None:
        action = parse_update_message("change production eta to 16 May 4pm")
        assert action.new_prod_eta is not None
        assert "16th May" in action.new_prod_eta
        assert "4pm" in action.new_prod_eta

    def test_prod_eta_tbd(self) -> None:
        action = parse_update_message("set prod eta to TBD")
        assert action.new_prod_eta == "TBD"

    # --- Combined updates ---

    def test_metadata_does_not_trigger_removal(self) -> None:
        action = parse_update_message("change release date to 15 May")
        assert action.remove_ticket_ids == set()
        assert action.remove_texts == []
        assert action.remove_indices == []

    def test_has_changes_with_metadata_only(self) -> None:
        action = parse_update_message("dev eta: Monday")
        assert action.has_changes

    # --- ETA without separator ---

    def test_dev_eta_no_separator(self) -> None:
        action = parse_update_message("Dev eta May 20 12pm")
        assert action.new_dev_eta is not None
        assert "20th May" in action.new_dev_eta
        assert "12pm" in action.new_dev_eta

    def test_prod_eta_no_separator(self) -> None:
        action = parse_update_message("Prod eta May 21 TBD")
        assert action.new_prod_eta is not None

    def test_prod_eta_no_separator_day_name(self) -> None:
        action = parse_update_message("prod eta Thursday 3pm")
        assert action.new_prod_eta is not None
        assert "3pm" in action.new_prod_eta


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
