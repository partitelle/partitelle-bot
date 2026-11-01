"""The Mini App server side end to end: the real web app, the real database, Telegram faked at the
network edge (getChatMember, editMessageText, sendMessage)."""

import logging
import re
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from starlette.testclient import TestClient
from telegram.error import TimedOut

import web.miniapp
from conf import conf
from db.repository import get_match, get_or_create_miniapp_token
from miniapp_signing import init_data
from telegram_world import BOT_TOKEN
from web.app import create_app
from web.miniapp import miniapp_routes
from web.rate_limit import RateLimiter

STARTS = datetime(2026, 11, 4, 20, 0, tzinfo=ZoneInfo("Europe/Rome"))
SUMMARY_ID = 5
# the default description of a match, as plain text
DESCRIPTION = (
    "5 goal di scarto e le squadre si potrebbero cambiare \n"
    "6 goal di scarto e le squadre si devono cambiare \n"
    "(ditelo a chiunque invitate) \n"
    "PORTARE UNA MAGLIA BIANCA E UNA COLORATA"
)


class Env:
    def __init__(self, world, db, **limits):
        self.world, self.db = world, db
        self.chat = world.add_chat("Calcetto")
        world.add_user("mario", "Mario", "mario")
        world.send("mario", "/start")
        db.set_starts(self.chat.id, STARTS)
        db.set_target(self.chat.id, 4)
        db.set_summary_message_id(self.chat.id, SUMMARY_ID)
        self.token = get_or_create_miniapp_token(self.chat.id)
        self.anna = world.add_user("anna", "Anna", "Anna_B")
        world.member_status[(self.chat.id, self.anna.id)] = "member"
        self.app = create_app(
            world.application,
            "secret",
            extra_routes=miniapp_routes(world.application, BOT_TOKEN, **limits),
        )
        self.client = TestClient(self.app)
        world.forget_calls()

    def auth(self, person=None, token=None, age=0, bot_token=BOT_TOKEN):
        person = person or self.anna
        raw = init_data(
            bot_token,
            auth_date=int(time.time()) - age,
            start_param=token or self.token,
            user=person.to_json(),
        )
        return {"Authorization": f"tma {raw}"}

    def match(self, **kw):
        return self.client.post("/app/api/match", json={}, headers=self.auth(**kw))

    def act(self, action, **kw):
        return self.client.post(
            "/app/api/action", json={"action": action}, headers=self.auth(**kw)
        )

    def players(self):
        return [
            (p.name, p.is_maybe, p.telegram_user_id)
            for p in get_match(self.chat.id).participants
        ]

    def calls(self):
        return [c for c in self.world.unconsumed() if c.method != "get_chat_member"]


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setattr(conf, "miniapp_short_name", "lista")


@pytest.fixture
def env(world, db, freeze_time, enabled):
    freeze_time("2026-10-21 21:00")
    return Env(world, db)


def state(confirmed=(), maybe=(), teams=None, has_room=True, status="out"):
    return {
        "match": {
            "day": "Mercoledì 04/11/2026",
            "time": "20:00",
            "target": 4,
            "has_room": has_room,
            "description": DESCRIPTION,
            "pitch": None,
            "confirmed": list(confirmed),
            "maybe": list(maybe),
            "teams": teams,
        },
        "me": {"name": "@anna_b", "status": status},
    }


def button(call):
    return call.params["reply_markup"]["inline_keyboard"]


# ---- reading ------------------------------------------------------------------------------------


def test_a_member_reads_the_state(env):
    env.db.set_players(env.chat.id, [("@mario", False), ("luca", True)])
    response = env.match()
    assert response.status_code == 200
    assert response.json() == state(["@mario"], ["luca"])
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert env.calls() == []


def test_the_state_shows_my_status_teams_and_a_full_match(env):
    env.db.set_players(
        env.chat.id,
        [
            ("@mario", False),
            ("bea", False),
            ("@anna_b", True, env.anna.id),
            ("c", False),
        ],
    )
    env.db.set_teams(env.chat.id, ["@mario", "bea"], ["c"])
    env.db.set_pitch(env.chat.id, "Campo 1")
    expected = state(
        ["@mario", "bea", "c"],
        ["@anna_b"],
        {"black": ["@mario", "bea"], "white": ["c"]},
        has_room=False,
        status="maybe",
    )
    expected["match"]["pitch"] = "Campo 1"
    assert env.match().json() == expected


