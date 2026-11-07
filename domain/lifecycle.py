"""Starting and stopping a match, free of storage and Telegram."""

from dataclasses import dataclass

from domain.match import Match


@dataclass(frozen=True)
class StartResult:
    # False when the chat already had an active match: /start leaves it untouched
    created: bool
    # the match to store when created, else the existing one
    match: Match


def decide_start(chat_id: int, existing: Match | None) -> StartResult:
    """/start: a chat has at most one active match, so an existing one is kept."""
    if existing is not None:
        return StartResult(False, existing)
    return StartResult(True, Match.new(chat_id))


def decide_stop(existing: Match | None) -> bool:
    """/stop: only an active match can be stopped."""
    return existing is not None
