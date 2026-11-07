"""Startup handling of the webhook and jobs secrets (main.py)."""

import asyncio
import hashlib
import hmac
import logging

import pytest

import main
from main import check_secrets, compute_webhook_secret

BOT_TOKEN = "123456:placeholder-token"


def test_the_derived_webhook_secret_is_deterministic_and_valid():
    first = compute_webhook_secret(BOT_TOKEN)
    assert (
        first
        == compute_webhook_secret(BOT_TOKEN, None)
        == compute_webhook_secret(BOT_TOKEN, "")
    )
    assert first != compute_webhook_secret("123456:other-token")
    assert (
        first
        == hmac.new(
            BOT_TOKEN.encode(), b"partitelle-webhook-secret-v1", hashlib.sha256
        ).hexdigest()
    )
    assert len(first) == 64 and set(first) <= set("0123456789abcdef")


def test_the_derived_webhook_secret_is_not_the_plain_hash_of_the_token():
    assert (
        compute_webhook_secret(BOT_TOKEN)
        != hashlib.sha256(BOT_TOKEN.encode()).hexdigest()
    )


def test_a_configured_webhook_secret_wins():
    assert (
        compute_webhook_secret(BOT_TOKEN, "configured_value-1") == "configured_value-1"
    )


def test_the_derived_secret_is_what_the_bot_registers_with_telegram(monkeypatch):
    registered = {}

    class FakeBot:
        async def set_webhook(self, url, secret_token):
            registered["secret_token"] = secret_token

    class FakeApplication:
        bot = FakeBot()
        started = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return None

        async def start(self):
            return None

        async def stop(self):
            return None

    class FakeServer:
        def __init__(self, config):
            pass

        async def serve(self):
            return None

    monkeypatch.setattr(main.uvicorn, "Server", FakeServer)
    monkeypatch.setattr(main.uvicorn, "Config", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "create_app", lambda *args, **kwargs: None)
    secret = compute_webhook_secret(BOT_TOKEN)
    asyncio.run(main.run_web(FakeApplication(), secret))
    assert registered["secret_token"] == secret


def test_a_warning_is_logged_when_the_webhook_secret_is_unset(caplog):
    with caplog.at_level(logging.WARNING):
        check_secrets(None, None)
    assert [r.levelname for r in caplog.records] == ["WARNING"]
    assert "PB_WEBHOOK_SECRET is not set" in caplog.text


def test_no_warning_when_the_webhook_secret_is_set(caplog):
    with caplog.at_level(logging.WARNING):
        check_secrets("configured_value-1", None)
    assert caplog.records == []


@pytest.mark.parametrize("short", ["x", "s" * 31])
def test_an_error_is_logged_for_a_short_jobs_secret_without_its_value(caplog, short):
    with caplog.at_level(logging.WARNING):
        check_secrets("configured_value-1", short)
    assert [r.levelname for r in caplog.records] == ["ERROR"]
    assert "shorter than 32" in caplog.text
    assert short not in caplog.text and str(len(short)) not in caplog.text


@pytest.mark.parametrize("fine", [None, "", "s" * 32])
def test_no_error_for_an_unset_or_long_enough_jobs_secret(caplog, fine):
    with caplog.at_level(logging.WARNING):
        check_secrets("configured_value-1", fine)
    assert caplog.records == []
