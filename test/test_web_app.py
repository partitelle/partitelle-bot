"""The web app: health endpoint (issue #149) and the guarded Telegram webhook."""

import asyncio
import logging

import pytest
from starlette.testclient import TestClient
from telegram.ext import Application

from db.connection import DatabaseUnavailable
from web.app import create_app, resolve_version

SECRET = "s3cret-token_value"
HEADER = "X-Telegram-Bot-Api-Secret-Token"
ORIGIN = "https://partitelle.com"


async def db_up():
    return None


async def db_down():
    raise DatabaseUnavailable("host db.internal:5432 password=hunter2")


async def db_hangs():
    await asyncio.sleep(60)


@pytest.fixture
def application():
    return Application.builder().token("123456:FAKE-token").updater(None).build()


def client(application, check=db_up, version="abc1234"):
    return TestClient(create_app(application, SECRET, check, version))


def test_health_is_ok_when_the_database_answers(application):
    response = client(application).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "abc1234", "database": "ok"}


def test_health_is_degraded_when_the_database_fails(application):
    response = client(application, db_down).get("/health")
    assert response.status_code == 503
    assert response.json() == {
        "status": "degraded",
        "version": "abc1234",
        "database": "unavailable",
    }
    assert "hunter2" not in response.text and "db.internal" not in response.text


def test_health_is_degraded_on_any_unexpected_error(application):
    async def boom():
        raise RuntimeError("boom")

    assert client(application, boom).get("/health").status_code == 503


def test_health_answers_head_without_a_body(application):
    response = client(application).head("/health")
    assert response.status_code == 200
    assert response.content == b""


def test_health_rejects_other_methods(application):
    assert client(application).post("/health").status_code == 405


def test_health_has_no_cors_header_without_origin(application):
    response = client(application).get("/health")
    assert "access-control-allow-origin" not in response.headers


def test_health_has_no_cors_header_for_other_origins(application):
    response = client(application).get(
        "/health", headers={"Origin": "https://evil.example"}
    )
    assert "access-control-allow-origin" not in response.headers


def test_health_allows_the_site_origin(application):
    response = client(application).get("/health", headers={"Origin": ORIGIN})
    assert response.headers["access-control-allow-origin"] == ORIGIN
    assert response.headers["access-control-allow-methods"] == "GET"
    assert response.headers["vary"] == "Origin"


def test_health_cors_also_applies_when_degraded(application):
    response = client(application, db_down).get("/health", headers={"Origin": ORIGIN})
    assert response.status_code == 503
    assert response.headers["access-control-allow-origin"] == ORIGIN


def test_health_is_not_cached(application):
    assert client(application).get("/health").headers["cache-control"] == "no-store"


def test_the_default_check_pings_the_database_with_the_health_timeout(
    application, monkeypatch
):
    import web.app as web_app

    calls = []
    monkeypatch.setattr(web_app, "ping", lambda timeout: calls.append(timeout))
    response = TestClient(create_app(application, SECRET, version="v")).get("/health")
    assert response.status_code == 200
    assert calls == [web_app.HEALTH_TIMEOUT] == [5]


def test_the_default_check_reports_an_unreachable_database_as_503(
    application, monkeypatch
):
    import web.app as web_app

    def unreachable(timeout):
        raise DatabaseUnavailable("down")

    monkeypatch.setattr(web_app, "ping", unreachable)
    response = TestClient(create_app(application, SECRET, version="v")).get("/health")
    assert response.status_code == 503


def test_check_database_times_out(monkeypatch):
    import web.app as web_app

    monkeypatch.setattr(web_app, "HEALTH_TIMEOUT", 0.05)
    monkeypatch.setattr(web_app, "ping", lambda timeout: __import__("time").sleep(1))
    with pytest.raises(TimeoutError):
        asyncio.run(web_app.check_database())


def test_health_never_logs_the_error_text(application, caplog):
    caplog.set_level(logging.DEBUG)
    client(application, db_down).get("/health")
    assert "hunter2" not in caplog.text


@pytest.mark.parametrize("headers", [{}, {HEADER: "wrong"}, {HEADER: ""}])
def test_webhook_rejects_a_missing_or_wrong_secret(application, headers):
    response = client(application).post(
        "/telegram", json={"update_id": 1}, headers=headers
    )
    assert response.status_code == 403
    assert application.update_queue.qsize() == 0


def test_webhook_queues_exactly_one_update_with_the_right_secret(application):
    payload = {"update_id": 4242}
    response = client(application).post(
        "/telegram", json=payload, headers={HEADER: SECRET}
    )
    assert response.status_code == 200
    assert application.update_queue.qsize() == 1
    update = application.update_queue.get_nowait()
    assert update.update_id == 4242


def test_webhook_rejects_a_body_that_is_not_json(application):
    response = client(application).post(
        "/telegram", content=b"not json", headers={HEADER: SECRET}
    )
    assert response.status_code == 400
    assert application.update_queue.qsize() == 0


def test_webhook_accepts_post_only(application):
    assert client(application).get("/telegram").status_code == 405


@pytest.mark.parametrize(
    ("environ", "expected"),
    [
        ({"PB_VERSION": "1.2.3", "RENDER_GIT_COMMIT": "abcdef0123456"}, "1.2.3"),
        ({"RENDER_GIT_COMMIT": "abcdef0123456"}, "abcdef0"),
        ({"PB_VERSION": "", "RENDER_GIT_COMMIT": "abcdef0123456"}, "abcdef0"),
        ({}, "unknown"),
    ],
)
def test_version_resolution_order(environ, expected):
    assert resolve_version(environ) == expected


def test_the_default_version_comes_from_the_environment(application, monkeypatch):
    monkeypatch.setenv("PB_VERSION", "9.9.9")
    response = TestClient(create_app(application, SECRET, db_up)).get("/health")
    assert response.json()["version"] == "9.9.9"


@pytest.mark.parametrize("body", ["null", "[]", '"text"', "{}"])
def test_webhook_rejects_a_json_body_that_is_not_an_update(application, body):
    response = client(application).post(
        "/telegram", content=body, headers={HEADER: SECRET}
    )
    assert response.status_code == 400
    assert application.update_queue.qsize() == 0
