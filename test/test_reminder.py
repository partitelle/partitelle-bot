import unittest
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from domain import is_reminder_due, reminder_window

ROME = ZoneInfo("Europe/Rome")


def rome(*args: int) -> datetime:
    return datetime(*args, tzinfo=ROME)


class TestReminderWindow(unittest.TestCase):
    def assertWindow(self, now, start, end):
        window = reminder_window(now)
        self.assertEqual(window, (start, end))
        self.assertEqual(window[0].utcoffset(), timedelta(0))  # UTC instants

    def test_after_eight_the_window_ends_today_at_eight(self):
        self.assertWindow(
            rome(2026, 10, 21, 9, 30), rome(2026, 10, 20, 8), rome(2026, 10, 21, 8)
        )

    def test_exactly_at_eight_the_window_ends_now(self):
        self.assertWindow(
            rome(2026, 10, 21, 8, 0), rome(2026, 10, 20, 8), rome(2026, 10, 21, 8)
        )

    def test_before_eight_the_window_is_the_previous_one(self):
        self.assertWindow(
            rome(2026, 10, 21, 7, 30), rome(2026, 10, 19, 8), rome(2026, 10, 20, 8)
        )

    def test_the_run_time_zone_does_not_matter(self):
        now = datetime(2026, 10, 21, 6, 30, tzinfo=UTC)  # 08:30 in Rome (CEST)
        self.assertWindow(now, rome(2026, 10, 20, 8), rome(2026, 10, 21, 8))

    def test_the_day_that_ends_daylight_saving_time_is_25_hours_long(self):
        start, end = reminder_window(
            rome(2026, 10, 26, 9)
        )  # clocks went back on the 25th
        self.assertEqual(end - start, timedelta(hours=24))
        start, end = reminder_window(rome(2026, 10, 25, 9))
        self.assertEqual(end - start, timedelta(hours=25))
        self.assertEqual(start, datetime(2026, 10, 24, 6, 0, tzinfo=UTC))  # 08:00 CEST
        self.assertEqual(end, datetime(2026, 10, 25, 7, 0, tzinfo=UTC))  # 08:00 CET

    def test_the_day_that_starts_daylight_saving_time_is_23_hours_long(self):
        start, end = reminder_window(rome(2026, 3, 29, 9))
        self.assertEqual(end - start, timedelta(hours=23))
        self.assertEqual(start, datetime(2026, 3, 28, 7, 0, tzinfo=UTC))  # 08:00 CET
        self.assertEqual(end, datetime(2026, 3, 29, 6, 0, tzinfo=UTC))  # 08:00 CEST


class TestIsReminderDue(unittest.TestCase):
    now = rome(2026, 10, 21, 9)
    starts = rome(2026, 10, 20, 21)

    def due(self, starts=None, confirmed=10, target=10, sent=None):
        return is_reminder_due(starts or self.starts, confirmed, target, sent, self.now)

    def test_a_full_match_of_yesterday_is_due(self):
        self.assertTrue(self.due())

    def test_more_confirmed_players_than_the_target_is_on(self):
        self.assertTrue(self.due(confirmed=12))

    def test_an_incomplete_match_is_not_due(self):
        self.assertFalse(self.due(confirmed=9))

    def test_a_match_already_reminded_is_not_due(self):
        self.assertFalse(self.due(sent=self.now))

    def test_start_is_inclusive_and_end_is_exclusive(self):
        self.assertTrue(self.due(starts=rome(2026, 10, 20, 8, 0)))
        self.assertFalse(self.due(starts=rome(2026, 10, 20, 7, 59)))
        self.assertTrue(self.due(starts=rome(2026, 10, 21, 7, 59)))
        self.assertFalse(self.due(starts=rome(2026, 10, 21, 8, 0)))

    def test_a_run_before_eight_reminds_the_matches_of_the_day_before_yesterday(self):
        early = rome(2026, 10, 21, 7, 30)
        args = (10, 10, None, early)
        self.assertTrue(is_reminder_due(rome(2026, 10, 19, 21), *args))
        self.assertFalse(is_reminder_due(rome(2026, 10, 20, 21), *args))

    def test_the_comparison_is_by_instant_on_a_daylight_saving_day(self):
        # the window of the 26th starts at 08:00 CET (07:00 UTC) of the day clocks went back
        now = rome(2026, 10, 26, 9)
        self.assertTrue(
            is_reminder_due(datetime(2026, 10, 25, 7, 0, tzinfo=UTC), 10, 10, None, now)
        )
        self.assertFalse(
            is_reminder_due(
                datetime(2026, 10, 25, 6, 59, tzinfo=UTC), 10, 10, None, now
            )
        )


if __name__ == "__main__":
    unittest.main()
