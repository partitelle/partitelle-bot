"""The start, stop and setter use cases against the real test database."""

from datetime import datetime

from db.repository import get_match
from domain.details import DetailOutcome, DetailResult
from domain.lifecycle import StartResult
from domain.schedule import TIMEZONE
from usecases import details
from usecases.lifecycle import start_match, stop_match

from test_participation_usecases import CHAT, start


def test_start_creates_the_match_once(db):
    first = start_match(CHAT)
    assert first.created is True
    assert get_match(CHAT) is not None
    db.set_target(CHAT, 7)
    second = start_match(CHAT)
    assert second == StartResult(False, second.match)
    assert second.match.target == 7
    assert get_match(CHAT).target == 7


def test_start_gives_the_match_the_default_pitch_of_the_chat(db):
    db.set_default_pitch(CHAT, "Campo Rossi")
    assert start_match(CHAT).created is True
    assert get_match(CHAT).pitch == "Campo Rossi"


def test_stop_ends_the_match_and_only_once(db):
    assert stop_match(CHAT) is False
    start_match(CHAT)
    assert stop_match(CHAT) is True
    assert get_match(CHAT) is None
    assert stop_match(CHAT) is False


def test_a_stopped_chat_can_start_again(db):
    start_match(CHAT)
    stop_match(CHAT)
    assert start_match(CHAT).created is True


def test_no_active_match_means_none_for_every_setter(db):
    assert details.set_day(CHAT, "25/10/2026") is None
    assert details.set_time(CHAT, "21:30") is None
    assert details.set_pitch(CHAT, "Campo") is None
    assert details.set_description(CHAT, "ciao") is None
    assert get_match(CHAT) is None


def test_the_day_is_written_and_keeps_the_time(db):
    start(db, "anna")
    before = get_match(CHAT).starts
    result = details.set_day(CHAT, "25/10/2026")
    expected = datetime(2026, 10, 25, before.hour, before.minute, tzinfo=TIMEZONE)
    assert result == DetailResult(DetailOutcome.SET, starts=expected)
    assert get_match(CHAT).starts == expected


def test_the_time_is_written_and_keeps_the_day(db):
    start(db, "anna")
    before = get_match(CHAT).starts
    result = details.set_time(CHAT, "21:30")
    expected = datetime(before.year, before.month, before.day, 21, 30, tzinfo=TIMEZONE)
    assert result == DetailResult(DetailOutcome.SET, starts=expected)
    assert get_match(CHAT).starts == expected


def test_missing_and_unreadable_values_change_nothing(db):
    start(db, "anna")
    before = get_match(CHAT)
    assert details.set_day(CHAT, "") == DetailResult(DetailOutcome.MISSING)
    assert details.set_day(CHAT, "boh") == DetailResult(DetailOutcome.UNREADABLE)
    assert details.set_time(CHAT, "") == DetailResult(DetailOutcome.MISSING)
    assert details.set_time(CHAT, "sera") == DetailResult(DetailOutcome.UNREADABLE)
    assert details.set_pitch(CHAT, "") == DetailResult(DetailOutcome.MISSING)
    assert details.set_description(CHAT, " ") == DetailResult(DetailOutcome.MISSING)
    assert get_match(CHAT) == before


def test_pitch_and_description_are_written(db):
    start(db, "anna")
    assert details.set_pitch(CHAT, "Campo Rossi") == DetailResult(
        DetailOutcome.SET, value="Campo Rossi"
    )
    assert details.set_description(CHAT, "  porta il pallone ") == DetailResult(
        DetailOutcome.SET, value="porta il pallone\n"
    )
    match = get_match(CHAT)
    assert match.pitch == "Campo Rossi"
    assert match.description == "porta il pallone\n"
