import unittest

from domain import Match, Participant, Teams, display_name
from domain.participation import (
    Change,
    Outcome,
    Person,
    decide_add,
    decide_join,
    decide_leave,
    decide_maybe,
    decide_propose,
    decide_remove,
)

TEAMS = Teams(("anna",), ("bea",))


def match(*players, target=4, teams=None):
    """players are names; a trailing "?" marks a maybe."""
    participants = [Participant(p.rstrip("?"), p.endswith("?")) for p in players]
    return Match(chat_id=1, participants=participants, target=target, teams=teams)


class TestJoin(unittest.TestCase):
    def test_a_new_name_is_added(self):
        self.assertEqual(
            decide_join(match("anna"), Person("bea")), Change(Outcome.ADDED, "bea")
        )

    def test_a_confirmed_name_is_already_in_even_when_full(self):
        m = match("anna", "bea", target=2)
        self.assertEqual(
            decide_join(m, Person("Anna")), Change(Outcome.ALREADY_IN, "anna")
        )

    def test_a_maybe_is_confirmed(self):
        self.assertEqual(
            decide_join(match("anna", "bea?"), Person("bea")),
            Change(Outcome.CONFIRMED, "bea"),
        )

    def test_a_maybe_is_confirmed_even_when_the_list_is_full(self):
        m = match("anna", "bea?", target=2)
        self.assertEqual(decide_join(m, Person("BEA")).outcome, Outcome.CONFIRMED)

    def test_the_target_is_reached_at_the_boundary_only(self):
        self.assertFalse(
            decide_join(match("a", "b", target=4), Person("c")).reached_target
        )
        self.assertTrue(
            decide_join(match("a", "b", "c", target=4), Person("d")).reached_target
        )
        self.assertTrue(
            decide_join(match("a", "b", "c?", target=3), Person("c")).reached_target
        )
        self.assertFalse(
            decide_join(match("a", "b?", "c?", target=3), Person("b")).reached_target
        )

    def test_maybe_participants_hold_a_place(self):
        full = match("a", "b?", target=2)
        self.assertEqual(decide_join(full, Person("c")), Change(Outcome.FULL, "c"))

    def test_joining_never_revokes_the_teams(self):
        m = match("anna", "bea?", teams=TEAMS)
        self.assertFalse(decide_join(m, Person("bea")).revokes_teams)
        self.assertFalse(decide_join(m, Person("carlo")).revokes_teams)


class TestMaybe(unittest.TestCase):
    def test_a_new_name_is_proposed(self):
        self.assertEqual(
            decide_maybe(match("anna"), Person("bea")), Change(Outcome.PROPOSED, "bea")
        )

    def test_a_maybe_is_already_maybe_even_when_full(self):
        m = match("anna", "bea?", target=2, teams=TEAMS)
        self.assertEqual(
            decide_maybe(m, Person("Bea")), Change(Outcome.ALREADY_MAYBE, "bea")
        )

    def test_a_confirmed_name_moves_to_maybe(self):
        self.assertEqual(
            decide_maybe(match("anna"), Person("ANNA")),
            Change(Outcome.MOVED_TO_MAYBE, "anna"),
        )

    def test_a_full_list_refuses_a_new_maybe(self):
        self.assertEqual(
            decide_maybe(match("a", "b?", target=2, teams=TEAMS), Person("c")),
            Change(Outcome.FULL, "c"),
        )

    def test_the_teams_are_revoked_only_when_the_list_changes(self):
        with_teams = match("anna", "carlo?", teams=TEAMS)
        self.assertTrue(decide_maybe(with_teams, Person("anna")).revokes_teams)
        self.assertTrue(decide_maybe(with_teams, Person("bea")).revokes_teams)
        self.assertFalse(decide_maybe(with_teams, Person("carlo")).revokes_teams)
        self.assertFalse(decide_maybe(match("anna"), Person("anna")).revokes_teams)
        self.assertFalse(decide_maybe(match("anna"), Person("bea")).revokes_teams)

    def test_the_target_is_never_reached(self):
        self.assertFalse(decide_maybe(match("a", "b", "c"), Person("d")).reached_target)


