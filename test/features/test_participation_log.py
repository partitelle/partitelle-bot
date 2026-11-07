# ruff: noqa: F811
"""The participation log: every change of the list is recorded, in the transaction of the change."""

import psycopg
import pytest

from db import repository
from db.repository import (
    add_participant,
    get_match,
    remove_participant,
    save_teams,
    set_participant_maybe,
)
from domain import Actor, Participant, Person, Teams
from domain.teams import SwapOutcome
from usecases import participation
from usecases import teams as teams_usecase

from test_miniapp_api import env, enabled  # noqa: F401  (fixtures)
from test_participation_usecases import CHAT, start

SELF, OTHER = "self", "other"


def events(db):
    """(action, actor, name, Telegram user id, team) of the whole log, oldest first."""
    return [row[:5] for row in db.fetch_events(CHAT)]


def test_a_new_person_joining_logs_added_by_self(db):
    start(db)
    participation.join(CHAT, Person("@anna", 7))
    assert events(db) == [("added", SELF, "@anna", 7, None)]
    assert [row[5] for row in db.fetch_events(CHAT)] == [
        db.fetch_participant_uuids(CHAT)["@anna"]
    ]


def test_a_new_person_saying_maybe_logs_proposed_by_self(db):
    start(db)
    participation.maybe(CHAT, Person("@anna", 7))
    assert events(db) == [("proposed", SELF, "@anna", 7, None)]


def test_confirming_and_flipping_to_maybe_log_the_row_id(db):
    start(db)
    participation.maybe(CHAT, Person("@anna", 7))
    participation.join(CHAT, Person("@anna", 7))
    participation.maybe(CHAT, Person("@anna", 7))
    assert events(db) == [
        ("proposed", SELF, "@anna", 7, None),
        ("confirmed", SELF, "@anna", 7, None),
        ("moved_to_maybe", SELF, "@anna", 7, None),
    ]
    assert {row[5] for row in db.fetch_events(CHAT)} == {
        db.fetch_participant_uuids(CHAT)["@anna"]
    }


def test_leaving_logs_the_removed_row_and_its_uuid(db):
    start(db)
    participation.join(CHAT, Person("@anna", 7))
    participation.maybe(CHAT, Person("@bea", 8))
    uuids = db.fetch_participant_uuids(CHAT)
    participation.leave(CHAT, Person("@anna", 7))
    participation.leave(CHAT, Person("@bea", 8))
    assert get_match(CHAT).participants == []
    assert db.fetch_events(CHAT)[2:] == [
        ("removed", SELF, "@anna", 7, None, uuids["@anna"]),
        ("removed_maybe", SELF, "@bea", 8, None, uuids["@bea"]),
    ]


def test_leaving_a_row_without_an_id_does_not_log_the_id_of_the_person_leaving(db):
    start(db)
    participation.add_names(CHAT, ["@anna"])
    participation.propose_names(CHAT, ["@bea"])
    assert participation.leave(CHAT, Person("@anna", 7)).outcome == "removed"
    assert participation.leave(CHAT, Person("@bea", 8)).outcome == "removed_maybe"
    assert events(db)[2:] == [
        ("removed", SELF, "@anna", None, None),
        ("removed_maybe", SELF, "@bea", None, None),
    ]
    assert all(row[3] is None for row in db.fetch_events(CHAT)[2:])


def test_actions_on_names_log_other_and_no_id(db):
    start(db)
    participation.add_names(CHAT, ["anna", "bea"])
    participation.propose_names(CHAT, ["carlo", "anna"])
    participation.add_names(CHAT, ["carlo"])
    participation.remove_name(CHAT, "anna")
    participation.remove_name(CHAT, "bea")
    participation.propose_names(CHAT, ["dino"])
    participation.remove_name(CHAT, "dino")
    assert events(db) == [
        ("added", OTHER, "anna", None, None),
        ("added", OTHER, "bea", None, None),
        ("proposed", OTHER, "carlo", None, None),
        ("moved_to_maybe", OTHER, "anna", None, None),
        ("confirmed", OTHER, "carlo", None, None),
        ("removed_maybe", OTHER, "anna", None, None),
        ("removed", OTHER, "bea", None, None),
        ("proposed", OTHER, "dino", None, None),
        ("removed_maybe", OTHER, "dino", None, None),
    ]