def test_i_am_in_when_my_row_carries_my_user_id(env):
    env.db.set_players(env.chat.id, [("old name", False, env.anna.id)])
    assert env.match().json()["me"] == {"name": "@anna_b", "status": "in"}


# ---- acting -------------------------------------------------------------------------------------


def test_join_stores_the_user_id_and_refreshes_the_summary_with_the_button(env):
    response = env.act("join")
    assert response.status_code == 200
    assert response.json() == {
        "outcome": "added",
        "teams_cancelled": False,
        "state": state(["@anna_b"], status="in"),
    }
    assert env.players() == [("@anna_b", False, env.anna.id)]
    (reply, edit, pin) = env.calls()
    assert reply.method == "send_message"
    assert reply.params["parse_mode"] == "markdown"
    assert reply.params["text"] == "Ok, @anna\\_b, ti aggiungo"
    assert edit.method == "edit_message_text"
    assert edit.params["message_id"] == SUMMARY_ID
    assert "1. @anna\\_b ✅" in edit.params["text"]
    assert button(edit) == [
        [
            {
                "text": "apri la lista",
                "url": f"https://t.me/partitelle_test_bot/lista?startapp={env.token}",
            }
        ]
    ]
    assert pin.method == "pin_chat_message"


def test_the_group_gets_the_chat_reply_and_nothing_in_place_of_the_typed_message(env):
    env.act("join")
    assert [c.method for c in env.calls()] == [
        "send_message",
        "edit_message_text",
        "pin_chat_message",
    ]


def test_join_reaching_the_target_announces_it(env):
    env.db.set_players(env.chat.id, [("a", False), ("b", False), ("c", False)])
    assert env.act("join").json()["outcome"] == "added"
    methods = [c.method for c in env.calls()]
    assert methods == [
        "send_message",
        "edit_message_text",
        "pin_chat_message",
        "send_message",
    ]
    assert "SI GIOCA" in env.calls()[3].params["text"]


def test_maybe_then_leave(env):
    assert env.act("maybe").json()["outcome"] == "proposed"
    assert env.players() == [("@anna_b", True, env.anna.id)]
    body = env.act("leave").json()
    assert body["outcome"] == "removed_maybe"
    assert body["state"] == state()
    assert env.players() == []


def test_maybe_and_leave_with_teams_cancel_them(env):
    env.db.set_players(
        env.chat.id, [("@anna_b", False, env.anna.id), ("b", False), ("c", False)]
    )
    env.db.set_teams(env.chat.id, ["@anna_b", "b"], ["c"])
    body = env.act("maybe").json()
    assert body["outcome"] == "moved_to_maybe"
    assert body["teams_cancelled"] is True
    assert body["state"]["match"]["teams"] is None
    assert get_match(env.chat.id).teams is None
    sent = [c for c in env.calls() if c.method == "send_message"]
    assert [c.params["text"] for c in sent] == [
        "Ok, @anna\\_b, ti metto in forse",
        "*SQUADRE ANNULLATE*",
    ]

    env.db.set_teams(env.chat.id, ["b"], ["c"])
    env.world.forget_calls()
    body = env.act("leave").json()
    assert body["outcome"] == "removed_maybe"
    assert body["teams_cancelled"] is True
    assert get_match(env.chat.id).teams is None
    sent = [c for c in env.calls() if c.method == "send_message"]
    assert [c.params["text"] for c in sent] == [
        "Peccato, un po' ci avevo sperato",
        "*SQUADRE ANNULLATE*",
    ]


def test_a_full_match_refuses_without_writing(env):
    env.db.set_players(
        env.chat.id, [("a", False), ("b", False), ("c", False), ("d", True)]
    )
    response = env.act("join")
    assert response.status_code == 200
    assert response.json()["outcome"] == "full"
    assert response.json()["teams_cancelled"] is False
    assert [p[0] for p in env.players()] == ["a", "b", "c", "d"]
    (reply,) = env.calls()  # only the answer, as in the chat: the list did not change
    assert reply.params["text"] == "Siete già in 4 (1 in forse)"


def test_a_name_held_by_another_user_is_refused(env):
    env.db.set_players(env.chat.id, [("@anna_b", False, 31337)])
    response = env.act("join")
    assert response.json()["outcome"] == "name_taken"
    assert env.players() == [("@anna_b", False, 31337)]
    (reply,) = env.calls()
    assert (
        reply.params["text"]
        == "Ma @anna\\_b, c'è già qualcuno con questo nome nella lista"
    )


