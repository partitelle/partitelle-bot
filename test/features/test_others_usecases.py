"""The add, propose, remove, swap and teams use cases against the real test database."""

import pytest

from db.repository import add_participant, get_match, save_teams
from domain import Change, Outcome, Participant, Person, Teams
from domain.teams import SwapOutcome, SwapResult, TeamsOutcome, TeamsResult
from usecases import participation
from usecases import teams as teams_usecase
from usecases.participation import add_names, propose_names, remove_name

from test_participation_usecases import CHAT, start, stored

TEAMS = Teams(("anna", "bea"), ("carlo", "dino"))
FOUR = ("anna", "bea", "carlo", "dino")


def test_no_active_match_means_none(db):
    assert add_names(CHAT, ["anna"]) is None
    assert propose_names(CHAT, ["anna"]) is None
    assert remove_name(CHAT, "anna") is None
    assert teams_usecase.swap(CHAT, "anna", "bea") is None
    assert teams_usecase.make_teams(CHAT) is None


def test_add_a_batch_with_mixed_outcomes(db):
    start(db, "anna", "bea?", "carlo?", target=4)
    changes = add_names(CHAT, ["Anna", "BEA", "dino", "enzo", "fido"])
    assert changes == [
        Change(Outcome.ALREADY_IN, "anna"),
        Change(Outcome.CONFIRMED, "bea"),
        Change(Outcome.ADDED, "dino"),
        Change(Outcome.FULL, "enzo"),
        Change(Outcome.FULL, "fido"),
    ]
    assert stored() == {
        ("anna", False),
        ("bea", False),
        ("carlo", True),
        ("dino", False),
    }
    assert get_match(CHAT).participants[-1] == Participant("dino", False, None)


def test_add_reads_the_list_again_before_each_name_and_dedups(db):
    start(db, "anna", "bea", target=4)
    changes = add_names(CHAT, ["carlo", "Dino", "carlo", "enzo"])
    assert changes == [
        Change(Outcome.ADDED, "carlo"),
        Change(Outcome.ADDED, "Dino", reached_target=True),
        Change(Outcome.FULL, "enzo"),
    ]
    assert stored() == {
        ("anna", False),
        ("bea", False),
        ("carlo", False),
        ("Dino", False),
    }


def test_add_never_revokes_the_teams(db):
    start(db, *FOUR, target=5, teams=TEAMS)
    assert add_names(CHAT, ["enzo"]) == [
        Change(Outcome.ADDED, "enzo", reached_target=True)
    ]
    assert get_match(CHAT).teams == TEAMS


def test_a_name_starting_with_a_slash_refuses_the_whole_batch(db):
    start(db, "anna")
    assert add_names(CHAT, ["bea", "/start"]) == []
    assert propose_names(CHAT, ["bea", "/start"]) == []
    assert stored() == {("anna", False)}


def test_an_empty_batch_changes_nothing(db):
    start(db, "anna")
    assert add_names(CHAT, []) == []
    assert propose_names(CHAT, []) == []


def test_propose_moves_a_confirmed_person_and_revokes_the_teams_once(db):
    start(db, *FOUR, target=5, teams=TEAMS)
    changes = propose_names(CHAT, ["ANNA", "enzo", "bea", "carlo", "fido"])
    assert changes == [
        Change(Outcome.MOVED_TO_MAYBE, "anna", revokes_teams=True),
        Change(Outcome.PROPOSED, "enzo", revokes_teams=True),
        Change(Outcome.MOVED_TO_MAYBE, "bea", revokes_teams=True),
        Change(Outcome.MOVED_TO_MAYBE, "carlo", revokes_teams=True),
        Change(Outcome.FULL, "fido"),
    ]
    assert get_match(CHAT).teams is None
    assert stored() == {
        ("anna", True),
        ("bea", True),
        ("carlo", True),
        ("dino", False),
        ("enzo", True),
    }


def test_propose_a_maybe_and_a_full_list(db):
    start(db, "anna?", "bea", target=2, teams=Teams(("bea",), ()))
    changes = propose_names(CHAT, ["Anna", "carlo"])
    assert changes == [
        Change(Outcome.ALREADY_MAYBE, "anna"),
        Change(Outcome.FULL, "carlo"),
    ]
    assert get_match(CHAT).teams == Teams(("bea",), ())


def test_remove_confirmed_maybe_and_not_in(db):
    start(db, "anna", "bea?", "carlo", teams=Teams(("anna",), ("carlo",)))
    assert remove_name(CHAT, "ANNA") == Change(
        Outcome.REMOVED, "anna", revokes_teams=True
    )
    assert get_match(CHAT).teams is None
    assert remove_name(CHAT, "bea") == Change(Outcome.REMOVED_MAYBE, "bea")
    assert remove_name(CHAT, "zed") == Change(Outcome.NOT_IN, "zed")
    assert stored() == {("carlo", False)}


