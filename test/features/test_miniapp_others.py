# ruff: noqa: F811
"""The Mini App acting on other people, swapping and making the teams.

The owner's requirement: whatever the Mini App does, the group gets EXACTLY the Bot API calls the
equivalent chat command produces. Each parity test runs the chat keyword in one chat and the Mini App
action in another, identical chat, and compares the recorded calls, the JSON answer and the database.
"""

import json
import logging
import random

import pytest

from db.repository import get_match, get_or_create_miniapp_token
from web.rate_limit import RateLimiter
from test_miniapp_api import (  # noqa: F401  (fixtures and helpers)
    DESCRIPTION,
    STARTS,
    SUMMARY_ID,
    Env,
    enabled,
    env,
)

ALL_FOUR = [("a", False), ("b", False), ("c", False), ("d", False)]


def teams_ab_cd(db, chat_id):
    db.set_teams(chat_id, ["a", "b"], ["c", "d"])


def chat_twin(env):
    """A second chat, set up like the Env's one, for the chat keyword."""
    world = env.world
    chat = world.add_chat("Gemello")
    world.send("mario", "/start", chat=chat)
    env.db.set_starts(chat.id, STARTS)
    env.db.set_target(chat.id, 4)
    env.db.set_summary_message_id(chat.id, SUMMARY_ID)
    return chat


def snapshot(chat_id):
    match = get_match(chat_id)
    teams = None if match.teams is None else (match.teams.black, match.teams.white)
    return (
        [(p.name, p.is_maybe, p.telegram_user_id) for p in match.participants],
        teams,
        match.target,
        match.summary_message_id,
    )


def normalised(calls, chat_id, token):
    out = []
    for call in calls:
        assert call.params["chat_id"] == chat_id
        text = json.dumps({**call.params, "chat_id": "CHAT"}, sort_keys=True)
        out.append((call.method, text.replace(token, "TOKEN")))
    return out


def run_parity(env, players, chat_text, body, *, teams=None, target=None, seed=1):
    """Runs `chat_text` in the twin chat and `body` in the Env's chat, both set up the same."""
    twin = chat_twin(env)
    for chat_id in (twin.id, env.chat.id):
        if target is not None:
            env.db.set_target(chat_id, target)
        if players:
            env.db.set_players(chat_id, players)
        if teams:
            env.db.set_teams(chat_id, *teams)
    env.world.forget_calls()

    random.seed(seed)
    env.world.send("anna", chat_text, chat=twin)
    chat_calls = list(env.world.unconsumed())
    env.world.forget_calls()

    random.seed(seed)
    response = env.client.post("/app/api/action", json=body, headers=env.auth())
    app_calls = [c for c in env.world.unconsumed() if c.method != "get_chat_member"]

    assert response.status_code == 200
    assert chat_calls, "the chat did nothing: the test proves nothing"
    twin_token = get_or_create_miniapp_token(twin.id)
    assert normalised(app_calls, env.chat.id, env.token) == normalised(
        chat_calls, twin.id, twin_token
    )
    assert snapshot(env.chat.id) == snapshot(twin.id)
    answer = response.json()
    assert answer["state"] == env.match().json()
    return answer, app_calls


def texts(calls):
    """What the group is told, in order (the summary edit and the pin are not messages)."""
    return [c.params["text"] for c in calls if c.method == "send_message"]


def without_state(answer):
    return {k: v for k, v in answer.items() if k != "state"}


def anna_row(env):
    return [("@anna_b", False, env.anna.id)]


# ---- self actions: the same reply as the chat -----------------------------------------------------


def test_parity_join(env):
    answer, calls = run_parity(env, None, "aggiungimi", {"action": "join"})
    assert without_state(answer) == {"outcome": "added", "teams_cancelled": False}
    assert texts(calls)[0] == "Ok, @anna\\_b, ti aggiungo"
    assert [c.method for c in calls] == [
        "send_message",
        "edit_message_text",
        "pin_chat_message",
    ]


def test_parity_maybe(env):
    answer, calls = run_parity(env, None, "proponimi", {"action": "maybe"})
    assert without_state(answer) == {"outcome": "proposed", "teams_cancelled": False}
    assert texts(calls)[0] == "Ok, @anna\\_b, ti propongo"


