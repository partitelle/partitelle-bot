"""The rules of joining, proposing and leaving the list, free of storage and Telegram."""

from dataclasses import dataclass
from enum import StrEnum

from domain.match import Match


class Outcome(StrEnum):
    ADDED = "added"
    CONFIRMED = "confirmed"
    ALREADY_IN = "already_in"
    PROPOSED = "proposed"
    MOVED_TO_MAYBE = "moved_to_maybe"
    ALREADY_MAYBE = "already_maybe"
    REMOVED = "removed"
    REMOVED_MAYBE = "removed_maybe"
    NOT_IN = "not_in"
    FULL = "full"


_CHANGES_LIST = frozenset(
    {
        Outcome.ADDED,
        Outcome.CONFIRMED,
        Outcome.PROPOSED,
        Outcome.MOVED_TO_MAYBE,
        Outcome.REMOVED,
        Outcome.REMOVED_MAYBE,
    }
)


@dataclass(frozen=True)
class Change:
    outcome: Outcome
    name: str
    reached_target: bool = False
    revokes_teams: bool = False

    @property
    def changes_list(self) -> bool:
        """Whether the list changed, so the summary must be refreshed."""
        return self.outcome in _CHANGES_LIST


def decide_join(match: Match, name: str) -> Change:
    if match.find(name, False):
        return Change(Outcome.ALREADY_IN, name)
    reached = match.confirmed_count + 1 == match.target
    if match.find(name, True):
        return Change(Outcome.CONFIRMED, name, reached_target=reached)
    if match.has_room:
        return Change(Outcome.ADDED, name, reached_target=reached)
    return Change(Outcome.FULL, name)


def decide_maybe(match: Match, name: str) -> Change:
    revokes = match.teams is not None
    if match.find(name, True):
        return Change(Outcome.ALREADY_MAYBE, name)
    if match.find(name, False):
        return Change(Outcome.MOVED_TO_MAYBE, name, revokes_teams=revokes)
    if match.has_room:
        return Change(Outcome.PROPOSED, name, revokes_teams=revokes)
    return Change(Outcome.FULL, name)


def decide_leave(match: Match, name: str) -> Change:
    revokes = match.teams is not None
    if match.find(name, False):
        return Change(Outcome.REMOVED, name, revokes_teams=revokes)
    if match.find(name, True):
        return Change(Outcome.REMOVED_MAYBE, name, revokes_teams=revokes)
    return Change(Outcome.NOT_IN, name)