class TestLeave(unittest.TestCase):
    def test_a_confirmed_name_is_removed(self):
        self.assertEqual(
            decide_leave(match("anna"), Person("Anna")), Change(Outcome.REMOVED, "anna")
        )

    def test_a_maybe_is_removed(self):
        self.assertEqual(
            decide_leave(match("anna?"), Person("anna")),
            Change(Outcome.REMOVED_MAYBE, "anna"),
        )

    def test_an_unknown_name_is_not_in(self):
        self.assertEqual(
            decide_leave(match("anna", teams=TEAMS), Person("carlo")),
            Change(Outcome.NOT_IN, "carlo"),
        )

    def test_the_teams_are_revoked_by_the_two_removals_only(self):
        self.assertTrue(
            decide_leave(match("anna", teams=TEAMS), Person("anna")).revokes_teams
        )
        self.assertTrue(
            decide_leave(match("anna?", teams=TEAMS), Person("anna")).revokes_teams
        )
        self.assertFalse(decide_leave(match("anna"), Person("anna")).revokes_teams)
        self.assertFalse(
            decide_leave(match("anna", teams=TEAMS), Person("bea")).revokes_teams
        )


class TestChange(unittest.TestCase):
    def test_only_the_outcomes_that_touch_the_list_change_it(self):
        changing = {
            Outcome.ADDED,
            Outcome.CONFIRMED,
            Outcome.PROPOSED,
            Outcome.MOVED_TO_MAYBE,
            Outcome.REMOVED,
            Outcome.REMOVED_MAYBE,
        }
        for outcome in Outcome:
            self.assertEqual(
                Change(outcome, "x").changes_list, outcome in changing, outcome
            )

    def test_the_values_are_lowercase_snake_strings(self):
        self.assertEqual(Outcome.MOVED_TO_MAYBE, "moved_to_maybe")
        self.assertEqual(Outcome.ALREADY_IN.value, "already_in")


def with_ids(*rows):
    """rows are (name, telegram user id), confirmed, in order; a "?" marks a maybe."""
    return Match(
        chat_id=1,
        participants=[
            Participant(name.rstrip("?"), name.endswith("?"), user_id)
            for name, user_id in rows
        ],
        target=4,
    )


class TestDisplayName(unittest.TestCase):
    def test_the_username_wins_and_is_lowercased(self):
        self.assertEqual(display_name("Mario", "Mario", "Rossi"), "@mario")

    def test_without_username_the_names_are_joined(self):
        self.assertEqual(display_name(None, "Luca", "Bianchi"), "Luca Bianchi")
        self.assertEqual(display_name("", "Luca", None), "Luca")
        self.assertEqual(display_name(None, None, "Bianchi"), "Bianchi")

    def test_nothing_to_show_is_none(self):
        self.assertIsNone(display_name(None, None, None))
        self.assertIsNone(display_name(None, "", ""))


class TestFindPerson(unittest.TestCase):
    def test_the_user_id_finds_the_row_whatever_its_name_and_status(self):
        m = with_ids(("@old", 7), ("@bea?", 8))
        self.assertEqual(
            m.find_person(Person("@new", 7)), Participant("@old", False, 7)
        )
        self.assertEqual(m.find_person(Person("@x", 8)), Participant("@bea", True, 8))

    def test_the_user_id_wins_over_a_name_match(self):
        m = with_ids(("@new", None), ("@old", 7))
        self.assertEqual(
            m.find_person(Person("@new", 7)), Participant("@old", False, 7)
        )

    def test_the_name_finds_a_row_without_user_id_ignoring_case(self):
        m = with_ids(("@anna", None))
        self.assertEqual(m.find_person(Person("@ANNA", 7)), Participant("@anna"))
        self.assertEqual(m.find_person(Person("@anna")), Participant("@anna"))

    def test_the_name_finds_a_row_of_the_same_user_id(self):
        m = with_ids(("@anna", 7))
        self.assertEqual(
            m.find_person(Person("@Anna", 7)), Participant("@anna", False, 7)
        )

    def test_a_row_of_another_user_id_is_someone_else(self):
        m = with_ids(("@anna", 7))
        self.assertIsNone(m.find_person(Person("@anna", 8)))
        self.assertIsNone(m.find_person(Person("@anna")))
        self.assertTrue(m.name_taken_by_other(Person("@anna", 8)))
        self.assertTrue(m.name_taken_by_other(Person("@anna")))

    def test_nobody_found(self):
        self.assertIsNone(with_ids(("@anna", 7)).find_person(Person("@bea", 9)))
        self.assertFalse(with_ids(("@anna", 7)).name_taken_by_other(Person("@bea", 9)))
        self.assertFalse(with_ids(("@anna", 7)).name_taken_by_other(Person("@anna", 7)))


