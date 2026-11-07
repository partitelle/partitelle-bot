import unittest

from domain import Match, Participant
from domain.lifecycle import StartResult, decide_start, decide_stop


class TestStart(unittest.TestCase):
    def test_a_chat_without_a_match_gets_a_new_one_with_no_pitch(self):
        result = decide_start(7, None)
        self.assertTrue(result.created)
        self.assertEqual(result.match.chat_id, 7)
        self.assertIsNone(result.match.pitch)
        self.assertEqual(result.match.participants, [])
        self.assertIsNone(result.match.teams)

    def test_an_existing_match_is_kept_as_it_is(self):
        existing = Match(chat_id=7, participants=[Participant("anna")], target=6)
        result = decide_start(7, existing)
        self.assertEqual(result, StartResult(False, existing))
        self.assertIs(result.match, existing)
        self.assertEqual(existing.target, 6)


class TestStop(unittest.TestCase):
    def test_only_an_active_match_can_be_stopped(self):
        self.assertTrue(decide_stop(Match(chat_id=7)))
        self.assertFalse(decide_stop(None))


if __name__ == "__main__":
    unittest.main()
