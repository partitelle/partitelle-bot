import unittest

from domain import Match, Participant, Teams
from domain.participation import (
    Change,
    Outcome,
    decide_join,
    decide_leave,
    decide_maybe,
)

TEAMS = Teams(("anna",), ("bea",))


def match(*players, target=4, teams=None):
    """players are names; a trailing "?" marks a maybe."""
    participants = [Participant(p.rstrip("?"), p.endswith("?")) for p in players]
    return Match(chat_id=1, participants=participants, target=target, teams=teams)


class TestJoin(unittest.TestCase):
    def test_a_new_name_is_added(self):
        self.assertEqual(
            decide_join(match("anna"), "bea"), Change(Outcome.ADDED, "bea")
        )

    def test_a_confirmed_name_is_already_in_even_when_full(self):
        m = match("anna", "bea", target=2)
        self.assertEqual(decide_join(m, "Anna"), Change(Outcome.ALREADY_IN, "Anna"))

    def test_a_maybe_is_confirmed(self):
        self.assertEqual(
            decide_join(match("anna", "bea?"), "bea"), Change(Outcome.CONFIRMED, "bea")
        )

    def test_a_maybe_is_confirmed_even_when_the_list_is_full(self):
        m = match("anna", "bea?", target=2)
        self.assertEqual(decide_join(m, "BEA").outcome, Outcome.CONFIRMED)

    def test_the_target_is_reached_at_the_boundary_only(self):
        self.assertFalse(decide_join(match("a", "b", target=4), "c").reached_target)
        self.assertTrue(decide_join(match("a", "b", "c", target=4), "d").reached_target)
        self.assertTrue(
            decide_join(match("a", "b", "c?", target=3), "c").reached_target
        )
        self.assertFalse(
            decide_join(match("a", "b?", "c?", target=3), "b").reached_target
        )

    def test_maybe_participants_hold_a_place(self):
        full = match("a", "b?", target=2)
        self.assertEqual(decide_join(full, "c"), Change(Outcome.FULL, "c"))

    def test_joining_never_revokes_the_teams(self):
        m = match("anna", "bea?", teams=TEAMS)
        self.assertFalse(decide_join(m, "bea").revokes_teams)
        self.assertFalse(decide_join(m, "carlo").revokes_teams)


class TestMaybe(unittest.TestCase):
    def test_a_new_name_is_proposed(self):
        self.assertEqual(
            decide_maybe(match("anna"), "bea"), Change(Outcome.PROPOSED, "bea")
        )

    def test_a_maybe_is_already_maybe_even_when_full(self):
        m = match("anna", "bea?", target=2, teams=TEAMS)
        self.assertEqual(decide_maybe(m, "Bea"), Change(Outcome.ALREADY_MAYBE, "Bea"))

    def test_a_confirmed_name_moves_to_maybe(self):
        self.assertEqual(
            decide_maybe(match("anna"), "ANNA"), Change(Outcome.MOVED_TO_MAYBE, "ANNA")
        )

    def test_a_full_list_refuses_a_new_maybe(self):
        self.assertEqual(
            decide_maybe(match("a", "b?", target=2, teams=TEAMS), "c"),
            Change(Outcome.FULL, "c"),
        )

    def test_the_teams_are_revoked_only_when_the_list_changes(self):
        with_teams = match("anna", "carlo?", teams=TEAMS)
        self.assertTrue(decide_maybe(with_teams, "anna").revokes_teams)
        self.assertTrue(decide_maybe(with_teams, "bea").revokes_teams)
        self.assertFalse(decide_maybe(with_teams, "carlo").revokes_teams)
        self.assertFalse(decide_maybe(match("anna"), "anna").revokes_teams)
        self.assertFalse(decide_maybe(match("anna"), "bea").revokes_teams)

    def test_the_target_is_never_reached(self):
        self.assertFalse(decide_maybe(match("a", "b", "c"), "d").reached_target)


class TestLeave(unittest.TestCase):
    def test_a_confirmed_name_is_removed(self):
        self.assertEqual(
            decide_leave(match("anna"), "Anna"), Change(Outcome.REMOVED, "Anna")
        )

    def test_a_maybe_is_removed(self):
        self.assertEqual(
            decide_leave(match("anna?"), "anna"), Change(Outcome.REMOVED_MAYBE, "anna")
        )

    def test_an_unknown_name_is_not_in(self):
        self.assertEqual(
            decide_leave(match("anna", teams=TEAMS), "carlo"),
            Change(Outcome.NOT_IN, "carlo"),
        )

    def test_the_teams_are_revoked_by_the_two_removals_only(self):
        self.assertTrue(decide_leave(match("anna", teams=TEAMS), "anna").revokes_teams)
        self.assertTrue(decide_leave(match("anna?", teams=TEAMS), "anna").revokes_teams)
        self.assertFalse(decide_leave(match("anna"), "anna").revokes_teams)
        self.assertFalse(decide_leave(match("anna", teams=TEAMS), "bea").revokes_teams)


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