def test_a_person_taking_over_a_name_logs_the_link_and_the_confirm(db):
    start(db)
    participation.add_names(CHAT, ["@anna"])
    participation.propose_names(CHAT, ["@bea", "@carlo"])
    participation.join(CHAT, Person("@anna", 7))  # already in: only the id is saved
    participation.join(CHAT, Person("@bea", 8))  # confirmed, with the id
    participation.maybe(CHAT, Person("@carlo", 9))  # already maybe: only the id
    assert events(db)[3:] == [
        ("user_linked", SELF, "@anna", 7, None),
        ("confirmed", SELF, "@bea", 8, None),
        ("user_linked", SELF, "@carlo", 9, None),
    ]


def test_linking_a_row_that_gets_the_id_by_flipping_logs_one_event(db):
    start(db)
    participation.add_names(CHAT, ["@anna"])
    participation.maybe(CHAT, Person("@anna", 7))
    assert events(db)[1:] == [("moved_to_maybe", SELF, "@anna", 7, None)]


def test_outcomes_that_write_nothing_log_nothing(db):
    start(db, target=3)
    participation.join(CHAT, Person("@anna", 7))
    participation.maybe(CHAT, Person("@bea", 8))
    participation.join(CHAT, Person("@carlo", 9))
    before = events(db)
    assert len(before) == 3
    assert participation.join(CHAT, Person("@anna", 7)).outcome == "already_in"
    assert participation.maybe(CHAT, Person("@bea", 8)).outcome == "already_maybe"
    assert participation.join(CHAT, Person("@dino", 10)).outcome == "full"
    assert participation.maybe(CHAT, Person("@dino", 10)).outcome == "full"
    assert participation.join(CHAT, Person("@anna", 99)).outcome == "name_taken"
    assert participation.maybe(CHAT, Person("@anna", 99)).outcome == "name_taken"
    assert participation.leave(CHAT, Person("@dino", 10)).outcome == "not_in"
    assert participation.remove_name(CHAT, "dino").outcome == "not_in"
    assert participation.add_names(CHAT, ["@anna", "@dino"])[0].outcome == "already_in"
    assert participation.propose_names(CHAT, ["@bea"])[0].outcome == "already_maybe"
    assert participation.add_names(CHAT, ["/stop"]) == []
    assert events(db) == before


def test_a_repeated_join_of_a_linked_row_logs_nothing(db):
    start(db)
    participation.add_names(CHAT, ["@anna"])
    participation.join(CHAT, Person("@anna", 7))
    participation.join(CHAT, Person("@anna", 7))
    assert events(db) == [
        ("added", OTHER, "@anna", None, None),
        ("user_linked", SELF, "@anna", 7, None),
    ]


def test_a_failed_write_logs_nothing(db):
    start(db, "anna", "bea?")
    with pytest.raises(ValueError):
        remove_participant(CHAT, Participant("zoe"), actor=Actor.OTHER)
    with pytest.raises(ValueError):
        remove_participant(CHAT, Participant("bea"), actor=Actor.OTHER)  # a maybe
    with pytest.raises(ValueError):
        set_participant_maybe(CHAT, "zoe", True, actor=Actor.OTHER)
    with pytest.raises(ValueError):
        repository.link_participant_user(CHAT, "zoe", 7, actor=Actor.SELF)
    with pytest.raises(ValueError):
        add_participant(CHAT, Participant("/stop"), actor=Actor.OTHER)
    assert db.fetch_events(CHAT) == []


def test_a_failed_log_insert_rolls_back_the_change(db, monkeypatch):
    start(db, "anna", "bea?")

    def failing(*args, **kwargs):
        raise RuntimeError("log unavailable")

    monkeypatch.setattr(repository, "_log_event", failing)
    with pytest.raises(RuntimeError):
        add_participant(CHAT, Participant("carlo"), actor=Actor.OTHER)
    with pytest.raises(RuntimeError):
        remove_participant(CHAT, Participant("anna"), actor=Actor.OTHER)
    with pytest.raises(RuntimeError):
        set_participant_maybe(CHAT, "bea", False, actor=Actor.OTHER)
    with pytest.raises(RuntimeError):
        save_teams(CHAT, Teams(("anna",), ()))
    match = get_match(CHAT)
    assert [(p.name, p.is_maybe) for p in match.participants] == [
        ("anna", False),
        ("bea", True),
    ]
    assert match.teams is None
    assert db.fetch_events(CHAT) == []


def test_a_draw_logs_one_team_assigned_per_player(db):
    start(db, "anna", "bea", "carlo", "dino", "enzo?", target=4)
    teams_usecase.make_teams(
        CHAT, draw=lambda names: Teams(("anna", "carlo"), ("bea", "dino"))
    )
    uuids = db.fetch_participant_uuids(CHAT)
    assert db.fetch_events(CHAT) == [
        ("team_assigned", None, "anna", None, "black", uuids["anna"]),
        ("team_assigned", None, "bea", None, "white", uuids["bea"]),
        ("team_assigned", None, "carlo", None, "black", uuids["carlo"]),
        ("team_assigned", None, "dino", None, "white", uuids["dino"]),
    ]