def test_parity_leave(env):
    env.db.set_players(env.chat.id, anna_row(env))  # placeholder, replaced below
    answer, calls = run_parity(
        env, [("@anna_b", False, env.anna.id)], "toglimi", {"action": "leave"}
    )
    assert without_state(answer) == {"outcome": "removed", "teams_cancelled": False}
    assert texts(calls)[0] == "Mamma mia... che paccaro"


def test_parity_join_when_full(env):
    answer, calls = run_parity(
        env, ALL_FOUR[:3] + [("d", True)], "aggiungimi", {"action": "join"}
    )
    assert answer["outcome"] == "full"
    assert texts(calls) == ["Siete già in 4 (1 in forse)"]


# ---- add and propose ------------------------------------------------------------------------------


def test_parity_add_with_mixed_outcomes(env):
    answer, calls = run_parity(
        env,
        [("luca", True), ("giulia", False)],
        "aggiungi Luca, marco, giulia, marco",
        {"action": "add", "text": "Luca, marco, giulia, marco"},
    )
    assert without_state(answer) == {
        "changes": [
            {"name": "luca", "outcome": "confirmed"},
            {"name": "marco", "outcome": "added"},
            {"name": "giulia", "outcome": "already_in"},
        ],
        "teams_cancelled": False,
        "reached_target": False,
    }
    assert texts(calls)[0] == (
        "Ok, aggiungo marco. Ok, luca, ti confermo. giulia è già nella lista"
    )
    assert sorted(env.players()) == [
        ("giulia", False, None),
        ("luca", False, None),
        ("marco", False, None),
    ]


def test_parity_add_when_full(env):
    answer, calls = run_parity(
        env, ALL_FOUR, "aggiungi e, f", {"action": "add", "text": "e, f"}
    )
    assert without_state(answer) == {
        "changes": [
            {"name": "e", "outcome": "full"},
            {"name": "f", "outcome": "full"},
        ],
        "teams_cancelled": False,
        "reached_target": False,
    }
    assert texts(calls) == ["Siete già in 4"]


def test_parity_add_reaching_the_target_and_then_full(env):
    answer, calls = run_parity(
        env,
        ALL_FOUR[:3],
        "aggiungi d, e",
        {"action": "add", "text": "d, e"},
    )
    assert answer["reached_target"] is True
    assert [c.method for c in calls] == [
        "send_message",
        "edit_message_text",
        "pin_chat_message",
        "send_message",
    ]
    assert (
        texts(calls)[0]
        == "Ok, aggiungo d. Ma aspetta! Non posso aggiungere e perché siete già in 4"
    )
    assert "SI GIOCA" in texts(calls)[1]


def test_parity_propose_moving_a_confirmed_person_cancels_the_teams(env):
    answer, calls = run_parity(
        env,
        ALL_FOUR,
        "proponi a",
        {"action": "propose", "text": "a"},
        teams=(["a", "b"], ["c", "d"]),
    )
    assert without_state(answer) == {
        "changes": [{"name": "a", "outcome": "moved_to_maybe"}],
        "teams_cancelled": True,
        "reached_target": False,
    }
    assert texts(calls)[:2] == ["Va bene, metto in forse a", "*SQUADRE ANNULLATE*"]
    assert answer["state"]["match"]["teams"] is None
    assert ("a", True, None) in env.players()


def test_parity_propose_new_names_and_full(env):
    answer, calls = run_parity(
        env,
        ALL_FOUR[:2] + [("c", True)],
        "proponi x, c, y",
        {"action": "propose", "text": "x, c, y"},
    )
    assert [c["outcome"] for c in answer["changes"]] == [
        "proposed",
        "already_maybe",
        "full",
    ]
    assert texts(calls)[0] == (
        "Ok, propongo x. c è già nella lista. "
        "Ma aspetta! Non posso proporre y perché siete già in 4"
    )


def test_parity_propose_when_full(env):
    answer, calls = run_parity(
        env, ALL_FOUR, "proponi e", {"action": "propose", "text": "e"}
    )
    assert answer["changes"] == [{"name": "e", "outcome": "full"}]
    assert texts(calls) == ["Siete già in 4"]


