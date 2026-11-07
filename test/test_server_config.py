"""The uvicorn config built by main.build_server_config."""

from telegram.ext import Application

import main
from main import build_server_config


def build(secret="placeholder-secret"):
    application = Application.builder().token("123456:FAKE-token").updater(None).build()
    return build_server_config(application, secret)


def route_paths(config):
    return {route.path for route in config.app.routes}


def test_the_web_server_has_no_access_log():
    config = build()
    assert config.access_log is False
    assert config.host == "0.0.0.0"


def test_the_mini_app_routes_are_served_and_still_have_no_access_log(monkeypatch):
    # its paths hold no token or user id (those travel in the Authorization header), but the
    # log stays off for them as for every route
    monkeypatch.setattr(main, "miniapp_short_name", "lista")
    config = build()
    assert config.access_log is False
    assert {"/app", "/app/api/match", "/app/api/action"} <= route_paths(config)
    assert not any("{" in path for path in route_paths(config))  # no path parameter


def test_without_a_short_name_the_mini_app_routes_are_absent(monkeypatch):
    monkeypatch.setattr(main, "miniapp_short_name", None)
    config = build()
    assert config.access_log is False
    assert "/app" not in route_paths(config)
    assert {"/telegram", "/health"} <= route_paths(config)
