import unittest
from unittest.mock import patch

from domain import Match, Participant, Teams
from domain.teams import (
    SwapOutcome,
    SwapResult,
    TeamsOutcome,
    TeamsResult,
    decide_swap,
    decide_teams,
    generate_teams,
    swap_players,
)


def match(*players, target=4, teams=None):
    """players are names; a trailing "?" marks a maybe."""
    participants = [Participant(p.rstrip("?"), p.endswith("?")) for p in players]
    return Match(chat_id=1, participants=participants, target=target, teams=teams)


class TestSwapPlayers(unittest.TestCase):
    def test_swap_players(self):
        teams = Teams(("JohnDoe", "JaneDoe", "Alice"), ("Bob", "Charlie", "Eve"))
        new_teams = swap_players(teams, "JohnDoe", "Bob")
        self.assertEqual(
            new_teams,
            Teams(("Bob", "JaneDoe", "Alice"), ("JohnDoe", "Charlie", "Eve")),
        )
        # the swap is the same whichever player is named first
        self.assertEqual(swap_players(teams, "Bob", "JohnDoe"), new_teams)
        with self.assertRaises(ValueError):
            swap_players(teams, "JohnDoe", "JaneDoe")

    def test_swap_players_ignores_case_and_keeps_the_stored_names(self):
        teams = Teams(("Anna", "bea"), ("Carlo", "dino"))
        self.assertEqual(
            swap_players(teams, "anna", "CARLO"),
            Teams(("Carlo", "bea"), ("Anna", "dino")),
        )
        with self.assertRaises(ValueError):
            swap_players(teams, "ANNA", "bea")

    def test_swap_players_refuses_a_player_outside_the_teams(self):
        teams = Teams(("anna", "bea"), ("carlo", "dino"))
        for x, y in [("anna", "enzo"), ("enzo", "carlo")]:
            with self.assertRaises(ValueError):
                swap_players(teams, x, y)
        self.assertEqual(teams, Teams(("anna", "bea"), ("carlo", "dino")))

    @patch("domain.teams.random.sample")
    def test_generate_teams(self, mock_sample):
        players = ["JohnDoe", "JaneDoe", "Alice", "Bob", "Charlie", "Eve"]
        mock_sample.return_value = ["JohnDoe", "JaneDoe", "Alice"]
        self.assertEqual(
            generate_teams(players),
            Teams(("JohnDoe", "JaneDoe", "Alice"), ("Bob", "Charlie", "Eve")),
        )
        mock_sample.assert_called_once_with(players, 3)


TEAMS = Teams(("Anna", "bea"), ("carlo", "dino"))
FOUR = ("Anna", "bea", "carlo", "dino")


class TestDecideSwap(unittest.TestCase):
    def test_no_teams(self):
        self.assertEqual(
            decide_swap(match(*FOUR), "anna", "carlo"),
            SwapResult(SwapOutcome.NO_TEAMS, "anna", "carlo"),
        )

    def test_a_player_in_no_team_is_reported_first_x_then_y(self):
        m = match("Anna", "bea", "carlo", "dino", "enzo?", target=5, teams=TEAMS)
        self.assertEqual(
            decide_swap(m, "zed", "yan"),
            SwapResult(SwapOutcome.NOT_IN_TEAMS, "zed", "yan", missing="zed"),
        )
        self.assertEqual(
            decide_swap(m, "anna", "yan"),
            SwapResult(SwapOutcome.NOT_IN_TEAMS, "anna", "yan", missing="yan"),
        )

    def test_a_confirmed_player_outside_the_teams_is_told_apart(self):
        m = match(
            "Anna", "bea", "carlo", "dino", "enzo", "fido?", target=6, teams=TEAMS
        )
        self.assertEqual(
            decide_swap(m, "ENZO", "anna"),
            SwapResult(
                SwapOutcome.NOT_IN_TEAMS,
                "ENZO",
                "anna",
                missing="ENZO",
                missing_is_confirmed=True,
            ),
        )
        # a maybe is not in a team and is not a confirmed participant
        self.assertEqual(
            decide_swap(m, "anna", "fido"),
            SwapResult(
                SwapOutcome.NOT_IN_TEAMS,
                "anna",
                "fido",
                missing="fido",
                missing_is_confirmed=False,
            ),
        )

    def test_the_same_team(self):
        self.assertEqual(
            decide_swap(match(*FOUR, teams=TEAMS), "ANNA", "Bea"),
            SwapResult(
                SwapOutcome.SAME_TEAM,
                "ANNA",
                "Bea",
                stored_x="Anna",
                stored_y="bea",
            ),
        )

    def test_the_existence_check_comes_before_the_same_team_check(self):
        result = decide_swap(match(*FOUR, teams=TEAMS), "anna", "zed")
        self.assertEqual(result.outcome, SwapOutcome.NOT_IN_TEAMS)
        self.assertEqual(result.missing, "zed")

    def test_swapped(self):
        self.assertEqual(
            decide_swap(match(*FOUR, teams=TEAMS), "ANNA", "Carlo"),
            SwapResult(
                SwapOutcome.SWAPPED,
                "ANNA",
                "Carlo",
                teams=Teams(("carlo", "bea"), ("Anna", "dino")),
                stored_x="Anna",
                stored_y="carlo",
            ),
        )


def fake_draw(names):
    return Teams(tuple(names[:2]), tuple(names[2:]))


def no_draw(names):
    raise AssertionError("the teams must not be drawn")


class TestDecideTeams(unittest.TestCase):
    def test_no_match(self):
        self.assertEqual(
            decide_teams(None, no_draw), TeamsResult(TeamsOutcome.NO_MATCH)
        )

    def test_existing_teams_are_shown_again_whatever_the_rest(self):
        # odd target and not full: the existing teams still win
        m = match("a", "b", target=3, teams=TEAMS)
        self.assertEqual(
            decide_teams(m, no_draw),
            TeamsResult(TeamsOutcome.SHOW_EXISTING, 3, TEAMS),
        )

    def test_odd_target_comes_before_not_full(self):
        self.assertEqual(
            decide_teams(match("a", target=5), no_draw),
            TeamsResult(TeamsOutcome.ODD_TARGET, 5),
        )

    def test_not_full(self):
        self.assertEqual(
            decide_teams(match("a", "b", "c", target=4), no_draw),
            TeamsResult(TeamsOutcome.NOT_FULL, 4),
        )
        # maybes do not count, and neither does an empty list
        self.assertEqual(
            decide_teams(match("a", "b", "c", "d?", target=4), no_draw).outcome,
            TeamsOutcome.NOT_FULL,
        )
        self.assertEqual(
            decide_teams(match(target=4), no_draw).outcome, TeamsOutcome.NOT_FULL
        )

    def test_drawn_with_the_confirmed_names_only(self):
        seen = []

        def draw(names):
            seen.append(names)
            return fake_draw(names)

        m = match("a", "b", "c", "d", target=4)
        self.assertEqual(
            decide_teams(m, draw),
            TeamsResult(TeamsOutcome.DRAWN, 4, Teams(("a", "b"), ("c", "d"))),
        )
        self.assertEqual(seen, [["a", "b", "c", "d"]])

    def test_a_target_of_zero_with_people_is_not_drawn(self):
        self.assertEqual(
            decide_teams(match("a", target=0), no_draw).outcome,
            TeamsOutcome.NOT_FULL,
        )