def test_remove_by_name_a_row_that_has_a_telegram_user_id(db):
    start(db)
    participation.join(CHAT, Person("@Anna", 7))
    add_participant(CHAT, Participant("luca"))
    assert remove_name(CHAT, "@anna") == Change(Outcome.REMOVED, "@Anna")
    assert get_match(CHAT).participants == [Participant("luca", False, None)]


def test_add_confirms_a_row_that_has_a_telegram_user_id_by_name(db):
    start(db)
    participation.maybe(CHAT, Person("@anna", 7))
    assert add_names(CHAT, ["@ANNA"]) == [Change(Outcome.CONFIRMED, "@anna")]
    assert get_match(CHAT).participants == [Participant("@anna", False, 7)]


def test_swap_all_the_outcomes(db):
    start(db, *FOUR, "enzo", "fido?", target=6)
    assert teams_usecase.swap(CHAT, "anna", "carlo") == SwapResult(
        SwapOutcome.NO_TEAMS, "anna", "carlo"
    )
    save_teams(CHAT, TEAMS)
    assert teams_usecase.swap(CHAT, "enzo", "anna") == SwapResult(
        SwapOutcome.NOT_IN_TEAMS,
        "enzo",
        "anna",
        missing="enzo",
        missing_is_confirmed=True,
    )
    assert teams_usecase.swap(CHAT, "anna", "fido") == SwapResult(
        SwapOutcome.NOT_IN_TEAMS, "anna", "fido", missing="fido"
    )
    assert teams_usecase.swap(CHAT, "zed", "yan").missing == "zed"
    assert teams_usecase.swap(CHAT, "Anna", "BEA") == SwapResult(
        SwapOutcome.SAME_TEAM, "Anna", "BEA", stored_x="anna", stored_y="bea"
    )
    assert get_match(CHAT).teams == TEAMS
    result = teams_usecase.swap(CHAT, "ANNA", "Carlo")
    assert result == SwapResult(
        SwapOutcome.SWAPPED,
        "ANNA",
        "Carlo",
        teams=Teams(("carlo", "bea"), ("anna", "dino")),
        stored_x="anna",
        stored_y="carlo",
    )
    # read back in list order, which is not the order of the swap
    assert get_match(CHAT).teams == Teams(("bea", "carlo"), ("anna", "dino"))


def reverse_draw(names):
    half = len(names) // 2
    return Teams(tuple(reversed(names))[:half], tuple(reversed(names))[half:])


def test_teams_all_outcomes_with_a_deterministic_draw(db):
    start(db, "anna", target=5)
    assert teams_usecase.make_teams(CHAT, reverse_draw) == TeamsResult(
        TeamsOutcome.ODD_TARGET, 5
    )
    db.set_target(CHAT, 4)
    assert teams_usecase.make_teams(CHAT, reverse_draw) == TeamsResult(
        TeamsOutcome.NOT_FULL, 4
    )
    db.set_players(CHAT, [(n, False) for n in FOUR[:3]] + [("dino", True)])
    assert teams_usecase.make_teams(CHAT, reverse_draw).outcome == TeamsOutcome.NOT_FULL
    db.set_players(CHAT, [(n, False) for n in FOUR])
    drawn = Teams(("dino", "carlo"), ("bea", "anna"))
    assert teams_usecase.make_teams(CHAT, reverse_draw) == TeamsResult(
        TeamsOutcome.DRAWN, 4, drawn
    )
    # read back in list order
    stored_teams = Teams(("carlo", "dino"), ("anna", "bea"))
    assert get_match(CHAT).teams == stored_teams
    # the second time they are shown again, not drawn again
    assert teams_usecase.make_teams(CHAT, lambda names: TEAMS) == TeamsResult(
        TeamsOutcome.SHOW_EXISTING, 4, stored_teams
    )
    assert get_match(CHAT).teams == stored_teams


@pytest.mark.parametrize(
    "function, is_maybe", [(add_names, False), (propose_names, True)]
)
def test_a_match_stopped_in_the_middle_of_a_batch_raises_lookup_error(
    db, monkeypatch, function, is_maybe
):
    start(db, "anna")
    real = participation.get_match
    reads = []

    def vanishing(chat_id):
        reads.append(chat_id)
        return real(chat_id) if len(reads) <= 2 else None  # up front, then 1st name

    monkeypatch.setattr(participation, "get_match", vanishing)
    with pytest.raises(LookupError) as raised:
        function(CHAT, ["bea", "carlo"])
    assert "bea" not in str(raised.value) and "carlo" not in str(raised.value)
    assert len(reads) == 3
    assert stored() == {
        ("anna", False),
        ("bea", is_maybe),
    }  # the first name was written
