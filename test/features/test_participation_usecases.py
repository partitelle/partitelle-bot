"""The join, maybe and leave use cases against the real test database."""

from db.repository import create_match, get_match, save_teams
from domain import Match, Outcome, Participant, Teams
from usecases import participation

CHAT = 4242


def start(db, *players, target=4, teams=None):
    create_match(Match.new(CHAT))
    db.set_target(CHAT, target)
    db.set_players(CHAT, [(p.rstrip("?"), p.endswith("?")) for p in players])
    if teams is not None:
        save_teams(CHAT, teams)


def stored():
    return {(p.name, p.is_maybe) for p in get_match(CHAT).participants}


def test_no_active_match_means_none(db):
    assert participation.join(CHAT, "anna") is None
    assert participation.maybe(CHAT, "anna") is None
    assert participation.leave(CHAT, "anna") is None


def test_join_adds_and_confirms(db):
    start(db, "bea?")
    change = participation.join(CHAT, "anna")
    assert change.outcome == Outcome.ADDED
    change = participation.join(CHAT, "bea")
    assert change.outcome == Outcome.CONFIRMED
    assert stored() == {("anna", False), ("bea", False)}
    assert participation.join(CHAT, "anna").outcome == Outcome.ALREADY_IN


def test_join_reaches_the_target_and_refuses_when_full(db):
    start(db, "anna", target=2)
    assert participation.join(CHAT, "bea").reached_target is True
    assert participation.join(CHAT, "carlo").outcome == Outcome.FULL
    assert stored() == {("anna", False), ("bea", False)}


def test_maybe_proposes_and_moves_and_revokes_the_teams(db):
    start(db, "anna", "bea", teams=Teams(("anna",), ("bea",)))
    change = participation.maybe(CHAT, "anna")
    assert change.outcome == Outcome.MOVED_TO_MAYBE and change.revokes_teams
    assert get_match(CHAT).teams is None
    assert participation.maybe(CHAT, "carlo").outcome == Outcome.PROPOSED
    assert participation.maybe(CHAT, "carlo").outcome == Outcome.ALREADY_MAYBE
    assert stored() == {("anna", True), ("bea", False), ("carlo", True)}


def test_maybe_is_refused_when_full(db):
    start(db, "anna", "bea?", target=2)
    assert participation.maybe(CHAT, "carlo").outcome == Outcome.FULL
    assert Participant("carlo", True) not in get_match(CHAT).participants


def test_leave_removes_and_revokes_the_teams(db):
    start(db, "anna", "bea?", "carlo", teams=Teams(("anna",), ("carlo",)))
    change = participation.leave(CHAT, "bea")
    assert change.outcome == Outcome.REMOVED_MAYBE and change.revokes_teams
    assert get_match(CHAT).teams is None
    assert participation.leave(CHAT, "anna").outcome == Outcome.REMOVED
    assert participation.leave(CHAT, "anna").outcome == Outcome.NOT_IN
    assert stored() == {("carlo", False)}