# ---- remove -----------------------------------------------------------------------------------------


def test_parity_remove_a_confirmed_person(env):
    answer, calls = run_parity(
        env,
        [("luca", False), ("b", False)],
        "togli Luca",
        {"action": "remove", "name": "Luca"},
    )
    assert without_state(answer) == {"outcome": "removed", "teams_cancelled": False}
    assert texts(calls)[0] == "Che vergogna, luca"
    assert env.players() == [("b", False, None)]


def test_parity_remove_a_confirmed_person_with_teams(env):
    answer, calls = run_parity(
        env,
        ALL_FOUR,
        "togli a",
        {"action": "remove", "name": "a"},
        teams=(["a", "b"], ["c", "d"]),
    )
    assert answer["teams_cancelled"] is True
    assert texts(calls)[:2] == ["Che vergogna, a", "*SQUADRE ANNULLATE*"]


def test_parity_remove_a_maybe_person(env):
    answer, calls = run_parity(
        env,
        [("luca", True)],
        "togli luca",
        {"action": "remove", "name": "luca"},
    )
    assert without_state(answer) == {
        "outcome": "removed_maybe",
        "teams_cancelled": False,
    }
    assert texts(calls)[0] == "Davvero? Ma luca, ne sei proprio sicuro?"


def test_parity_remove_somebody_who_is_not_in(env):
    answer, calls = run_parity(
        env,
        [("b", False)],
        "togli luca",
        {"action": "remove", "name": " luca "},
    )
    assert without_state(answer) == {"outcome": "not_in", "teams_cancelled": False}
    assert texts(calls) == ["luca non è nella lista. Chi dovrei togliere?"]


def test_remove_escapes_the_name_like_the_chat(env):
    answer, calls = run_parity(
        env,
        [("a_b*", False)],
        "togli a_b*",
        {"action": "remove", "name": "a_b*"},
    )
    assert texts(calls)[0] == "Che vergogna, a\\_b\\*"


# ---- swap --------------------------------------------------------------------------------------------


def test_parity_swap(env):
    answer, calls = run_parity(
        env,
        ALL_FOUR,
        "scambia A con c",
        {"action": "swap", "x": " A ", "y": "c"},
        teams=(["a", "b"], ["c", "d"]),
    )
    assert without_state(answer) == {"outcome": "swapped"}
    assert texts(calls) == ["Perfetto, ho scambiato a con c"]
    assert answer["state"]["match"]["teams"] == {
        "black": ["b", "c"],
        "white": ["a", "d"],
    }


def test_parity_swap_two_players_of_the_same_team(env):
    answer, calls = run_parity(
        env,
        ALL_FOUR,
        "scambia a con b",
        {"action": "swap", "x": "a", "y": "b"},
        teams=(["a", "b"], ["c", "d"]),
    )
    assert without_state(answer) == {"outcome": "same_team"}
    assert texts(calls) == ["a e b sono nella stessa squadra!"]


def test_parity_swap_without_teams(env):
    answer, calls = run_parity(
        env, ALL_FOUR, "scambia a con c", {"action": "swap", "x": "a", "y": "c"}
    )
    assert without_state(answer) == {"outcome": "no_teams"}
    assert texts(calls) == [
        "Per usare questa funzionalità devi prima formare delle squadre con /teams"
    ]


def test_parity_swap_with_somebody_in_no_team(env):
    answer, calls = run_parity(
        env,
        ALL_FOUR,
        "scambia a con d",
        {"action": "swap", "x": "a", "y": "d"},
        teams=(["a", "b"], ["c"]),
    )
    assert without_state(answer) == {"outcome": "not_in_teams", "missing": "d"}
    assert texts(calls) == ["d non è in nessuna squadra"]


def test_parity_swap_with_a_maybe_person(env):
    answer, calls = run_parity(
        env,
        ALL_FOUR[:3] + [("d", True)],
        "scambia a con d",
        {"action": "swap", "x": "a", "y": "d"},
        teams=(["a", "b"], ["c"]),
    )
    assert without_state(answer) == {"outcome": "not_in_teams", "missing": "d"}
    assert texts(calls) == ["d non c'è"]


