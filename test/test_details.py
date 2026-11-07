import unittest
from datetime import datetime

from domain import Match
from domain.details import (
    DetailOutcome,
    DetailResult,
    decide_day,
    decide_description,
    decide_pitch,
    decide_time,
)
from domain.schedule import TIMEZONE

STARTS = datetime(2026, 10, 28, 20, 0, tzinfo=TIMEZONE)
MATCH = Match(chat_id=1, starts=STARTS)
MISSING = DetailResult(DetailOutcome.MISSING)
UNREADABLE = DetailResult(DetailOutcome.UNREADABLE)


class TestDay(unittest.TestCase):
    def test_a_day_keeps_the_time(self):
        self.assertEqual(
            decide_day(MATCH, "25/10/2026"),
            DetailResult(
                DetailOutcome.SET,
                starts=datetime(2026, 10, 25, 20, 0, tzinfo=TIMEZONE),
            ),
        )

    def test_nothing_written_is_missing(self):
        self.assertEqual(decide_day(MATCH, ""), MISSING)

    def test_an_unreadable_day_is_refused(self):
        self.assertEqual(decide_day(MATCH, "boh"), UNREADABLE)


class TestTime(unittest.TestCase):
    def test_a_time_keeps_the_day(self):
        self.assertEqual(
            decide_time(MATCH, "21:30"),
            DetailResult(
                DetailOutcome.SET,
                starts=datetime(2026, 10, 28, 21, 30, tzinfo=TIMEZONE),
            ),
        )

    def test_a_bare_hour_is_accepted(self):
        self.assertEqual(
            decide_time(MATCH, "19").starts,
            datetime(2026, 10, 28, 19, 0, tzinfo=TIMEZONE),
        )

    def test_nothing_written_is_missing(self):
        self.assertEqual(decide_time(MATCH, ""), MISSING)

    def test_an_unreadable_time_is_refused(self):
        self.assertEqual(decide_time(MATCH, "sera"), UNREADABLE)


class TestPitch(unittest.TestCase):
    def test_the_pitch_is_stored_as_written(self):
        self.assertEqual(
            decide_pitch("Campo Rossi, via Roma"),
            DetailResult(DetailOutcome.SET, value="Campo Rossi, via Roma"),
        )

    def test_nothing_written_is_missing(self):
        self.assertEqual(decide_pitch(""), MISSING)


class TestDescription(unittest.TestCase):
    def test_the_description_is_trimmed_and_ends_with_a_newline(self):
        self.assertEqual(
            decide_description("  porta una maglia \n"),
            DetailResult(DetailOutcome.SET, value="porta una maglia\n"),
        )

    def test_inner_lines_are_kept(self):
        self.assertEqual(
            decide_description("riga 1\n\nriga  2").value, "riga 1\n\nriga  2\n"
        )

    def test_blank_is_missing(self):
        self.assertEqual(decide_description(""), MISSING)
        self.assertEqual(decide_description(" \n "), MISSING)


if __name__ == "__main__":
    unittest.main()
