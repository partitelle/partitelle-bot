"""Join, propose and leave the list of a chat: the rules plus their storage writes.

Every channel (the chat handler, the web endpoint) goes through these functions.
"""

from collections.abc import Callable

from db.repository import (
    add_participant,
    get_match,
    link_participant_user,
    remove_participant,
    save_teams,
    set_participant_maybe,
)
from domain import Actor, Change, Match, Outcome, Participant, Person
from domain.names import is_command_name
from domain.participation import (
    decide_add,
    decide_join,
    decide_leave,
    decide_maybe,
    decide_propose,
    decide_remove,
)


def _run(
    chat_id: int,
    person: Person,
    decide: Callable[[Match, Person], Change],
) -> Change | None:
    match = get_match(chat_id)
    if match is None:
        return None
    change = decide(match, person)
    _apply(chat_id, change, Actor.SELF)
    if change.revokes_teams:
        save_teams(chat_id, None)
    return change


def _apply(chat_id: int, change: Change, actor: Actor) -> None:
    name = change.name
    user_id = change.telegram_user_id
    match change.outcome:
        case Outcome.ADDED:
            add_participant(chat_id, Participant(name, False, user_id), actor=actor)
        case Outcome.CONFIRMED:
            set_participant_maybe(
                chat_id, name, False, actor=actor, telegram_user_id=user_id
            )
        case Outcome.PROPOSED:
            add_participant(chat_id, Participant(name, True, user_id), actor=actor)
        case Outcome.MOVED_TO_MAYBE:
            set_participant_maybe(
                chat_id, name, True, actor=actor, telegram_user_id=user_id
            )
        case Outcome.REMOVED:
            remove_participant(chat_id, Participant(name), actor=actor)
        case Outcome.REMOVED_MAYBE:
            remove_participant(chat_id, Participant(name, True), actor=actor)
        case Outcome.ALREADY_IN | Outcome.ALREADY_MAYBE if user_id:
            link_participant_user(chat_id, name, user_id, actor=actor)
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


def _run_names(
    chat_id: int,
    names: list[str],
    decide: Callable[[Match, str], Change],
) -> list[Change] | None:
    """One change per distinct name, in the order typed. The match is re-read before
    each name, so the earlier names count; the teams are revoked once, at the end."""
    if get_match(chat_id) is None:
        return None
    if any(is_command_name(name) for name in names):
        # a name cannot start with /: the whole batch is refused
        return []
    changes = []
    for name in dict.fromkeys(names):
        match = get_match(chat_id)
        if match is None:
            # stopped while the batch ran (no names in the message)
            raise LookupError("the match was stopped during the batch")
        change = decide(match, name)
        _apply(chat_id, change, Actor.OTHER)
        changes.append(change)
    if any(change.revokes_teams for change in changes):
        save_teams(chat_id, None)
    return changes


def add_names(chat_id: int, names: list[str]) -> list[Change] | None:
    """Confirm names added by someone else, one change per distinct name (matched by
    name, ignoring case). None when the chat has no active match; an empty list when a
    name starts with "/" (nothing is written)."""
    return _run_names(chat_id, names, decide_add)


def propose_names(chat_id: int, names: list[str]) -> list[Change] | None:
    """Put names in as maybes, same contract as `add_names`."""
    return _run_names(chat_id, names, decide_propose)


def remove_names(chat_id: int, names: list[str]) -> list[Change] | None:
    """Take names out of the list, same contract as `add_names`."""
    return _run_names(chat_id, names, decide_remove)


def remove_name(chat_id: int, name: str) -> Change | None:
    """Take a name out of the list; None when the chat has no active match."""
    match = get_match(chat_id)
    if match is None:
        return None
    change = decide_remove(match, name)
    _apply(chat_id, change, Actor.OTHER)
    if change.revokes_teams:
        save_teams(chat_id, None)
    return change
