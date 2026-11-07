"""Set the day, time, pitch or description of a match: the rules plus their storage
writes. Each returns None when the chat has no active match."""

from db import repository
from db.repository import get_match
from domain.details import (
    DetailOutcome,
    DetailResult,
    decide_day,
    decide_description,
    decide_pitch,
    decide_time,
)


def set_day(chat_id: int, text: str) -> DetailResult | None:
    match = get_match(chat_id)
    if match is None:
        return None
    result = decide_day(match, text)
    if result.outcome == DetailOutcome.SET:
        assert result.starts is not None
        repository.set_starts(chat_id, result.starts)
    return result


def set_time(chat_id: int, text: str) -> DetailResult | None:
    match = get_match(chat_id)
    if match is None:
        return None
    result = decide_time(match, text)
    if result.outcome == DetailOutcome.SET:
        assert result.starts is not None
        repository.set_starts(chat_id, result.starts)
    return result


def set_pitch(chat_id: int, text: str) -> DetailResult | None:
    if get_match(chat_id) is None:
        return None
    result = decide_pitch(text)
    if result.outcome == DetailOutcome.SET:
        assert result.value is not None
        repository.set_pitch(chat_id, result.value)
    return result


def set_description(chat_id: int, text: str) -> DetailResult | None:
    if get_match(chat_id) is None:
        return None
    result = decide_description(text)
    if result.outcome == DetailOutcome.SET:
        assert result.value is not None
        repository.set_description(chat_id, result.value)
    return result