def test_repeating_an_action_changes_nothing(env):
    env.act("join")
    env.world.forget_calls()
    assert env.act("join").json()["outcome"] == "already_in"
    assert env.act("leave").json()["outcome"] == "removed"
    assert env.act("leave").json()["outcome"] == "not_in"
    assert env.players() == []


def test_a_race_in_the_repository_is_a_conflict(env, monkeypatch):
    def lost_race(chat_id, person):
        raise ValueError("not in the list")

    monkeypatch.setitem(web.miniapp.ACTIONS, "leave", lost_race)
    response = env.act("leave")
    assert response.status_code == 409
    assert response.json() == {"error": "conflict"}


def test_a_match_stopped_during_the_action_is_closed(env, monkeypatch):
    def stopped(chat_id, person):
        return None

    monkeypatch.setitem(web.miniapp.ACTIONS, "join", stopped)
    response = env.act("join")
    assert response.status_code == 404
    assert response.json() == {"error": "match_closed"}

    def stopped_at_the_lock(chat_id, person):
        raise LookupError("no match stored")

    monkeypatch.setitem(web.miniapp.ACTIONS, "join", stopped_at_the_lock)
    assert env.act("join").json() == {"error": "match_closed"}


def test_a_failing_group_update_is_logged_by_type_and_the_action_still_succeeds(
    env, caplog
):
    env.world.telegram.fail_next("edit_message_text", "message to edit not found")
    with caplog.at_level(logging.WARNING):
        response = env.act("join")
    assert response.status_code == 200
    assert response.json()["outcome"] == "added"
    assert env.players() == [("@anna_b", False, env.anna.id)]
    assert [r.getMessage() for r in caplog.records] == [
        "Mini app: could not update the group: BadRequest"
    ]


# ---- refusals -----------------------------------------------------------------------------------


def test_a_non_member_is_refused_and_nothing_changes(env):
    stranger = env.world.add_user("eve", "Eve", "eve")
    response = env.act("join", person=stranger)
    assert response.status_code == 403
    assert response.json() == {"error": "not_member"}
    assert env.players() == []
    assert env.calls() == []
    assert env.match(person=stranger).status_code == 403
    for forbidden in (env.token, str(env.chat.id), str(stranger.id), "eve"):
        assert forbidden not in response.text


@pytest.mark.parametrize("status", ["left", "kicked"])
def test_a_member_who_left_is_refused(env, status):
    env.world.member_status[(env.chat.id, env.anna.id)] = status
    assert env.act("join").status_code == 403


def test_an_unknown_token_is_closed(env):
    response = env.match(token="x" * 32)
    assert response.status_code == 404
    assert response.json() == {"error": "match_closed"}


def test_a_stopped_match_is_closed_and_a_new_one_has_a_new_link(env):
    env.world.send("mario", "/stop")
    env.world.forget_calls()
    assert env.match().json() == {"error": "match_closed"}
    env.world.send("mario", "/start")
    assert env.match().status_code == 404  # the old link stays dead


def test_expired_init_data_is_refused(env):
    response = env.match(age=3601)
    assert response.status_code == 401
    assert response.json() == {"error": "session"}
    assert env.match(age=3590).status_code == 200


def test_init_data_signed_for_another_bot_is_refused(env):
    assert env.match(bot_token="1:OTHER").status_code == 401


def test_a_missing_or_wrong_authorization_is_refused(env):
    for headers in ({}, {"Authorization": "Bearer abc"}, {"Authorization": "tma "}):
        response = env.client.post("/app/api/match", json={}, headers=headers)
        assert response.status_code == 401
        assert response.json() == {"error": "session"}
    assert env.players() == []


def test_a_user_without_any_name_is_refused(env):
    nameless = {"id": env.anna.id}
    raw = init_data(
        BOT_TOKEN, auth_date=int(time.time()), start_param=env.token, user=nameless
    )
    response = env.client.post(
        "/app/api/match", json={}, headers={"Authorization": f"tma {raw}"}
    )
    assert response.status_code == 401


@pytest.mark.parametrize(
    "body",
    [
        {"action": "kick"},
        {"action": 1},
        {"action": "join", "extra": 1},
        {},
        [],
        "join",
        None,
    ],
)
def test_a_bad_action_is_a_bad_request(env, body):
    response = env.client.post("/app/api/action", json=body, headers=env.auth())
    assert response.status_code == 400
    assert response.json() == {"error": "bad_request"}
    assert env.players() == []