def test_parity_swap_with_somebody_not_in_the_list(env):
    answer, calls = run_parity(
        env,
        ALL_FOUR,
        "scambia a con zed",
        {"action": "swap", "x": "a", "y": "zed"},
        teams=(["a", "b"], ["c", "d"]),
    )
    assert without_state(answer) == {"outcome": "not_in_teams", "missing": "zed"}
    assert texts(calls) == ["zed non c'è"]


# ---- teams -------------------------------------------------------------------------------------------


def test_parity_teams_drawn(env):
    answer, calls = run_parity(env, ALL_FOUR, "/teams", {"action": "teams"})
    assert without_state(answer) == {"outcome": "drawn"}
    (call,) = calls
    assert call.params["text"].startswith("*SQUADRA NERA* \n - ")
    teams = answer["state"]["match"]["teams"]
    assert sorted(teams["black"] + teams["white"]) == ["a", "b", "c", "d"]
    assert len(teams["black"]) == 2


def test_parity_teams_not_full(env):
    answer, calls = run_parity(env, ALL_FOUR[:3], "/teams", {"action": "teams"})
    assert without_state(answer) == {"outcome": "not_full"}
    assert texts(calls) == [
        "Prima di poter fare le squadre, devi raggiungere 4 partecipanti"
    ]
    assert answer["state"]["match"]["teams"] is None


def test_parity_teams_odd_target(env):
    answer, calls = run_parity(env, ALL_FOUR, "/teams", {"action": "teams"}, target=5)
    assert without_state(answer) == {"outcome": "odd_target"}
    assert texts(calls) == [
        "Per usare questa funzionalità dovete essere in un numero pari di partecipanti"
    ]


def test_parity_teams_existing(env):
    answer, calls = run_parity(
        env,
        ALL_FOUR,
        "/teams",
        {"action": "teams"},
        teams=(["a", "b"], ["c", "d"]),
    )
    assert without_state(answer) == {"outcome": "show_existing"}
    assert texts(calls) == [
        "*SQUADRA NERA* \n - a\n - b\n\n*SQUADRA BIANCA* \n - c\n - d\n"
    ]


# ---- privacy ------------------------------------------------------------------------------------------


def test_people_added_by_others_never_get_a_telegram_id(env):
    env.act("join")
    env.client.post(
        "/app/api/action",
        json={"action": "add", "text": "anna_b, @anna_b, zed"},
        headers=env.auth(),
    )
    ids = {name: user_id for name, _, user_id in env.players()}
    assert ids["@anna_b"] == env.anna.id
    assert ids["zed"] is None and ids["anna_b"] is None


def test_responses_carry_no_ids(env):
    env.db.set_players(env.chat.id, ALL_FOUR)
    for body in (
        {"action": "add", "text": "x"},
        {"action": "remove", "name": "a"},
        {"action": "teams"},
        {"action": "swap", "x": "a", "y": "b"},
    ):
        text = env.client.post("/app/api/action", json=body, headers=env.auth()).text
        for forbidden in (str(env.chat.id), str(env.anna.id), env.token):
            assert forbidden not in text


def test_a_match_stopped_in_the_meantime_is_closed_for_every_action(env):
    env.world.send("mario", "/stop")
    env.world.forget_calls()
    for body in (
        {"action": "add", "text": "x"},
        {"action": "propose", "text": "x"},
        {"action": "remove", "name": "x"},
        {"action": "swap", "x": "x", "y": "y"},
        {"action": "teams"},
    ):
        response = env.client.post("/app/api/action", json=body, headers=env.auth())
        assert response.status_code == 404
        assert response.json() == {"error": "match_closed"}
    assert env.calls() == []


