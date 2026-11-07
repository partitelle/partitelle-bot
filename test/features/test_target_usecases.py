"""The target change use case against the real test database."""

from db.repository import get_match
from domain import Teams, TargetTooLow
from domain.target import TargetOutcome, TargetResult
from usecases.target import change_target

from test_participation_usecases import CHAT, start

TEAMS = Teams(("anna", "bea"), ("carlo", "dino"))


def test_no_active_match_means_none(db):
    assert change_target(CHAT, 6) is None


def test_a_valid_target_is_written(db):
    start(db, "anna", "bea", target=4)
    assert change_target(CHAT, 6) == TargetResult(TargetOutcome.SET, 6, 4)
    assert get_match(CHAT).target == 6


def test_setting_the_target_cancels_the_teams_and_reports_it(db):
    start(db, "anna", "bea", "carlo", "dino", target=4, teams=TEAMS)
    assert change_target(CHAT, 5) == TargetResult(
        TargetOutcome.SET, 5, 4, revokes_teams=True
    )
    match = get_match(CHAT)
    assert match.target == 5
    assert match.teams is None


def test_reaching_the_target_is_reported(db):
    start(db, "anna", "bea", target=4)
    assert change_target(CHAT, 2) == TargetResult(
        TargetOutcome.SET, 2, 4, reached_target=True
    )
    assert get_match(CHAT).target == 2


def test_refused_targets_change_nothing(db):
    start(db, "anna", "bea", "carlo", "dino", target=4, teams=TEAMS)
    for number, outcome in ((0, TargetOutcome.INVALID), (41, TargetOutcome.INVALID)):
        assert change_target(CHAT, number).outcome == outcome
    assert change_target(CHAT, 1).outcome == TargetOutcome.TOO_SMALL
    assert change_target(CHAT, 2) == TargetResult(
        TargetOutcome.TOO_LOW, 2, 4, refusal=TargetTooLow(2, 4, 0)
    )
    match = get_match(CHAT)
    assert match.target == 4
    assert match.teams == TEAMS