def test_a_bad_match_body_is_a_bad_request(env):
    for content in (b'{"a": 1}', b"not json", b"\xff\xfe", b"[]", b""):
        response = env.client.post(
            "/app/api/match", content=content, headers=env.auth()
        )
        assert response.status_code == 400


def test_the_body_is_capped_at_4kb(env):
    padding = " " * 4096
    ok = env.client.post(
        "/app/api/action",
        content=('{"action": "join"}' + padding)[:4096],
        headers=env.auth(),
    )
    assert ok.status_code == 200
    big = env.client.post(
        "/app/api/action",
        content=('{"action": "join"}' + padding)[:4097],
        headers=env.auth(),
    )
    assert big.status_code == 400


class Down:
    """A membership check whose Telegram call times out."""

    def __init__(self, text):
        self.text = text

    async def check(self, bot, chat_id, user_id, fresh=False):
        raise TimedOut(self.text)


def test_telegram_being_down_is_unavailable(world, db, freeze_time, enabled):
    freeze_time("2026-10-21 21:00")
    env = Env(world, db, membership=Down("slow"))
    response = env.act("join")
    assert response.status_code == 503
    assert response.json() == {"error": "unavailable"}
    assert env.players() == []


def test_an_unexpected_failure_is_unavailable(env, monkeypatch):
    def broken(chat_id):
        raise RuntimeError("db password=hunter2")

    monkeypatch.setattr(web.miniapp, "get_match", broken)
    response = env.match()
    assert response.status_code == 503
    assert "hunter2" not in response.text


def test_only_post_is_accepted_on_the_api(env):
    assert env.client.get("/app/api/match").status_code == 405
    assert env.client.get("/app/api/action").status_code == 405


# ---- rate limits --------------------------------------------------------------------------------


def test_the_global_limit_applies_before_authentication(
    world, db, freeze_time, enabled
):
    freeze_time("2026-10-21 21:00")
    env = Env(world, db, api_limiter=RateLimiter(3, 60))
    for _ in range(3):
        assert env.client.post("/app/api/match", json={}).status_code == 401
    response = env.client.post("/app/api/match", json={})
    assert response.status_code == 429
    assert response.json() == {"error": "rate_limited"}
    assert env.match().status_code == 429


def test_the_per_user_limit_is_per_user(world, db, freeze_time, enabled):
    freeze_time("2026-10-21 21:00")
    env = Env(world, db, user_limiter=RateLimiter(2, 60))
    assert env.match().status_code == 200
    assert env.match().status_code == 200
    response = env.match()
    assert response.status_code == 429
    assert response.json() == {"error": "rate_limited"}
    world.member_status[(env.chat.id, 1000)] = "member"
    assert env.match(person=world.users["mario"]).status_code == 200


def test_actions_have_their_own_limit(world, db, freeze_time, enabled):
    freeze_time("2026-10-21 21:00")
    env = Env(world, db, action_limiter=RateLimiter(2, 60))
    assert env.act("maybe").status_code == 200
    assert env.act("join").status_code == 200
    response = env.act("leave")
    assert response.status_code == 429
    assert response.json() == {"error": "rate_limited"}
    assert [p[0] for p in env.players()] == ["@anna_b"]
    assert env.match().status_code == 200  # reading is not an action


# ---- page and static files ----------------------------------------------------------------------


def test_the_page_carries_the_security_headers(env):
    response = env.client.get("/app")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["content-security-policy"] == (
        "default-src 'none'; script-src 'self' https://telegram.org; style-src 'self'; "
        "font-src 'self'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; "
        "form-action 'none'"
    )
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "no-cache"
    assert '<html lang="it">' in response.text
    assert "https://telegram.org/js/telegram-web-app.js" in response.text
    assert "/app/static/app.js" in response.text


def test_static_files_are_served_with_nosniff(env):
    response = env.client.get("/app/static/app.js")
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "javascript" in response.headers["content-type"]


