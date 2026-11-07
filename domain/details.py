"""The rules of setting the day, time, pitch and description of a match, free of
storage and Telegram."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from domain.match import Match
from domain.schedule import parse_day, parse_time, with_day, with_time


class DetailOutcome(StrEnum):
    SET = "set"
    # nothing was written after the command
    MISSING = "missing"
    # day and time only: the text is not a date or a time
    UNREADABLE = "unreadable"


@dataclass(frozen=True)
class DetailResult:
    outcome: DetailOutcome
    # SET, day and time: the new start of the match
    starts: datetime | None = None
    # SET, pitch and description: the value to store
    value: str | None = None


def decide_day(match: Match, text: str) -> DetailResult:
    """`/setday <day>`: text is what follows the command, empty when nothing does."""
    if text == "":
        return DetailResult(DetailOutcome.MISSING)
    day = parse_day(text)
    if day is None:
        return DetailResult(DetailOutcome.UNREADABLE)
    return DetailResult(DetailOutcome.SET, starts=with_day(match.starts, day))


def decide_time(match: Match, text: str) -> DetailResult:
    """`/settime <time>`: text is what follows the command, empty when nothing does."""
    if text == "":
        return DetailResult(DetailOutcome.MISSING)
    at = parse_time(text)
    if at is None:
        return DetailResult(DetailOutcome.UNREADABLE)
    return DetailResult(DetailOutcome.SET, starts=with_time(match.starts, at))


def decide_pitch(text: str) -> DetailResult:
    """`/setpitch <pitch>`: text is what follows the command, empty when nothing does."""
    if text == "":
        return DetailResult(DetailOutcome.MISSING)
    return DetailResult(DetailOutcome.SET, value=text)


def decide_description(text: str) -> DetailResult:
    """`/setdescription <text>`: stored trimmed, ended by a newline; blank is missing."""
    text = text.strip()
    if text == "":
        return DetailResult(DetailOutcome.MISSING)
    return DetailResult(DetailOutcome.SET, value=text + "\n")