# ---- validation ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        {"action": "add"},
        {"action": "add", "text": 1},
        {"action": "add", "text": None},
        {"action": "add", "text": ["a"]},
        {"action": "add", "text": "x", "name": "y"},
        {"action": "add", "name": "x"},
        {"action": "add", "text": "a" * 501},
        {"action": "propose", "text": "a" * 501},
        {"action": "propose"},
        {"action": "remove"},
        {"action": "remove", "text": "x"},
        {"action": "remove", "name": "a" * 501},
        {"action": "remove", "name": 3},
        {"action": "swap", "x": "a"},
        {"action": "swap", "x": "a", "y": None},
        {"action": "swap", "x": "a", "y": "b", "z": "c"},
        {"action": "swap", "x": "a" * 501, "y": "b"},
        {"action": "teams", "x": "a"},
        {"action": "join", "text": "x"},
        {"action": "leave", "name": "x"},
    ],
)
def test_a_malformed_action_is_a_bad_request(env, body):
    response = env.client.post("/app/api/action", json=body, headers=env.auth())
    assert response.status_code == 400
    assert response.json() == {"error": "bad_request"}
    assert env.players() == []
    assert env.calls() == []


def test_the_longest_text_is_accepted(env):
    long_name = "a" * 500
    response = env.client.post(
        "/app/api/action",
        json={"action": "add", "text": long_name},
        headers=env.auth(),
    )
    assert response.status_code == 200
    assert env.players() == [(long_name, False, None)]


@pytest.mark.parametrize(
    "body",
    [
        {"action": "add", "text": ""},
        {"action": "add", "text": " , ,"},
        {"action": "add", "text": "/start"},
        {"action": "add", "text": "luca, /start"},
        {"action": "propose", "text": "  "},
        {"action": "propose", "text": "/x, luca"},
        {"action": "remove", "name": ""},
        {"action": "remove", "name": "   "},
        {"action": "remove", "name": "/stop"},
        {"action": "swap", "x": "", "y": "b"},
        {"action": "swap", "x": "a", "y": "  "},
        {"action": "swap", "x": "a con b", "y": "c"},
    ],
)
def test_an_invalid_name_is_refused_and_nothing_is_posted(env, body):
    env.db.set_players(env.chat.id, ALL_FOUR[:2])
    response = env.client.post("/app/api/action", json=body, headers=env.auth())
    assert response.status_code == 422
    assert response.json() == {"error": "invalid_name"}
    assert env.players() == [("a", False, None), ("b", False, None)]
    assert env.calls() == []


def test_the_validation_comes_after_the_membership_check(env):
    stranger = env.world.add_user("eve", "Eve", "eve")
    response = env.client.post(
        "/app/api/action",
        json={"action": "add", "text": "/x"},
        headers=env.auth(person=stranger),
    )
    assert response.status_code == 403


# ---- membership ---------------------------------------------------------------------------------------


def test_a_write_checks_the_membership_afresh_a_read_uses_the_cache(env):
    assert env.match().status_code == 200  # cached as a member
    env.world.member_status[(env.chat.id, env.anna.id)] = "left"
    assert env.match().status_code == 200  # still within the 60 seconds
    response = env.client.post(
        "/app/api/action",
        json={"action": "add", "text": "luca"},
        headers=env.auth(),
    )
    assert response.status_code == 403
    assert response.json() == {"error": "not_member"}
    assert env.players() == []
    assert env.calls() == []
    assert env.match().status_code == 403  # the refreshed answer is remembered


@pytest.mark.parametrize(
    "body",
    [
        {"action": "join"},
        {"action": "propose", "text": "luca"},
        {"action": "remove", "name": "luca"},
        {"action": "swap", "x": "a", "y": "b"},
        {"action": "teams"},
    ],
)
def test_every_action_is_checked_afresh(env, body):
    env.match()
    env.world.member_status[(env.chat.id, env.anna.id)] = "kicked"
    response = env.client.post("/app/api/action", json=body, headers=env.auth())
    assert response.status_code == 403
    assert env.calls() == []


# ---- the description and the pitch ----------------------------------------------------------------------


def set_description(env, value):
    env.db._set_match(env.chat.id, "description", value)


@pytest.mark.parametrize(
    "stored, expected",
    [
        (None, None),
        ("", None),
        ("None", None),
        (
            "*Portare* la _maglia_ [qui](http://x.y/a_b) `ok`  \n\n",
            "Portare la maglia qui ok",
        ),
    ],
)
def test_the_description_is_plain_text(env, stored, expected):
    set_description(env, stored)
    assert env.match().json()["match"]["description"] == expected