def test_the_page_is_the_real_one_and_has_no_inline_code_or_style(env):
    text = env.client.get("/app").text
    assert "/app/static/app.js" in text
    assert "/app/static/app.css" in text
    assert "https://telegram.org/js/telegram-web-app.js" in text
    assert 'href="/app/static/mark.svg"' in text
    assert 'id="app"' in text
    scripts = re.findall(r"<script\b[^>]*>(.*?)</script>", text, flags=re.S)
    assert len(scripts) == 2 and all(body.strip() == "" for body in scripts)
    assert "<style" not in text
    assert not re.search(r"\sstyle\s*=", text)
    assert not re.search(r"\son[a-z]+\s*=", text)


@pytest.mark.parametrize(
    "path, content_type",
    [
        ("/app/static/app.js", "text/javascript"),
        ("/app/static/app.css", "text/css"),
        ("/app/static/mark.svg", "image/svg+xml"),
        ("/app/static/fonts/outfit-latin-500-normal.woff2", "font/woff2"),
        ("/app/static/fonts/outfit-latin-700-normal.woff2", "font/woff2"),
        ("/app/static/fonts/OFL.txt", "text/plain"),
    ],
)
def test_each_static_asset_is_served_with_its_content_type(env, path, content_type):
    response = env.client.get(path)
    assert response.status_code == 200
    assert response.headers["content-type"].split(";")[0] in (
        content_type,
        "application/javascript",  # the same file, as some systems name it
    )
    assert response.headers["x-content-type-options"] == "nosniff"
    assert len(response.content) > 0


@pytest.mark.parametrize(
    "path",
    [
        "/app/static/../index.html",
        "/app/static/%2e%2e/index.html",
        "/app/static/..%2findex.html",
        "/app/static/%2e%2e%2f%2e%2e%2fapp.py",
        "/app/static//etc/passwd",
        "/app/static/missing.js",
    ],
)
def test_path_traversal_under_static_is_rejected(env, path):
    response = env.client.get(path)
    assert response.status_code in (400, 404)
    assert "<!doctype" not in response.text.lower()
    assert "create_app" not in response.text


# ---- feature off --------------------------------------------------------------------------------


def test_with_the_feature_off_there_are_no_app_routes(world):
    app = create_app(world.application, "secret")
    client = TestClient(app)
    for method, path in [
        ("get", "/app"),
        ("get", "/app/static/app.js"),
        ("post", "/app/api/match"),
        ("post", "/app/api/action"),
    ]:
        assert getattr(client, method)(path).status_code == 404


def test_without_a_short_name_no_button_is_added(world, db, freeze_time, monkeypatch):
    freeze_time("2026-10-21 21:00")
    monkeypatch.setattr(conf, "miniapp_short_name", None)
    world.add_chat("Calcetto")
    world.add_user("mario", "Mario", "mario")
    world.send("mario", "/start")
    world.send("mario", "aggiungimi")
    world.send("mario", "proponimi")
    summaries = [
        c for c in world.telegram.calls if "*GIORNO*" in c.params.get("text", "")
    ]
    assert [c.method for c in summaries] == ["send_message", "edit_message_text"]
    assert all("reply_markup" not in c.params for c in summaries)
    assert (
        get_or_create_miniapp_token(world.current_chat.id) is not None
    )  # lazily, on demand


# ---- the link button through the chat flow ------------------------------------------------------


def test_the_button_is_under_a_new_summary_and_under_an_edit(
    world, db, freeze_time, enabled
):
    freeze_time("2026-10-21 21:00")
    chat = world.add_chat("Calcetto")
    world.add_user("mario", "Mario", "mario")
    world.send("mario", "/start")
    world.send("mario", "aggiungimi")  # prints the summary
    world.send("mario", "proponimi")  # edits it
    token = get_or_create_miniapp_token(chat.id)
    expected = [
        [
            {
                "text": "apri la lista",
                "url": f"https://t.me/partitelle_test_bot/lista?startapp={token}",
            }
        ]
    ]
    sent = [c for c in world.telegram.calls if "*GIORNO*" in c.params.get("text", "")]
    assert [c.method for c in sent] == ["send_message", "edit_message_text"]
    for call in sent:
        assert call.params["reply_markup"]["inline_keyboard"] == expected


def test_the_configured_bot_username_wins(world, db, freeze_time, enabled, monkeypatch):
    freeze_time("2026-10-21 21:00")
    monkeypatch.setattr(conf, "bot_username", "other_bot")
    chat = world.add_chat("Calcetto")
    world.add_user("mario", "Mario", "mario")
    world.send("mario", "/start")
    world.send("mario", "aggiungimi")
    token = get_or_create_miniapp_token(chat.id)
    summary = [
        c for c in world.telegram.calls if "*GIORNO*" in c.params.get("text", "")
    ]
    assert (
        summary[0].params["reply_markup"]["inline_keyboard"][0][0]["url"]
        == f"https://t.me/other_bot/lista?startapp={token}"
    )


