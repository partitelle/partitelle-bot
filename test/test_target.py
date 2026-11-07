import unittest

from domain import Match, Participant, TargetTooLow, Teams
from domain.target import MAX_TARGET, TargetOutcome, TargetResult, decide_target

TEAMS = Teams(("anna",), ("bea",))


def match(*players, target=4, teams=None):
    """players are names; a trailing "?" marks a maybe."""
    participants = [Participant(p.rstrip("?"), p.endswith("?")) for p in players]
    return Match(chat_id=1, participants=participants, target=target, teams=teams)


class TestRange(unittest.TestCase):
    def test_zero_and_above_the_maximum_are_invalid(self):
        self.assertEqual(
            decide_target(match(target=6), 0),
            TargetResult(TargetOutcome.INVALID, 0, 6),
        )
        self.assertEqual(
            decide_target(match(target=6), MAX_TARGET + 1),
            TargetResult(TargetOutcome.INVALID, 41, 6),
        )
        self.assertEqual(
            decide_target(match(target=6), 1000),
            TargetResult(TargetOutcome.INVALID, 1000, 6),
        )

    def test_one_is_too_small(self):
        self.assertEqual(
            decide_target(match(target=6), 1),
            TargetResult(TargetOutcome.TOO_SMALL, 1, 6),
        )

    def test_both_bounds_are_accepted(self):
        self.assertEqual(
            decide_target(match(target=6), 2),
            TargetResult(TargetOutcome.SET, 2, 6),
        )
        self.assertEqual(
            decide_target(match(target=6), 40),
            TargetResult(TargetOutcome.SET, 40, 6),
        )
        self.assertEqual(MAX_TARGET, 40)

    def test_the_range_is_checked_before_the_list(self):
        self.assertEqual(
            decide_target(match("a", "b", "c", target=6), 1).outcome,
            TargetOutcome.TOO_SMALL,
        )
        self.assertEqual(
            decide_target(match("a", "b", "c", target=6), 0).outcome,
            TargetOutcome.INVALID,
        )


class TestTooLow(unittest.TestCase):
    def test_fewer_than_the_people_in_the_list_is_refused(self):
        result = decide_target(match("a", "b", "c?", "d?", target=6), 3)
        self.assertEqual(
            result,
            TargetResult(
                TargetOutcome.TOO_LOW,
                3,
                6,
                refusal=TargetTooLow(requested=3, confirmed=2, maybe=2),
            ),
        )
        self.assertFalse(result.revokes_teams)
        self.assertFalse(result.reached_target)

    def test_the_list_size_itself_is_accepted(self):
        self.assertEqual(
            decide_target(match("a", "b", "c?", target=6), 3).outcome,
            TargetOutcome.SET,
        )
        self.assertEqual(
            decide_target(match("a", "b", "c?", target=6), 2).outcome,
            TargetOutcome.TOO_LOW,
        )

    def test_a_refusal_keeps_the_teams(self):
        result = decide_target(match("a", "b", "c", target=4, teams=TEAMS), 2)
        self.assertEqual(result.outcome, TargetOutcome.TOO_LOW)
        self.assertFalse(result.revokes_teams)


class TestEffects(unittest.TestCase):
    def test_teams_are_cancelled_only_when_they_exist(self):
        self.assertEqual(
            decide_target(match("a", "b", target=4, teams=TEAMS), 6),
            TargetResult(TargetOutcome.SET, 6, 4, revokes_teams=True),
        )
        self.assertEqual(
            decide_target(match("a", "b", target=4), 6),
            TargetResult(TargetOutcome.SET, 6, 4),
        )

    def test_the_target_is_reached_by_exactly_the_confirmed_people(self):
        self.assertEqual(
            decide_target(match("a", "b", target=4), 2),
            TargetResult(TargetOutcome.SET, 2, 4, reached_target=True),
        )

    def test_not_reached_with_fewer_or_only_maybes(self):
        self.assertFalse(decide_target(match("a", target=4), 2).reached_target)
        # a maybe holds a place but is not confirmed
        self.assertFalse(decide_target(match("a", "b?", target=4), 2).reached_target)
        self.assertFalse(decide_target(match("a?", "b?", target=4), 2).reached_target)
        self.assertFalse(decide_target(match(target=4), 2).reached_target)

    def test_teams_and_reached_together(self):
        self.assertEqual(
            decide_target(match("a", "b", "c", target=6, teams=TEAMS), 3),
            TargetResult(
                TargetOutcome.SET, 3, 6, revokes_teams=True, reached_target=True
            ),
        )

    def test_the_same_target_again_is_still_a_change(self):
        self.assertEqual(
            decide_target(match("a", "b", target=2, teams=TEAMS), 2),
            TargetResult(
                TargetOutcome.SET, 2, 2, revokes_teams=True, reached_target=True
            ),
        )

    def test_refused_results_have_no_effects(self):
        for number in (0, 1, 41):
            result = decide_target(match("a", "b", target=2, teams=TEAMS), number)
            self.assertFalse(result.revokes_teams)
            self.assertFalse(result.reached_target)