def test_a_match_never_described_shows_the_default_text(env):
    description = env.match().json()["match"]["description"]
    assert description == DESCRIPTION
    assert "*" not in description and "_" not in description


def test_the_pitch_set_with_setpitch_is_in_the_state(env):
    env.world.send("mario", "/setpitch Campo 1, Via Roma", chat=env.chat)
    env.world.forget_calls()
    assert get_match(env.chat.id).pitch == "Campo 1, Via Roma"
    assert env.match().json()["match"]["pitch"] == "Campo 1, Via Roma"
    assert env.act("join").json()["state"]["match"]["pitch"] == "Campo 1, Via Roma"


def test_the_group_default_pitch_is_in_the_state(env):
    world = env.world
    chat = world.add_chat("Con campo")
    env.db.set_default_pitch(chat.id, "Campo di default")
    world.send("mario", "/start", chat=chat)
    token = get_or_create_miniapp_token(chat.id)
    world.member_status[(chat.id, env.anna.id)] = "member"
    response = env.client.post("/app/api/match", json={}, headers=env.auth(token=token))
    assert response.status_code == 200
    assert response.json()["match"]["pitch"] == "Campo di default"


def test_a_match_without_a_pitch_says_null(env):
    assert env.match().json()["match"]["pitch"] is None


# ---- failures towards the group, and logs ----------------------------------------------------------------

NAME = "zorrolino"
OTHER = "pancrazio"


def test_a_failing_reply_is_logged_by_type_and_the_action_still_succeeds(env, caplog):
    env.world.telegram.fail_next("send_message", f"{NAME} not found")
    with caplog.at_level(logging.WARNING):
        response = env.client.post(
            "/app/api/action",
            json={"action": "add", "text": NAME},
            headers=env.auth(),
        )
    assert response.status_code == 200
    assert response.json()["changes"] == [{"name": NAME, "outcome": "added"}]
    assert env.players() == [(NAME, False, None)]
    # the summary is still refreshed
    assert [c.method for c in env.calls()] == [
        "send_message",
        "edit_message_text",
        "pin_chat_message",
    ]
    assert [r.getMessage() for r in caplog.records] == [
        "Mini app: could not update the group: BadRequest"
    ]


def test_no_name_reaches_the_logs_when_telegram_fails(
    world, db, freeze_time, enabled, caplog
):
    freeze_time("2026-10-21 21:00")
    env = Env(world, db, action_limiter=RateLimiter(1000, 60))
    env.db.set_players(env.chat.id, ALL_FOUR)
    env.db.set_teams(env.chat.id, ["a", "b"], ["c", "d"])
    caplog.set_level(logging.DEBUG)
    caplog.set_level(logging.INFO, logger="telegram")
    failing = f"{NAME} {OTHER} {env.anna.id} {env.token}"
    results = []
    for method in ("send_message", "edit_message_text"):
        for body in (
            {"action": "add", "text": f"{NAME}, {OTHER}"},
            {"action": "remove", "name": "a"},
            {"action": "swap", "x": "b", "y": "c"},
            {"action": "propose", "text": NAME},
            {"action": "teams"},
            {"action": "join"},
        ):
            env.world.telegram.fail_next(method, failing)
            results.append(
                env.client.post("/app/api/action", json=body, headers=env.auth())
            )
    assert [r.status_code for r in results] == [200] * len(results)
    logged = "\n".join(
        f"{r.name} {r.getMessage()} {r.exc_text} {r.args}" for r in caplog.records
    )
    assert "BadRequest" in logged
    for secret in (NAME, OTHER, str(env.anna.id), env.token, "anna_b", "Anna"):
        assert secret not in logged, "a name or id reached the logs"


def test_an_invalid_name_logs_nothing(env, caplog):
    caplog.set_level(logging.DEBUG)
    caplog.set_level(logging.INFO, logger="telegram")
    env.client.post(
        "/app/api/action",
        json={"action": "add", "text": f"{NAME}, /{OTHER}"},
        headers=env.auth(),
    )
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert NAME not in logged and OTHER not in logged