class TestDecideWithIds(unittest.TestCase):
    def test_new_rows_carry_the_user_id(self):
        self.assertEqual(
            decide_join(match(), Person("@bea", 8)),
            Change(Outcome.ADDED, "@bea", telegram_user_id=8),
        )
        self.assertEqual(
            decide_maybe(match(), Person("@bea", 8)),
            Change(Outcome.PROPOSED, "@bea", telegram_user_id=8),
        )

    def test_after_a_username_change_the_stored_name_is_used(self):
        m = with_ids(("@old", 7), ("@bea?", 8))
        self.assertEqual(
            decide_join(m, Person("@new", 7)), Change(Outcome.ALREADY_IN, "@old")
        )
        self.assertEqual(
            decide_join(m, Person("@x", 8)), Change(Outcome.CONFIRMED, "@bea")
        )
        self.assertEqual(
            decide_maybe(m, Person("@new", 7)), Change(Outcome.MOVED_TO_MAYBE, "@old")
        )
        self.assertEqual(
            decide_maybe(m, Person("@x", 8)), Change(Outcome.ALREADY_MAYBE, "@bea")
        )
        self.assertEqual(
            decide_leave(m, Person("@new", 7)), Change(Outcome.REMOVED, "@old")
        )
        self.assertEqual(
            decide_leave(m, Person("@x", 8)), Change(Outcome.REMOVED_MAYBE, "@bea")
        )

    def test_a_name_held_by_another_user_is_taken_even_when_full(self):
        m = with_ids(("@anna", 7), ("@bea", 8))
        m = Match(chat_id=1, participants=m.participants, target=2)
        self.assertEqual(
            decide_join(m, Person("@anna", 9)), Change(Outcome.NAME_TAKEN, "@anna")
        )
        self.assertEqual(
            decide_maybe(m, Person("@ANNA", 9)), Change(Outcome.NAME_TAKEN, "@ANNA")
        )
        self.assertFalse(Change(Outcome.NAME_TAKEN, "@anna").changes_list)

    def test_a_name_held_by_another_user_is_not_left(self):
        self.assertEqual(
            decide_leave(with_ids(("@anna", 7)), Person("@anna", 9)),
            Change(Outcome.NOT_IN, "@anna"),
        )