# ---- logging ------------------------------------------------------------------------------------

SECRET_ID = 987654321
SECRET_USERNAME = "zorro_unico"


def test_nothing_sensitive_is_ever_logged(env, caplog, monkeypatch):
    user = {"id": SECRET_ID, "first_name": "Zeta", "username": SECRET_USERNAME}
    env.world.member_status[(env.chat.id, SECRET_ID)] = "member"
    raws = []

    def headers(token=None, age=0, bot_token=BOT_TOKEN):
        raw = init_data(
            bot_token,
            auth_date=int(time.time()) - age,
            start_param=token or env.token,
            user=user,
        )
        raws.append(raw)
        return {"Authorization": f"tma {raw}"}

    def post(path, body=None, **kw):
        return env.client.post(path, json=body, headers=headers(**kw))

    caplog.set_level(logging.DEBUG)
    # as main.configure_logging sets it: python-telegram-bot logs the parameters of every call at DEBUG
    caplog.set_level(logging.INFO, logger="telegram")
    results = [
        post("/app/api/match", {}),
        post("/app/api/action", {"action": "join"}),
        post("/app/api/action", {"action": "maybe"}),
        post("/app/api/action", {"action": "leave"}),
        post("/app/api/action", {"action": "nope"}),
        post("/app/api/match", {}, token="x" * 32),
        post("/app/api/match", {}, age=99999),
        post("/app/api/match", {}, bot_token="1:OTHER"),
        env.client.post("/app/api/match", json={}),
    ]
    # a user the cache has not seen: a non-member
    outsider = {"id": SECRET_ID + 1, "first_name": "Ex", "username": "ex_unico"}
    raw = init_data(
        BOT_TOKEN, auth_date=int(time.time()), start_param=env.token, user=outsider
    )
    raws.append(raw)
    results.append(
        env.client.post(
            "/app/api/action",
            json={"action": "join"},
            headers={"Authorization": f"tma {raw}"},
        )
    )
    # Telegram failing while the error text holds personal data
    env.world.telegram.fail_next("edit_message_text", f"{SECRET_USERNAME} {SECRET_ID}")
    results.append(post("/app/api/action", {"action": "join"}))
    # acting on others and swapping, with the group's reply failing and a name in the error
    for body in (
        {"action": "add", "text": f"{SECRET_USERNAME}, ex_unico"},
        {"action": "remove", "name": SECRET_USERNAME},
        {"action": "swap", "x": SECRET_USERNAME, "y": "ex_unico"},
    ):
        env.world.telegram.fail_next("send_message", f"{SECRET_USERNAME} {SECRET_ID}")
        results.append(post("/app/api/action", body))

    down = TestClient(
        create_app(
            env.world.application,
            "secret",
            extra_routes=miniapp_routes(
                env.world.application,
                BOT_TOKEN,
                membership=Down(f"{SECRET_USERNAME} {SECRET_ID}"),
            ),
        )
    )
    results.append(down.post("/app/api/match", json={}, headers=headers()))

    def broken(chat_id):
        raise RuntimeError(f"{SECRET_USERNAME} {SECRET_ID} {env.token}")

    monkeypatch.setattr(web.miniapp, "get_match", broken)
    results.append(post("/app/api/match", {}))

    statuses = [r.status_code for r in results]
    assert 200 in statuses and 400 in statuses and 401 in statuses
    assert 403 in statuses and 404 in statuses and 503 in statuses

    logged = "\n".join(
        f"{r.name} {r.getMessage()} {r.exc_text} {r.args}" for r in caplog.records
    )
    # the log is not empty: the failures were logged, by type only
    for logged_type in ("BadRequest", "TimedOut", "RuntimeError"):
        assert logged_type in logged
    secrets = [env.token, str(SECRET_ID), SECRET_USERNAME, "Zeta", "ex_unico"]
    for raw in raws:
        secrets += [raw, raw.rsplit("hash=", 1)[1]]
    for secret in secrets:
        assert secret not in logged, "a secret reached the logs"
    assert "Authorization" not in logged and "tma " not in logged
