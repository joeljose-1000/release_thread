from __future__ import annotations

from app.parsers.update_parser import parse_update_message


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
