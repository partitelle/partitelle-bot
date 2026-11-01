"""Join, propose and leave the list of a chat: the rules plus their storage writes.

Every channel (the chat handler, the web endpoint) goes through these functions.
"""

from collections.abc import Callable

from db.repository import (
    add_participant,
    get_match,
    remove_participant,
    save_teams,
    set_participant_maybe,
)
from domain import Change, Match, Outcome, Participant, Person
from domain.participation import decide_join, decide_leave, decide_maybe


def _run(
    chat_id: int,
    person: Person,
    decide: Callable[[Match, Person], Change],
) -> Change | None:
    match = get_match(chat_id)
    if match is None:
        return None
    change = decide(match, person)
    _apply(chat_id, change)
    if change.revokes_teams:
        save_teams(chat_id, None)
    return change


def _apply(chat_id: int, change: Change) -> None:
    name = change.name
    match change.outcome:
        case Outcome.ADDED:
            add_participant(chat_id, Participant(name, False, change.telegram_user_id))
        case Outcome.CONFIRMED:
            set_participant_maybe(chat_id, name, False)
        case Outcome.PROPOSED:
            add_participant(chat_id, Participant(name, True, change.telegram_user_id))
        case Outcome.MOVED_TO_MAYBE:
            set_participant_maybe(chat_id, name, True)
        case Outcome.REMOVED:
            remove_participant(chat_id, Participant(name))
        case Outcome.REMOVED_MAYBE:
            remove_participant(chat_id, Participant(name, True))
        case _:
            pass


def join(chat_id: int, person: Person) -> Change | None:
    """Confirm the person; None when the chat has no active match."""
    return _run(chat_id, person, decide_join)


def maybe(chat_id: int, person: Person) -> Change | None:
    """Put the person in the list as a maybe; None when the chat has no active match."""
    return _run(chat_id, person, decide_maybe)


def leave(chat_id: int, person: Person) -> Change | None:
    """Take the person out of the list; None when the chat has no active match."""
    return _run(chat_id, person, decide_leave)
