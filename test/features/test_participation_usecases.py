"""The join, maybe and leave use cases against the real test database."""

from db.repository import add_participant, create_match, get_match, save_teams
from domain import Match, Outcome, Participant, Person, Teams
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
    assert participation.join(CHAT, Person("anna")) is None
    assert participation.maybe(CHAT, Person("anna")) is None
    assert participation.leave(CHAT, Person("anna")) is None


def test_join_adds_and_confirms(db):
    start(db, "bea?")
    change = participation.join(CHAT, Person("anna"))
    assert change.outcome == Outcome.ADDED
    change = participation.join(CHAT, Person("bea"))
    assert change.outcome == Outcome.CONFIRMED
    assert stored() == {("anna", False), ("bea", False)}
    assert participation.join(CHAT, Person("anna")).outcome == Outcome.ALREADY_IN


def test_join_reaches_the_target_and_refuses_when_full(db):
    start(db, "anna", target=2)
    assert participation.join(CHAT, Person("bea")).reached_target is True
    assert participation.join(CHAT, Person("carlo")).outcome == Outcome.FULL
    assert stored() == {("anna", False), ("bea", False)}


def test_maybe_proposes_and_moves_and_revokes_the_teams(db):
    start(db, "anna", "bea", teams=Teams(("anna",), ("bea",)))
    change = participation.maybe(CHAT, Person("anna"))
    assert change.outcome == Outcome.MOVED_TO_MAYBE and change.revokes_teams
    assert get_match(CHAT).teams is None
    assert participation.maybe(CHAT, Person("carlo")).outcome == Outcome.PROPOSED
    assert participation.maybe(CHAT, Person("carlo")).outcome == Outcome.ALREADY_MAYBE
    assert stored() == {("anna", True), ("bea", False), ("carlo", True)}


def test_maybe_is_refused_when_full(db):
    start(db, "anna", "bea?", target=2)
    assert participation.maybe(CHAT, Person("carlo")).outcome == Outcome.FULL
    assert Participant("carlo", True) not in get_match(CHAT).participants


def test_leave_removes_and_revokes_the_teams(db):
    start(db, "anna", "bea?", "carlo", teams=Teams(("anna",), ("carlo",)))
    change = participation.leave(CHAT, Person("bea"))
    assert change.outcome == Outcome.REMOVED_MAYBE and change.revokes_teams
    assert get_match(CHAT).teams is None
    assert participation.leave(CHAT, Person("anna")).outcome == Outcome.REMOVED
    assert participation.leave(CHAT, Person("anna")).outcome == Outcome.NOT_IN
    assert stored() == {("carlo", False)}


def test_new_rows_store_the_user_id_and_names_added_by_others_do_not(db):
    start(db)
    participation.join(CHAT, Person("@anna", 7))
    participation.maybe(CHAT, Person("@bea", 8))
    add_participant(CHAT, Participant("luca"))
    assert get_match(CHAT).participants == [
        Participant("@anna", False, 7),
        Participant("@bea", True, 8),
        Participant("luca", False, None),
    ]


def test_a_person_is_found_by_user_id_after_a_username_change(db):
    start(db)
    participation.join(CHAT, Person("@old", 7))
    assert participation.join(CHAT, Person("@new", 7)).outcome == Outcome.ALREADY_IN
    change = participation.maybe(CHAT, Person("@new", 7))
    assert change.outcome == Outcome.MOVED_TO_MAYBE and change.name == "@old"
    assert get_match(CHAT).participants == [Participant("@old", True, 7)]
    change = participation.leave(CHAT, Person("@new", 7))
    assert change.outcome == Outcome.REMOVED_MAYBE
    assert get_match(CHAT).participants == []


def test_a_name_held_by_another_user_writes_nothing(db):
    start(db)
    participation.join(CHAT, Person("@anna", 7))
    assert participation.join(CHAT, Person("@anna", 9)).outcome == Outcome.NAME_TAKEN
    assert participation.maybe(CHAT, Person("@Anna", 9)).outcome == Outcome.NAME_TAKEN
    assert get_match(CHAT).participants == [Participant("@anna", False, 7)]


def test_create_match_keeps_the_user_ids(db):
    match = Match.new(CHAT)
    match.participants.append(Participant("@anna", False, 7))
    create_match(match)
    assert get_match(CHAT).participants == [Participant("@anna", False, 7)]