def test_a_swap_logs_the_teams_again_and_revoking_logs_nothing(db):
    start(db, "anna", "bea", "carlo", "dino", target=4)
    teams_usecase.make_teams(
        CHAT, draw=lambda names: Teams(("anna", "carlo"), ("bea", "dino"))
    )
    assert teams_usecase.swap(CHAT, "anna", "bea").outcome == SwapOutcome.SWAPPED
    assert events(db)[4:] == [
        ("team_assigned", None, "anna", None, "white"),
        ("team_assigned", None, "bea", None, "black"),
        ("team_assigned", None, "carlo", None, "black"),
        ("team_assigned", None, "dino", None, "white"),
    ]
    participation.maybe(CHAT, Person("carlo"))  # revokes the teams
    assert get_match(CHAT).teams is None
    assert events(db)[8:] == [("moved_to_maybe", SELF, "carlo", None, None)]


def test_a_failed_team_save_logs_nothing(db):
    start(db, "anna", "bea")
    with pytest.raises(ValueError):
        save_teams(CHAT, Teams(("anna",), ("zoe",)))
    assert db.fetch_events(CHAT) == []
    assert get_match(CHAT).teams is None


def test_the_log_refuses_updates(db):
    start(db)
    participation.join(CHAT, Person("@anna", 7))
    with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
        db.conn.execute("UPDATE participation_event SET display_name = 'x'")
    assert events(db) == [("added", SELF, "@anna", 7, None)]


def test_deleting_a_match_or_a_chat_deletes_its_events(db):
    start(db)
    participation.join(CHAT, Person("@anna", 7))
    db.conn.execute("DELETE FROM match")
    assert db.fetch_events(CHAT) == []
    start(db)
    participation.join(CHAT, Person("@bea", 8))
    assert len(db.fetch_events(CHAT)) == 1
    db.conn.execute("DELETE FROM chat")
    assert db.conn.execute("SELECT count(*) FROM participation_event").fetchone() == (
        0,
    )


def test_the_mini_app_logs_self_actions_with_the_member_id(env):
    anna = env.anna.id
    chat = env.chat.id
    assert env.act("join").json()["outcome"] == "added"
    assert env.act("maybe").json()["outcome"] == "moved_to_maybe"
    assert env.act("join").json()["outcome"] == "confirmed"
    assert env.act("join").json()["outcome"] == "already_in"
    assert env.act("leave").json()["outcome"] == "removed"
    assert env.act("maybe").json()["outcome"] == "proposed"
    assert env.act("leave").json()["outcome"] == "removed_maybe"
    assert [row[:5] for row in env.db.fetch_events(chat)] == [
        ("added", SELF, "@anna_b", anna, None),
        ("moved_to_maybe", SELF, "@anna_b", anna, None),
        ("confirmed", SELF, "@anna_b", anna, None),
        ("removed", SELF, "@anna_b", anna, None),
        ("proposed", SELF, "@anna_b", anna, None),
        ("removed_maybe", SELF, "@anna_b", anna, None),
    ]


def test_the_mini_app_logs_actions_on_names_as_other(env):
    chat = env.chat.id
    body = {"action": "add", "text": "luca, marco"}
    assert env.client.post("/app/api/action", json=body, headers=env.auth()).json()[
        "changes"
    ] == [
        {"name": "luca", "outcome": "added"},
        {"name": "marco", "outcome": "added"},
    ]
    body = {"action": "remove", "name": "luca"}
    env.client.post("/app/api/action", json=body, headers=env.auth())
    assert [row[:5] for row in env.db.fetch_events(chat)] == [
        ("added", OTHER, "luca", None, None),
        ("added", OTHER, "marco", None, None),
        ("removed", OTHER, "luca", None, None),
    ]


def test_the_chat_handler_logs_through_the_same_use_cases(env):
    chat = env.chat.id
    env.world.send("anna", "aggiungimi")
    env.world.send("mario", "aggiungi luca")
    env.world.send("anna", "toglimi")
    assert [row[:5] for row in env.db.fetch_events(chat)] == [
        ("added", SELF, "@anna_b", env.anna.id, None),
        ("added", OTHER, "luca", None, None),
        ("removed", SELF, "@anna_b", env.anna.id, None),
    ]
