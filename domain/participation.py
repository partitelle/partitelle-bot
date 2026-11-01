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
    # the name is on the list under another Telegram user (a username that changed
    # hands): nothing is written, as the name unique index would reject the row
    NAME_TAKEN = "name_taken"


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
class Person:
    """Who is acting on themselves: the name they are listed under and, when known,
    their Telegram user id (the stable identity: names change)."""

    name: str
    telegram_user_id: int | None = None


def display_name(
    username: str | None, first_name: str | None, last_name: str | None
) -> str | None:
    """`@username` lowercased, else the first and last names, else None."""
    if username:
        return "@" + username.lower()
    return " ".join(part for part in (first_name, last_name) if part) or None


@dataclass(frozen=True)
class Change:
    outcome: Outcome
    # the stored name for an existing row, the person's name for a new one
    name: str
    reached_target: bool = False
    revokes_teams: bool = False
    # the person's id, for the rows being created (ADDED, PROPOSED)
    telegram_user_id: int | None = None

    @property
    def changes_list(self) -> bool:
        """Whether the list changed, so the summary must be refreshed."""
        return self.outcome in _CHANGES_LIST


def decide_join(match: Match, person: Person) -> Change:
    found = match.find_person(person)
    if found is not None and not found.is_maybe:
        return Change(Outcome.ALREADY_IN, found.name)
    reached = match.confirmed_count + 1 == match.target
    if found is not None:
        return Change(Outcome.CONFIRMED, found.name, reached_target=reached)
    if match.name_taken_by_other(person):
        return Change(Outcome.NAME_TAKEN, person.name)
    if match.has_room:
        return Change(
            Outcome.ADDED,
            person.name,
            reached_target=reached,
            telegram_user_id=person.telegram_user_id,
        )
    return Change(Outcome.FULL, person.name)


def decide_maybe(match: Match, person: Person) -> Change:
    revokes = match.teams is not None
    found = match.find_person(person)
    if found is not None and found.is_maybe:
        return Change(Outcome.ALREADY_MAYBE, found.name)
    if found is not None:
        return Change(Outcome.MOVED_TO_MAYBE, found.name, revokes_teams=revokes)
    if match.name_taken_by_other(person):
        return Change(Outcome.NAME_TAKEN, person.name)
    if match.has_room:
        return Change(
            Outcome.PROPOSED,
            person.name,
            revokes_teams=revokes,
            telegram_user_id=person.telegram_user_id,
        )
    return Change(Outcome.FULL, person.name)


def decide_leave(match: Match, person: Person) -> Change:
    revokes = match.teams is not None
    found = match.find_person(person)
    if found is None:
        return Change(Outcome.NOT_IN, person.name)
    outcome = Outcome.REMOVED_MAYBE if found.is_maybe else Outcome.REMOVED
    return Change(outcome, found.name, revokes_teams=revokes)