# ---- stricter input and races ---------------------------------------------------------------------------

UNSTORABLE = ["\x00", "\ud800"]
UNSTORABLE_IDS = ["nul", "lone_surrogate"]


def unstorable_bodies(bad):
    return [
        {"action": "add", "text": f"lu{bad}ca"},
        {"action": "propose", "text": f"lu{bad}ca"},
        {"action": "remove", "name": f"lu{bad}ca"},
        {"action": "swap", "x": f"a{bad}", "y": "b"},
        {"action": "swap", "x": "a", "y": f"{bad}b"},
    ]


@pytest.mark.parametrize("bad", UNSTORABLE, ids=UNSTORABLE_IDS)
@pytest.mark.parametrize("index", range(5))
def test_a_nul_or_unencodable_text_is_a_bad_request(env, bad, index):
    env.db.set_players(env.chat.id, ALL_FOUR)
    env.db.set_teams(env.chat.id, ["a", "b"], ["c", "d"])
    body = unstorable_bodies(bad)[index]
    # json.dumps escapes the lone surrogate as \\ud800, as a browser's JSON.stringify does
    response = env.client.post(
        "/app/api/action", content=json.dumps(body), headers=env.auth()
    )
    assert response.status_code == 400
    assert response.json() == {"error": "bad_request"}
    assert env.players() == [(n, m, None) for n, m in ALL_FOUR]
    assert get_match(env.chat.id).teams is not None
    assert env.calls() == []


def names_text(count):
    return ", ".join(f"n{i:02}" for i in range(count))


def test_fifty_distinct_names_are_accepted(env):
    response = env.client.post(
        "/app/api/action",
        json={"action": "add", "text": names_text(50)},
        headers=env.auth(),
    )
    assert response.status_code == 200
    assert len(response.json()["changes"]) == 50
    assert len(env.players()) == 4  # the target is 4: the others are "full"


@pytest.mark.parametrize("action", ["add", "propose"])
def test_more_than_fifty_distinct_names_are_refused(env, action):
    response = env.client.post(
        "/app/api/action",
        json={"action": action, "text": names_text(51)},
        headers=env.auth(),
    )
    assert response.status_code == 422
    assert response.json() == {"error": "invalid_name"}
    assert env.players() == []
    assert env.calls() == []


def test_repeated_names_count_once_towards_the_cap(env):
    text = ", ".join([names_text(50)] * 2)[:500]
    assert len(set(text.replace(" ", "").split(","))) <= 50
    response = env.client.post(
        "/app/api/action",
        json={"action": "propose", "text": text},
        headers=env.auth(),
    )
    assert response.status_code == 200


@pytest.mark.parametrize("action", ["add", "propose"])
def test_a_match_stopped_in_the_middle_of_a_batch_is_closed(env, monkeypatch, action):
    import usecases.participation as usecase

    real = usecase.get_match
    reads = []

    def vanishing(chat_id):
        reads.append(chat_id)
        return real(chat_id) if len(reads) <= 1 else None

    monkeypatch.setattr(usecase, "get_match", vanishing)
    response = env.client.post(
        "/app/api/action", json={"action": action, "text": "x, y"}, headers=env.auth()
    )
    assert response.status_code == 404
    assert response.json() == {"error": "match_closed"}
    assert len(reads) == 2
    assert env.players() == []
    assert env.calls() == []


@pytest.mark.parametrize("action", ["join", "maybe", "leave"])
def test_a_match_stopped_right_after_a_self_action_is_closed_like_the_others(
    env, monkeypatch, action
):
    import web.miniapp as miniapp

    env.db.set_players(env.chat.id, [("@anna_b", False, env.anna.id)])
    reads = []

    def stopped(chat_id):
        reads.append(chat_id)
        return None

    monkeypatch.setattr(miniapp, "get_match", stopped)
    response = env.client.post(
        "/app/api/action", json={"action": action}, headers=env.auth()
    )
    assert response.status_code == 404
    assert response.json() == {"error": "match_closed"}
    assert reads == [
        env.chat.id
    ]  # the read right after the write, nothing is announced
    assert env.calls() == []
