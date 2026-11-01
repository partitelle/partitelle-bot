"""When the payment reminder of a match is due: a rule on what is stored, not on a timer."""

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta

from domain.schedule import TIMEZONE

REMINDER_HOUR = time(8, 0)


@dataclass(frozen=True)
class ReminderCandidate:
    """A match that has no reminder yet, as stored."""

    match_uuid: str
    chat_id: int
    starts: datetime
    confirmed: int
    target: int


def reminder_window(now: datetime) -> tuple[datetime, datetime]:
    """[start, end) of the matches to remind, as UTC instants.

    The end is the most recent 08:00 Europe/Rome at or before `now`, the start is 08:00 of
    the day before. Both are built from the local wall time, so a day that changes DST
    is 23 or 25 hours long and the window follows it.
    """
    local = now.astimezone(TIMEZONE)
    end_day = (
        local.date()
        if local.time() >= REMINDER_HOUR
        else local.date() - timedelta(days=1)
    )
    end = datetime.combine(end_day, REMINDER_HOUR, tzinfo=TIMEZONE)
    start = datetime.combine(
        end_day - timedelta(days=1), REMINDER_HOUR, tzinfo=TIMEZONE
    )
    return start.astimezone(UTC), end.astimezone(UTC)


def is_reminder_due(
    starts: datetime,
    confirmed: int,
    target: int,
    reminder_sent: datetime | None,
    now: datetime,
) -> bool:
    """On (enough confirmed players), started inside the window and not reminded yet.

    /stop is deliberately not an input: a group that stops after the match is still reminded.
    """
    start, end = reminder_window(now)
    return (
        confirmed >= target
        and reminder_sent is None
        and start <= starts.astimezone(UTC) < end
    )