class TestAdd(unittest.TestCase):
    def test_a_new_name_is_added_with_the_name_as_typed(self):
        self.assertEqual(decide_add(match("anna"), "Bea"), Change(Outcome.ADDED, "Bea"))

    def test_a_confirmed_name_is_already_in_under_its_stored_name(self):
        self.assertEqual(
            decide_add(match("Anna", "bea", target=2), "ANNA"),
            Change(Outcome.ALREADY_IN, "Anna"),
        )

    def test_a_maybe_is_confirmed(self):
        self.assertEqual(
            decide_add(match("anna", "Bea?"), "bea"), Change(Outcome.CONFIRMED, "Bea")
        )

    def test_the_target_is_reached_by_a_new_name_or_a_confirmed_maybe(self):
        self.assertEqual(
            decide_add(match("a", "b", "c", target=4), "d"),
            Change(Outcome.ADDED, "d", reached_target=True),
        )
        self.assertEqual(
            decide_add(match("a", "b", "c?", target=3), "c"),
            Change(Outcome.CONFIRMED, "c", reached_target=True),
        )
        self.assertFalse(decide_add(match("a", target=4), "b").reached_target)
        self.assertFalse(
            decide_add(match("a", "b?", "c?", target=3), "b").reached_target
        )

    def test_full_counts_the_maybes_and_never_revokes_the_teams(self):
        m = match("a", "b?", target=2, teams=TEAMS)
        self.assertEqual(decide_add(m, "c"), Change(Outcome.FULL, "c"))
        m = match("a", "b?", "c", target=4, teams=TEAMS)
        self.assertFalse(decide_add(m, "b").revokes_teams)
        self.assertFalse(decide_add(m, "d").revokes_teams)

    def test_the_telegram_user_id_is_ignored(self):
        m = Match(1, [Participant("anna", False, 7)], target=4)
        self.assertEqual(decide_add(m, "ANNA"), Change(Outcome.ALREADY_IN, "anna"))


class TestPropose(unittest.TestCase):
    def test_a_new_name_is_proposed(self):
        self.assertEqual(
            decide_propose(match("anna"), "Bea"), Change(Outcome.PROPOSED, "Bea")
        )

    def test_a_maybe_is_already_maybe(self):
        self.assertEqual(
            decide_propose(match("anna", "Bea?", teams=TEAMS), "BEA"),
            Change(Outcome.ALREADY_MAYBE, "Bea"),
        )

    def test_a_confirmed_name_moves_to_maybe_and_revokes_the_teams(self):
        self.assertEqual(
            decide_propose(match("Anna", "bea", teams=TEAMS), "anna"),
            Change(Outcome.MOVED_TO_MAYBE, "Anna", revokes_teams=True),
        )
        self.assertEqual(
            decide_propose(match("Anna", "bea"), "anna"),
            Change(Outcome.MOVED_TO_MAYBE, "Anna"),
        )

    def test_a_new_name_revokes_the_teams_when_they_exist(self):
        self.assertEqual(
            decide_propose(match("anna", teams=TEAMS), "carlo"),
            Change(Outcome.PROPOSED, "carlo", revokes_teams=True),
        )

    def test_full_changes_nothing(self):
        self.assertEqual(
            decide_propose(match("a", "b?", target=2, teams=TEAMS), "c"),
            Change(Outcome.FULL, "c"),
        )


class TestRemove(unittest.TestCase):
    def test_a_confirmed_name_is_removed(self):
        self.assertEqual(
            decide_remove(match("Anna", "bea"), "ANNA"),
            Change(Outcome.REMOVED, "Anna"),
        )

    def test_a_maybe_is_removed(self):
        self.assertEqual(
            decide_remove(match("anna", "Bea?"), "bea"),
            Change(Outcome.REMOVED_MAYBE, "Bea"),
        )

    def test_removing_revokes_the_teams_when_they_exist(self):
        self.assertEqual(
            decide_remove(match("anna", "bea?", teams=TEAMS), "anna"),
            Change(Outcome.REMOVED, "anna", revokes_teams=True),
        )
        self.assertEqual(
            decide_remove(match("anna", "bea?", teams=TEAMS), "bea"),
            Change(Outcome.REMOVED_MAYBE, "bea", revokes_teams=True),
        )

    def test_an_unknown_name_is_not_in_and_revokes_nothing(self):
        self.assertEqual(
            decide_remove(match("anna", teams=TEAMS), "Zed"),
            Change(Outcome.NOT_IN, "Zed"),
        )

    def test_a_confirmed_row_wins_over_a_maybe_of_the_same_name(self):
        m = Match(1, [Participant("anna", True), Participant("Anna", False)], target=4)
        self.assertEqual(decide_remove(m, "anna"), Change(Outcome.REMOVED, "Anna"))
