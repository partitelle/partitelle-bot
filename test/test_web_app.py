"""The web app: health endpoint (issue #149) and the guarded Telegram webhook."""

import asyncio
import logging
from datetime import datetime, timezone

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


JOBS_SECRET = "jobs-s3cret_value"
JOBS_PATH = "/jobs/payment-reminders"
NOW = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
COUNTS = {"sent": 2, "skipped": 3, "failed": 1}


class FakeSender:
    def __init__(self, result=COUNTS, error=None):
        self.calls = []
        self.result = result
        self.error = error

    async def __call__(self, bot, now):
        self.calls.append((bot, now))
        if self.error:
            raise self.error
        return self.result


def jobs_client(application, sender, jobs_secret=JOBS_SECRET):
    return TestClient(
        create_app(
            application,
            SECRET,
            db_up,
            "abc1234",
            jobs_secret=jobs_secret,
            send_reminders=sender,
            now=lambda: NOW,
        )
    )


def bearer(value=JOBS_SECRET):
    return {"Authorization": f"Bearer {value}"}


@pytest.mark.parametrize("jobs_secret", [None, ""])
def test_jobs_endpoint_is_disabled_without_a_secret(application, jobs_secret):
    sender = FakeSender()
    response = jobs_client(application, sender, jobs_secret).post(
        JOBS_PATH, headers=bearer("")
    )
    assert response.status_code == 404
    assert sender.calls == []


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": JOBS_SECRET},
        {"Authorization": f"Basic {JOBS_SECRET}"},
        bearer("wrong-secret"),
        bearer(""),
    ],
)
def test_jobs_endpoint_rejects_a_missing_or_wrong_secret(application, headers):
    sender = FakeSender()
    response = jobs_client(application, sender).post(JOBS_PATH, headers=headers)
    assert response.status_code == 401
    assert response.content == b""
    assert sender.calls == []


def test_jobs_endpoint_runs_the_reminders_and_returns_counts(application):
    sender = FakeSender()
    response = jobs_client(application, sender).post(JOBS_PATH, headers=bearer())
    assert response.status_code == 200
    assert response.json() == {"sent": 2, "skipped": 3, "failed": 1}
    assert response.headers["Cache-Control"] == "no-store"
    assert len(sender.calls) == 1
    assert sender.calls[0][0] is application.bot
    assert sender.calls[0][1] == NOW


def test_jobs_endpoint_is_unavailable_when_the_sender_fails(application, caplog):
    sender = FakeSender(error=DatabaseUnavailable("chat -100123 Mario Rossi"))
    with caplog.at_level(logging.WARNING):
        response = jobs_client(application, sender).post(JOBS_PATH, headers=bearer())
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
    assert "100123" not in response.text and "Mario" not in response.text
    assert "DatabaseUnavailable" in caplog.text
    assert "100123" not in caplog.text and "Mario" not in caplog.text


def test_jobs_endpoint_accepts_post_only(application):
    sender = FakeSender()
    response = jobs_client(application, sender).get(JOBS_PATH, headers=bearer())
    assert response.status_code == 405
    assert sender.calls == []


def test_jobs_endpoint_has_no_cors_headers(application):
    sender = FakeSender()
    response = jobs_client(application, sender).post(
        JOBS_PATH, headers={**bearer(), "Origin": ORIGIN}
    )
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers
    assert "access-control-allow-methods" not in response.headers


class Clock:
    def __init__(self):
        self.value = 1000.0

    def __call__(self):
        return self.value


class CountingCheck:
    def __init__(self, fail=False):
        self.calls = 0
        self.fail = fail

    async def __call__(self):
        self.calls += 1
        if self.fail:
            raise DatabaseUnavailable("down")


def cached_client(application, check, clock):
    return TestClient(
        create_app(application, SECRET, check, "abc1234", monotonic=clock)
    )


def test_health_cache_windows():
    import web.app as web_app

    assert (web_app.HEALTH_CACHE_OK, web_app.HEALTH_CACHE_FAILED) == (20, 5)


def test_health_checks_the_database_once_within_the_window(application):
    check, clock = CountingCheck(), Clock()
    api = cached_client(application, check, clock)
    bodies = []
    for _ in range(5):
        response = api.get("/health")
        assert response.status_code == 200
        bodies.append(response.json())
        clock.value += 3  # 15 s in total, inside the 20 s window
    assert check.calls == 1
    assert bodies == [{"status": "ok", "version": "abc1234", "database": "ok"}] * 5


def test_health_checks_again_after_the_window(application):
    check, clock = CountingCheck(), Clock()
    api = cached_client(application, check, clock)
    api.get("/health")
    clock.value += 19.9
    api.get("/health")
    assert check.calls == 1
    clock.value += 0.2
    assert api.get("/health").status_code == 200
    assert check.calls == 2


def test_health_caches_a_failure_for_a_shorter_window(application, caplog):
    check, clock = CountingCheck(fail=True), Clock()
    api = cached_client(application, check, clock)
    with caplog.at_level(logging.WARNING):
        assert api.get("/health").status_code == 503
        clock.value += 4.9
        response = api.get("/health")
    assert response.status_code == 503
    assert response.json()["database"] == "unavailable"
    assert check.calls == 1
    assert caplog.text.count("the database is unavailable") == 1
    clock.value += 0.2
    api.get("/health")
    assert check.calls == 2


def test_health_notices_a_recovery_after_the_failure_window(application):
    check, clock = CountingCheck(fail=True), Clock()
    api = cached_client(application, check, clock)
    assert api.get("/health").status_code == 503
    check.fail = False
    clock.value += 5.1
    assert api.get("/health").status_code == 200
    assert check.calls == 2


def test_concurrent_health_requests_share_one_database_check(application):
    import httpx

    clock = Clock()
    calls = []

    async def slow_check():
        calls.append(1)
        await asyncio.sleep(0.05)

    app = create_app(application, SECRET, slow_check, "abc1234", monotonic=clock)

    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as api:
            return await asyncio.gather(*(api.get("/health") for _ in range(10)))

    responses = asyncio.run(run())
    assert [r.status_code for r in responses] == [200] * 10
    assert len(calls) == 1
